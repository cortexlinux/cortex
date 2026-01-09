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
        user's current workflow, intent, and technical expertise level to
        provide highly contextual role suggestions and package recommendations.

        Returns:
            list[str]: A list containing the last 15 trimmed shell commands,
                       or an empty list if sensing is unavailable.
        """
        try:
            # Iterate through common shell history locations for standard Linux environments
            for history_file in [".bash_history", ".zsh_history"]:
                path = Path.home() / history_file

                if path.exists():
                    # Use 'errors=ignore' to prevent decoding crashes. History files
                    # frequently contain non-UTF-8 binary data from interrupted commands.
                    lines = path.read_text(errors="ignore").splitlines()

                    # Gather the last 15 non-empty commands to provide factual context to the AI
                    return [l.strip() for l in lines[-15:] if l.strip()]

        except (OSError, PermissionError) as e:
            # Handle restricted environment cases (e.g., specific security policies)
            # Log as warning for diagnostic visibility without interrupting the user.
            logger.warning(f"Sensing layer could not access shell history: {e}")
            return []
        except Exception as e:
            # Global defensive fallback to ensure sensing layer failures never crash the CLI
            logger.debug(f"Unexpected error during shell pattern sensing: {e}")
            return []

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
        # Signal list expanded to support more modern DevOps and system toolchains.
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

        # PERSISTENCE SYNC: Retrieve the current active role from ~/.cortex/.env.
        # Using 'active_role' instead of 'role_history' prevents 'Persona Pollution'
        # where the AI gets stuck on old role definitions during a manual override.
        current_role = self.get_saved_role()

        return {
            "binaries": detected_binaries,
            "has_gpu": bool(shutil.which("nvidia-smi")),
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
            RuntimeError: If file I/O or locking fails during persistence.
        """

        def modifier(existing_content: str, key: str, value: str) -> str:
            # Logic: Update the value if the key exists, otherwise append to end
            if f"{key}=" in existing_content:
                pattern = rf"^{key}=.*$"
                return re.sub(pattern, f"{key}={value}", existing_content, flags=re.MULTILINE)
            else:
                # Ensure we start on a new line if appending
                if existing_content and not existing_content.endswith("\n"):
                    existing_content += "\n"
                return existing_content + f"{key}={value}\n"

        try:
            self._locked_read_modify_write(self.CONFIG_KEY, role_slug, modifier)
        except Exception as e:
            logger.error(f"Failed to save system role: {e}")
            # Chain exception 'from e' to preserve original diagnostic info
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
