import logging
import os
import re
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any, Optional, TypedDict

# Explicit type annotation for modules to satisfy type-checkers
# and handle conditional imports gracefully.
fcntl: ModuleType | None = None
try:
    import fcntl
except ImportError:
    fcntl = None

msvcrt: ModuleType | None = None
if sys.platform == "win32":
    try:
        import msvcrt
    except ImportError:
        msvcrt = None

logger = logging.getLogger(__name__)


class SystemContext(TypedDict):
    """Structured type representing core system architectural facts."""

    binaries: list[str]
    has_gpu: bool
    patterns: list[str]
    active_role: str
    has_install_history: bool


class RoleManager:
    """
    Provides system context for LLM-driven role detection and recommendations.

    Serves as the 'sensing layer' for the system architect. It aggregates factual
    signals (binary presence, hardware capabilities, and minimized shell patterns)
    to provide a synchronized ground truth for AI inference.
    """

    CONFIG_KEY = "CORTEX_SYSTEM_ROLE"

    # Performance: Precompile patterns once at the class level to optimize regex matching
    # performance across repeated CLI executions and prevent redundant overhead.
    _SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
        re.compile(p)
        for p in [
            r"(?i)api[-_]?key\s*[:=]\s*[^\s]+",
            r"(?i)token\s*[:=]\s*[^\s]+",
            r"(?i)password\s*[:=]\s*[^\s]+",
            r"(?i)passwd\s*[:=]\s*[^\s]+",
            r"(?i)Authorization:\s*[^\s]+",
            r"(?i)Bearer\s+[^\s]+",
            r"(?i)X-Api-Key:\s*[^\s]+",
            r"(?i)-H\s+['\"][^'\"]*auth[^'\"]*['\"]",
            r"(?i)export\s+(?:[^\s]*(?:key|token|secret|password|passwd|credential|auth)[^\s]*)=[^\s]+",
            r"(?i)AWS_(?:ACCESS_KEY_ID|SECRET_ACCESS_KEY)\s*[:=]\s*[^\s]+",
            r"(?i)GOOGLE_APPLICATION_CREDENTIALS\s*[:=]\s*[^\s]+",
            r"(?i)GCP_(?:SERVICE_ACCOUNT|CREDENTIALS)\s*[:=]\s*[^\s]+",
            r"(?i)AZURE_(?:CLIENT_SECRET|TENANT_ID|SUBSCRIPTION_ID)\s*[:=]\s*[^\s]+",
            r"(?i)(?:GITHUB|GITLAB)_TOKEN\s*[:=]\s*[^\s]+",
            r"(?i)docker\s+login.*-p\s+[^\s]+",
            r"(?i)-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
            r"(?i)sshpass\s+-p\s+[^\s]+",
            r"(?i)ssh-add.*-k",
            r"(?i)(?:postgres|mysql|mongodb)://[^@\s]+:[^@\s]+@",
        ]
    )

    def __init__(self, env_path: Path | None = None) -> None:
        """
        Initializes the manager and sets the configuration and history paths.

        Args:
            env_path: Optional Path to the environment file. Defaults to ~/.cortex/.env.
        """
        self.env_file = env_path or (Path.home() / ".cortex" / ".env")
        self.history_db = Path.home() / ".cortex" / "history.db"

    def _get_shell_patterns(self) -> list[str]:
        """
        Senses user activity patterns from local shell history while minimizing privacy risk.

        This method fulfills the 'Learn from patterns' requirement by providing
        contextual intent to the AI. It applies several layers of protection:
        1. Opt-out via 'CORTEX_SENSE_HISTORY' environment variable.
        2. Precompiled regex redaction for known sensitive patterns (API keys, etc.).
        3. Intent tokenization to strip raw arguments and local file paths.
        4. Cleaning of shell-specific metadata (e.g., zsh epoch/duration stamps).

        Returns:
            list[str]: A list of coarse-grained intent tokens (e.g., 'intent:install')
                       or '<redacted>' for sensitive lines.
        """
        import shlex

        # Global opt-out mechanism for users in high-privacy environments
        if os.environ.get("CORTEX_SENSE_HISTORY", "true").lower() == "false":
            return []

        # Maps raw shell verbs to generalized intent categories to prevent data leakage
        intent_map = {
            "apt": "intent:install",
            "pip": "intent:install",
            "npm": "intent:install",
            "kubectl": "intent:k8s",
            "helm": "intent:k8s",
            "docker": "intent:container",
            "git": "intent:version_control",
            "systemctl": "intent:service_mgmt",
            "python": "intent:execution",
        }

        try:
            all_history_lines: list[str] = []
            for history_file in [".bash_history", ".zsh_history"]:
                path = Path.home() / history_file
                if not path.exists():
                    continue

                # Using errors="replace" ensures the CLI handles binary data or
                # corrupted bytes in history files without crashing.
                all_history_lines.extend(
                    path.read_text(encoding="utf-8", errors="replace").splitlines()
                )

            trimmed_commands = [l.strip() for l in all_history_lines if l.strip()]
            recent_commands = trimmed_commands[-15:]

            patterns: list[str] = []
            for cmd in recent_commands:
                # Handle zsh extended history format: ": <epoch>:<duration>;<command>"
                if cmd.startswith(":") and ";" in cmd:
                    cmd = cmd.split(";", 1)[1].strip()

                # Exclude local role management operations from context
                if cmd.startswith("cortex role set"):
                    continue

                # Check against precompiled PII/Credential patterns
                if any(p.search(cmd) for p in self._SENSITIVE_PATTERNS):
                    patterns.append("<redacted>")
                    continue

                # Robust tokenization: Extract the verb using shell-aware splitting
                try:
                    parts = shlex.split(cmd)
                except ValueError:
                    # Fallback to standard split if history has malformed quoting
                    parts = cmd.split()

                if not parts:
                    continue

                # Skip leading environment variable assignments: KEY=value cmd ...
                # This prevents leaking secrets passed directly in the command line.
                while parts and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", parts[0]):
                    parts.pop(0)

                if not parts:
                    patterns.append("<redacted>")
                    continue

                # Data Minimization: Use only the base command name (e.g., /usr/bin/git -> git)
                verb = parts[0].lower()
                if "/" in verb:
                    verb = Path(verb).name

                # Map to a generalized intent or a coarse-grained command token
                patterns.append(intent_map.get(verb, f"intent:{verb}"))

            return patterns

        except OSError as e:
            logger.warning("Access denied to sensing layer history: %s", e)
            return []
        except Exception as e:
            logger.debug("Unexpected error during shell pattern sensing: %s", e)
            return []

    def get_system_context(self) -> SystemContext:
        """
        Aggregates factual system signals and activity patterns for AI inference.

        Returns:
            SystemContext: Factual architectural context including hardware and signals.
        """
        signals = [
            "nginx",
            "apache2",
            "docker",
            "psql",
            "mysql",
            "redis-server",
            "nvidia-smi",
            "rocm-smi",
            "intel_gpu_top",
            "conda",
            "jupyter",
            "gcc",
            "make",
            "git",
            "go",
            "node",
            "ansible",
            "terraform",
            "kubectl",
            "rustc",
            "cargo",
            "python3",
        ]

        # Use 'signal' as loop variable to avoid shadowing built-in bin() function
        detected_binaries = [signal for signal in signals if shutil.which(signal)]

        has_gpu = any(x in detected_binaries for x in ["nvidia-smi", "rocm-smi", "intel_gpu_top"])
        has_install_history = self.history_db.exists()

        return {
            "binaries": detected_binaries,
            "has_gpu": has_gpu,
            "patterns": self._get_shell_patterns(),
            "active_role": self.get_saved_role() or "undefined",
            "has_install_history": has_install_history,
        }

    def save_role(self, role_slug: str) -> None:
        """
        Persists the system role identifier using an atomic update pattern.
        Preserves existing formatting such as 'export' prefixes and quotes.
        """
        if not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9_-]*[a-zA-Z0-9])?", role_slug):
            logger.error("Invalid role slug rejected: %r", role_slug)
            raise ValueError(f"Invalid role slug format: {role_slug!r}")

        def modifier(existing_content: str, key: str, value: str) -> str:
            # Fix: Added $ anchor and clarified groups to prevent value concatenation
            # Group 1: Prefix | Group 2: Quote | Group 3: Old Value | Group 4: Closing Quote/End
            pattern = (
                rf"^(\s*(?:export\s+)?{re.escape(key)}\s*=\s*)(['\"]?)(.*?)(['\"]?\s*(?:#.*)?)$"
            )

            if re.search(pattern, existing_content, flags=re.MULTILINE):
                return re.sub(
                    pattern,
                    lambda m: f"{m.group(1)}{m.group(2)}{value}{m.group(4)}",
                    existing_content,
                    flags=re.MULTILINE,
                )
            else:
                if existing_content and not existing_content.endswith("\n"):
                    existing_content += "\n"
                return existing_content + f"{key}={value}\n"

        try:
            self._locked_read_modify_write(self.CONFIG_KEY, role_slug, modifier)
        except Exception as e:
            logger.error("Failed to persist system role: %s", e)
            raise RuntimeError(f"Could not persist role to {self.env_file}") from e

    def get_saved_role(self) -> str | None:
        """
        Reads the active role with tolerant parsing for standard shell file formats.

        Handles leading whitespace, optional 'export' prefix, flexible assignment
        spacing, quotes, and ignores trailing inline comments.
        """
        if not self.env_file.exists():
            return None

        try:
            content = self.env_file.read_text(encoding="utf-8", errors="replace")

            # Improved Regex:
            # ^\s* -> Allows leading whitespace
            # (?:export\s+)? -> Optional export
            # \s*=\s* -> Flexible spacing around equals
            # ['\"]?(.*?)['\"]? -> Non-greedy capture of value inside optional quotes
            # (?:\s*#.*)?$   -> Ignores trailing whitespace and inline comments
            pattern = rf"^\s*(?:export\s+)?{re.escape(self.CONFIG_KEY)}\s*=\s*['\"]?(.*?)['\"]?(?:\s*#.*)?$"

            # Use findall and pick the last match to follow standard shell override behavior
            matches = re.findall(pattern, content, re.MULTILINE)

            if not matches:
                return None

            value = matches[-1].strip()
            return value if value else None
        except Exception as e:
            logger.error("Error reading saved role: %s", e)
            return None

    def _locked_read_modify_write(
        self,
        key: str,
        value: str,
        modifier_func: Callable[[str, str, str], str],
        target_file: Path | None = None,
    ) -> None:
        """
        Performs a thread-safe, atomic file update with cross-platform locking support.

        This internal utility implements a 'write-to-temporary-and-swap' pattern to
        ensure file integrity. It prevents lost updates by using POSIX advisory
        locking (fcntl) or Windows byte-range locking (msvcrt). It specifically
        handles file path collisions and provides safety for restricted filesystems.

        Args:
            key: The configuration key to update.
            value: The new value to set.
            modifier_func: A callback to handle the specific string manipulation.
            target_file: Optional path override for the target file.
        """
        target = target_file or self.env_file
        target.parent.mkdir(parents=True, exist_ok=True)

        # 1. Collision Prevention: Use full filename for companion files.
        # This prevents collisions between '.env' and '.env.local' companion files.
        lock_file = target.parent.joinpath(f"{target.name}.lock")
        lock_file.touch(exist_ok=True)
        try:
            lock_file.chmod(0o600)
        except OSError:
            # Silently ignore chmod failures on unsupported filesystems (e.g., WSL, FAT32)
            pass

        temp_file = target.parent.joinpath(f"{target.name}.tmp")

        try:
            with open(lock_file, "r+") as lock_fd:
                # 2. Acquire platform-specific exclusive lock.
                # Logic switches between POSIX (fcntl) and Windows (msvcrt).
                if fcntl:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX)
                elif msvcrt:
                    # Windows locking requires a specific byte range; 1 byte is sufficient.
                    msvcrt.locking(lock_fd.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    # Defensive signal: Warn if the environment lacks atomic locking support.
                    logger.warning(
                        "No file locking backend available (fcntl/msvcrt missing). "
                        "Concurrent updates to %s may result in data loss.",
                        target.name,
                    )

                try:
                    # 3. Read existing data with error-resilient decoding.
                    # 'replace' handler prevents crashes on corrupted binary markers.
                    existing = (
                        target.read_text(encoding="utf-8", errors="replace")
                        if target.exists()
                        else ""
                    )

                    # 4. Generate modified content via the provided callback.
                    updated = modifier_func(existing, key, value)

                    # 5. Write to temporary file with secure permissions.
                    temp_file.write_text(updated, encoding="utf-8")
                    try:
                        temp_file.chmod(0o600)
                    except OSError:
                        pass

                    # 6. Atomic swap guaranteed by the OS 'replace' operation.
                    temp_file.replace(target)
                finally:
                    # 7. Release lock regardless of write success.
                    if fcntl:
                        fcntl.flock(lock_fd, fcntl.LOCK_UN)
                    elif msvcrt:
                        msvcrt.locking(lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            # 8. Integrity Cleanup: Remove orphaned temporary files if replace() failed.
            if temp_file.exists():
                try:
                    os.remove(temp_file)
                except OSError:
                    pass
