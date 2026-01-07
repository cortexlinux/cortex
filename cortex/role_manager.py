"""
Role management and system personality detection for Cortex.
Handles identification of system purpose and suggests relevant software stacks.
"""

import copy
import fcntl
import logging
import os
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class RoleManager:
    """
    Manages system role detection and package recommendations.

    This class acts as the source of truth for what a system 'is' based on
    installed binaries and what it 'should be' based on user-set roles.
    """

    # Constants for role slugs to prevent string typos throughout the app
    ROLE_WEB_SERVER = "web-server"
    ROLE_DB_SERVER = "database-server"
    ROLE_ML_WORKSTATION = "ml-workstation"

    # Canonical configuration key
    CONFIG_KEY = "CORTEX_SYSTEM_ROLE"

    # Mapping of user-friendly names to internal slugs and their detection binaries
    ROLE_DEFINITIONS: dict[str, dict[str, Any]] = {
        "Web Server": {
            "slug": ROLE_WEB_SERVER,
            "binaries": ["nginx", "apache2", "httpd"],
            "recommendations": ["Certbot", "Fail2Ban", "Nginx Amplify"],
        },
        "Database Server": {
            "slug": ROLE_DB_SERVER,
            "binaries": ["psql", "mysql", "mongod", "redis-server"],
            "recommendations": ["pgAdmin", "Redis Insight", "Database Backup Tools"],
        },
        "ML Workstation": {
            "slug": ROLE_ML_WORKSTATION,
            "binaries": ["nvidia-smi", "nvcc", "conda", "jupyter"],
            "recommendations": [
                "CUDA Toolkit",
                "PyTorch",
                "TensorFlow",
                "Jupyter Lab",
                "NVIDIA Drivers",
            ],
        },
    }

    def __init__(self, env_path: Path | None = None) -> None:
        """Initializes the RoleManager and loads custom role definitions.

        Args:
            env_path: Optional custom path to the .env file.
                     Defaults to ~/.cortex/.env.
        """
        self.env_file = env_path or (Path.home() / ".cortex" / ".env")
        self.custom_roles_file = self.env_file.parent / "custom_roles.json"

        # We use a copy of ROLE_DEFINITIONS to avoid mutating the class constant
        self.roles = copy.deepcopy(self.ROLE_DEFINITIONS)
        self._load_custom_roles()

    def _load_custom_roles(self) -> None:
        """Loads user-defined roles from custom_roles.json if the file exists.

        This allows users to define their own system roles and package
        bundles without modifying the Cortex source code.
        """
        if not self.custom_roles_file.exists():
            return

        import json

        try:
            # Atomic read of user-defined roles
            custom_data = json.loads(self.custom_roles_file.read_text())
            # Merge custom roles into the active roles dictionary
            self.roles.update(custom_data)
        except Exception as e:
            logger.error(f"Failed to load custom roles from {self.custom_roles_file}: {e}")

    def detect_active_roles(self) -> list[str]:
        """
        Scans the system PATH to identify currently active roles based on binaries.

        Returns:
            list[str]: A list of human-readable role names detected on the system.
        """
        detected_roles: list[str] = []

        for role_name, config in self.roles.items():
            try:
                if any(shutil.which(binary) for binary in config["binaries"]):
                    detected_roles.append(role_name)
            except Exception as e:
                logger.error(f"Error detecting binary for {role_name}: {e}")

        return detected_roles

    def save_role(self, role_slug: str) -> None:
        """
        Persists the selected role to the Cortex environment file securely.

        Args:
            role_slug: The machine-readable identifier to save.
        """

        def modifier(existing_content: str, key: str, value: str) -> str:
            if f"{key}=" in existing_content:
                # Update existing key
                pattern = rf"^{key}=.*$"
                return re.sub(pattern, f"{key}={value}", existing_content, flags=re.MULTILINE)
            else:
                # Append new key
                if existing_content and not existing_content.endswith("\n"):
                    existing_content += "\n"
                return existing_content + f"{key}={value}\n"

        try:
            self._locked_read_modify_write(self.CONFIG_KEY, role_slug, modifier)
        except Exception as e:
            logger.error(f"Failed to save system role: {e}")
            raise RuntimeError(f"Could not persist role to {self.env_file}")

    def get_saved_role(self) -> str | None:
        """
        Retrieves the currently set role from the configuration file.

        Returns:
            Optional[str]: The role slug if set, otherwise None.
        """
        if not self.env_file.exists():
            return None

        try:
            content = self.env_file.read_text()
            match = re.search(rf"^{self.CONFIG_KEY}=(.*)$", content, re.MULTILINE)
            return match.group(1).strip() if match else None
        except Exception as e:
            logger.error(f"Error reading saved role: {e}")
            return None

    def get_recommendations_by_slug(self, role_slug: str) -> list[str]:
        """
        Retrieves package recommendations for a specific role slug.

        Args:
            role_slug: The machine-readable identifier for the role.

        Returns:
            List[str]: A list of recommended packages.
        """
        for config in self.roles.values():
            if config["slug"] == role_slug:
                return config["recommendations"]
        return []

    def get_all_slugs(self) -> list[str]:
        """
        Returns all valid role slugs for validation purposes.

        Returns:
            List[str]: List of valid slugs.
        """
        return [config["slug"] for config in self.roles.values()]

    def learn_package(self, role_slug: str, package_name: str) -> None:
        """
        Records a successfully installed package as a recommendation for a role.

        This builds local intelligence of which packages are commonly used
        within specific system personalities.
        """
        # Define the separate storage file to maintain .env cleanliness
        learned_file = self.env_file.parent / "learned_roles.json"

        def modifier(existing_json: str, key: str, value: str) -> str:
            import json

            try:
                # Safely handle empty files or malformed JSON
                data = json.loads(existing_json) if existing_json else {}
            except json.JSONDecodeError:
                data = {}

            if key not in data:
                data[key] = []

            # Only add the package if it's not already recorded
            if value not in data[key]:
                data[key].append(value)

            return json.dumps(data, indent=4)

        try:
            # Use target_file to ensure thread-safe writes to learned_roles.json
            # without mutating the global state of the manager instance.
            self._locked_read_modify_write(
                role_slug, package_name, modifier, target_file=learned_file
            )
        except Exception as e:
            logger.error(f"Failed to learn package {package_name} for role {role_slug}: {e}")

    def _locked_read_modify_write(
        self,
        key: str,
        value: str,
        modifier_func: Callable[[str, str, str], str],
        target_file: Path | None = None,
    ) -> None:
        """
        Performs a thread-safe and process-safe write to a configuration file.
        Defaults to self.env_file unless target_file is provided.
        """
        # Use target_file if provided, otherwise fall back to the default env_file
        target = target_file or self.env_file

        # Ensure directory exists
        target.parent.mkdir(parents=True, exist_ok=True)

        # Define lock and temp files based on the target
        lock_file = target.with_suffix(".lock")
        lock_file.touch(exist_ok=True)

        with open(lock_file, "r+") as lock_fd:
            # Acquire exclusive lock
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                # Read current state from the correct target
                existing = target.read_text() if target.exists() else ""

                # Apply the modification logic
                updated = modifier_func(existing, key, value)

                # Atomic write via temporary file to prevent corruption
                temp_file = target.with_suffix(".tmp")
                temp_file.write_text(updated)
                temp_file.chmod(0o600)

                # Atomic swap
                temp_file.replace(target)
            finally:
                # Release lock
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
