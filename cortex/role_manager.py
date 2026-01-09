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
    environment for technical signals (binaries, hardware) and packages them
    into a context object. This object is then fed to the AI layer to determine
    the system's role contextually, satisfying the requirement for
    dynamic, non-hardcoded role detection.
    """

    # Key used for persisting the LLM's classification in the .env file
    CONFIG_KEY = "CORTEX_SYSTEM_ROLE"

    def __init__(self, env_path: Path | None = None) -> None:
        """
        Initializes the manager and sets the configuration file path.

        Args:
            env_path: Optional Path to the environment file.
                     Defaults to ~/.cortex/.env.
        """
        self.env_file = env_path or (Path.home() / ".cortex" / ".env")

    def _get_shell_patterns(self) -> list[str]:
        """
        Senses user activity patterns from local shell history files.

        This method fulfills the 'Learn from patterns' acceptance criteria. By
        providing the LLM with recent command history, the AI can infer the
        user's current workflow and intent.

        To protect user privacy, obvious secrets (API keys, tokens, passwords)
        are redacted before being passed to the AI layer.

        Returns:
            list[str]: A list containing the last 15 trimmed and redacted shell
                       commands, or an empty list if sensing is unavailable.
        """
        # Define common markers for sensitive data to redact PII before AI processing.
        # This prevents accidental leakage of API keys or credentials.
        secret_markers = (
            "AWS_SECRET_ACCESS_KEY",
            "GITHUB_TOKEN",
            "NPM_TOKEN",
            "PASSWORD",
            "passwd",
            "Authorization:",
            "Bearer ",
        )

        try:
            all_history_lines: list[str] = []

            # Iterate through common shell history locations.
            # We now collect from both .bash_history and .zsh_history to provide
            # a more comprehensive context of user activity.
            for history_file in [".bash_history", ".zsh_history"]:
                path = Path.home() / history_file

                if not path.exists():
                    continue

                # Use 'errors=ignore' to prevent decoding crashes. History files
                # frequently contain non-UTF-8 binary data from interrupted commands.
                # We explicitly use utf-8 encoding for consistency.
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
                all_history_lines.extend(lines)

            # Filter for non-empty, trimmed commands
            trimmed_commands = [l.strip() for l in all_history_lines if l.strip()]

            # Gather the last 15 commands to provide factual context to the AI
            recent_commands = trimmed_commands[-15:]

            # Redaction Logic: Replace any command containing a secret marker with <redacted>.
            # This ensures technical intent is preserved without exposing sensitive values.
            return [
                "<redacted>" if any(marker in cmd for marker in secret_markers) else cmd
                for cmd in recent_commands
            ]

        except (OSError, PermissionError) as e:
            # Handle restricted environment cases. We use lazy %-formatting for logging
            # to follow Python production-grade best practices.
            logger.warning("Sensing layer could not access shell history: %s", e)
            return []
        except Exception as e:
            # Global defensive fallback to ensure sensing layer failures never crash the CLI
            logger.debug("Unexpected error during shell pattern sensing: %s", e)
            return []

    def get_system_context(self) -> dict[str, Any]:
        """
        Gathers factual system signals and activity patterns for AI inference.

        Acts as the 'sensing layer' for the AI Architect. Instead of sending
        ambiguous history, it provides a synchronized snapshot of the system's
        current factual environment and active persona.

        Returns:
            dict: A dictionary containing:
                - binaries: Signature tools found in system PATH.
                - has_gpu: NVIDIA hardware availability.
                - patterns: Recent shell usage patterns (Learn from patterns).
                - active_role: The single source of truth for the current role state.
        """
        # A curated list of signature binaries across various domains (Web, DB, ML, Dev).
        # These act as 'feature flags' for the AI model to identify machine use-cases.
        signals = [
            "nginx",
            "apache2",
            "docker",
            "psql",
            "mysql",
            "redis-server",
            "nvidia-smi",
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

        # Fact gathering: Short-circuit check for binary existence in system PATH.
        detected_binaries = [bin for bin in signals if shutil.which(bin)]

        # OPTIMIZATION: Reuse the detected_binaries list to determine GPU presence.
        # This addresses the CodeRabbit review by avoiding a redundant shutil.which()
        # system call for "nvidia-smi".
        has_gpu = "nvidia-smi" in detected_binaries

        # PERSISTENCE SYNC: Retrieve the current active role from ~/.cortex/.env.
        # Using 'active_role' instead of 'role_history' prevents 'Persona Pollution'
        # where the AI gets stuck on old role definitions during a manual override.
        current_role = self.get_saved_role()

        return {
            "binaries": detected_binaries,
            "has_gpu": has_gpu,
            "patterns": self._get_shell_patterns(),  # Fulfills: 'Learn from patterns'
            "active_role": current_role if current_role else "undefined",
        }

    def save_role(self, role_slug: str) -> None:
        """
        Persists the LLM-selected role identifier to the environment file.

        This uses a thread-safe modification loop to ensure that even if
        multiple processes are interacting with Cortex, the .env file
        remains uncorrupted.

        Args:
            role_slug: The string identifier determined by the AI.

        Raises:
            ValueError: If the role_slug contains malicious injection characters.
            RuntimeError: If file I/O or locking fails during persistence.
        """
        # CRITICAL: Validate the role_slug to prevent .env injection.
        # This ensures no newlines or '=' characters can be used to inject
        # arbitrary environment variables into the .env file.
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?", role_slug):
            logger.error(f"Malicious or invalid role slug blocked: {role_slug!r}")
            raise ValueError(f"Invalid role slug format: {role_slug!r}")

        def modifier(existing_content: str, key: str, value: str) -> str:
            """
            Atomic internal modifier for the read-modify-write cycle.
            """
            # Use re.escape on the key to prevent regex injection.
            # We use a line-start anchor (^) to avoid false positives where
            # the key name might appear inside another variable's value.
            pattern = rf"^{re.escape(key)}=.*$"

            if re.search(pattern, existing_content, flags=re.MULTILINE):
                # We use a lambda for the replacement string. This is a security
                # best practice to ensure backslashes in the 'value' are treated
                # as literal text and not as regex backreferences.
                return re.sub(
                    pattern, lambda _: f"{key}={value}", existing_content, flags=re.MULTILINE
                )
            else:
                # Append to the end of the file if the key doesn't exist.
                # Ensure we start on a new line to maintain valid .env syntax.
                if existing_content and not existing_content.endswith("\n"):
                    existing_content += "\n"
                return existing_content + f"{key}={value}\n"

        try:
            # Standardized utility for atomic, thread-safe file updates.
            # Implements an advisory locking mechanism using fcntl.
            self._locked_read_modify_write(self.CONFIG_KEY, role_slug, modifier)
        except Exception as e:
            # We use logging with placeholders for better performance and
            # chain the exception to preserve the original traceback for debugging.
            logger.error("Failed to save system role: %s", e)
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
            # Regex extracts the value following the CORTEX_SYSTEM_ROLE key
            match = re.search(rf"^{self.CONFIG_KEY}=(.*)$", content, re.MULTILINE)
            return match.group(1).strip() if match else None
        except Exception as e:
            logger.error(f"Error reading saved role: {e}")
            return None

    def _locked_read_modify_write(
        self,
        key: str,
        value: str,
        modifier_func: Callable[[str, str, str], str],
        target_file: Path | None = None,
    ) -> None:
        """
        Standardized utility for atomic, thread-safe file updates.

        Implements an advisory locking mechanism using fcntl and an
        atomic swap pattern. This ensures 'No silent administrative
        execution' failures and protects against partial writes.
        """
        target = target_file or self.env_file
        target.parent.mkdir(parents=True, exist_ok=True)

        # Use a hidden .lock file to coordinate access across processes
        lock_file = target.with_suffix(".lock")
        lock_file.touch(exist_ok=True)

        with open(lock_file, "r+") as lock_fd:
            # Block until exclusive lock is acquired
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                existing = target.read_text() if target.exists() else ""
                updated = modifier_func(existing, key, value)

                # Use a temp file for the write to ensure atomicity
                temp_file = target.with_suffix(".tmp")
                temp_file.write_text(updated)
                temp_file.chmod(0o600)  # Restrict to user-only read/write

                # Atomic swap: The OS ensures this operation is 'all or nothing'
                temp_file.replace(target)
            finally:
                # Always release the lock, even if the write fails
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
