import fcntl
import logging
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class RoleManager:
    """
    Provides system context for LLM-driven role detection and recommendations.

    This class serves as the 'sensing layer' for Cortex. It scans the local
    environment for technical signals (binaries, hardware, and history) and
    packages them into a synchronized Single Source of Truth for AI inference.
    """

    # Configuration keys and paths
    CONFIG_KEY = "CORTEX_SYSTEM_ROLE"

    def __init__(self, env_path: Path | None = None) -> None:
        """
        Initializes the manager and sets the configuration and history paths.

        Args:
            env_path: Optional Path to the environment file.
                     Defaults to ~/.cortex/.env.
        """
        self.env_file = env_path or (Path.home() / ".cortex" / ".env")
        # Learning from installations: Reference the local history database
        self.history_db = Path.home() / ".cortex" / "history.db"

    def _get_shell_patterns(self) -> list[str]:
        """
        Senses user activity patterns from local shell history files with
        hardened regex-based PII redaction.

        This method fulfills the 'Learn from patterns' requirement by providing
        contextual intent to the AI while ensuring sensitive credentials like
        API keys, tokens, and exported secrets are sanitized.

        Returns:
            list[str]: The last 15 trimmed and redacted shell commands.
        """
        # Advanced regex patterns to detect sensitive data (API keys, exports, and curl headers)
        sensitive_patterns = [
            r"(?i)api[-_]?key\s*[:=]\s*[^\s]+",  # Catch API_KEY=xxx or API-Key: xxx
            r"(?i)token\s*[:=]\s*[^\s]+",  # Catch token=xxx or Token: xxx
            r"(?i)password\s*[:=]\s*[^\s]+",  # Catch password=xxx
            r"(?i)passwd\s*[:=]\s*[^\s]+",  # Catch passwd=xxx
            r"(?i)Authorization:\s*[^\s]+",  # Catch HTTP Authorization headers
            r"(?i)Bearer\s+[^\s]+",  # Catch Bearer authentication tokens
            r"(?i)export\s+[^\s]+=[^\s]+",  # Catch environment variable exports
            r"(?i)-H\s+['\"][^'\"]*auth[^'\"]*['\"]",  # Catch sensitive curl auth headers
            r"(?i)X-Api-Key:\s*[^\s]+",  # Catch specific X-Api-Key headers (FastAPI)
        ]

        try:
            all_history_lines: list[str] = []
            for history_file in [".bash_history", ".zsh_history"]:
                path = Path.home() / history_file
                if not path.exists():
                    continue

                # Standardizing on utf-8 with error handling for corrupted binary data
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
                all_history_lines.extend(lines)

            trimmed_commands = [l.strip() for l in all_history_lines if l.strip()]
            recent_commands = trimmed_commands[-15:]

            # Redaction: Replace commands matching sensitive patterns with a safe placeholder
            return [
                "<redacted>" if any(re.search(p, cmd) for p in sensitive_patterns) else cmd
                for cmd in recent_commands
                if not cmd.startswith("cortex role set")
            ]

        except (OSError, PermissionError) as e:
            logger.warning("Access denied to sensing layer history: %s", e)
            return []
        except Exception as e:
            logger.debug("Unexpected error during shell pattern sensing: %s", e)
            return []

    def get_system_context(self) -> dict[str, Any]:
        """
        Aggregates factual system signals and activity patterns for AI inference.

        Acts as the 'sensing layer' for the AI Architect. This method now
        incorporates multi-vendor GPU detection (NVIDIA, AMD, Intel) and
        installation history to provide a complete factual ground truth.

        Returns:
            dict: Synchronized facts including binaries, hardware acceleration,
                  patterns, active persona, and installation history flag.
        """
        # Curated signature binaries for cross-domain identification (Web, DB, ML, Dev)
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

        detected_binaries = [bin for bin in signals if shutil.which(bin)]

        # Broad hardware detection: Check for NVIDIA, AMD (ROCm), or Intel GPU tools
        has_gpu = any(x in detected_binaries for x in ["nvidia-smi", "rocm-smi", "intel_gpu_top"])

        # Check for installation history to satisfy 'Learning from installations'
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
        Persists the AI-selected role identifier to the configuration file.

        Args:
            role_slug: The role slug. Supports alphanumeric characters, dashes,
                       and underscores (e.g., 'ml', 'ML-Workstation').

        Raises:
            ValueError: If the role_slug format is invalid or malicious.
            RuntimeError: If file persistence fails.
        """
        # Professional-grade validation: Allows short slugs ('ml') and uppercase
        if not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9_-]*[a-zA-Z0-9])?", role_slug):
            logger.error("Invalid role slug rejected: %r", role_slug)
            raise ValueError(f"Invalid role slug format: {role_slug!r}")

        def modifier(existing_content: str, key: str, value: str) -> str:
            """Safe regex-based modifier for atomic file updates."""
            pattern = rf"^{re.escape(key)}=.*$"

            if re.search(pattern, existing_content, flags=re.MULTILINE):
                # Using a lambda ensures backslashes are treated as literal text
                return re.sub(
                    pattern, lambda _: f"{key}={value}", existing_content, flags=re.MULTILINE
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
        Reads the currently active role from the configuration file.

        Returns:
            str | None: The saved role slug or None if no role is configured.
        """
        if not self.env_file.exists():
            return None

        try:
            content = self.env_file.read_text()
            match = re.search(rf"^{self.CONFIG_KEY}=(.*)$", content, re.MULTILINE)
            return match.group(1).strip() if match else None
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
        Performs an atomic, thread-safe file update with advisory locking.
        """
        target = target_file or self.env_file
        target.parent.mkdir(parents=True, exist_ok=True)

        lock_file = target.with_suffix(".lock")
        lock_file.touch(exist_ok=True)

        with open(lock_file, "r+") as lock_fd:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                existing = target.read_text() if target.exists() else ""
                updated = modifier_func(existing, key, value)

                temp_file = target.with_suffix(".tmp")
                temp_file.write_text(updated)
                temp_file.chmod(0o600)  # User-restricted permissions

                # Atomic swap ensures data integrity
                temp_file.replace(target)
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
