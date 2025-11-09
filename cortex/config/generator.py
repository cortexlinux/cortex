"""
Configuration File Generator with template support.
"""

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from .exceptions import (
    ConfigError,
    ValidationError,
    TemplateError,
    BackupError,
)
from .validators import get_validator


class ConfigGenerator:
    """
    Generate configuration files from templates with validation and backup support.

    Supported configuration types:
        - nginx: Web server and reverse proxy configurations
        - postgres: PostgreSQL database configurations
        - redis: Redis cache server configurations
        - docker-compose: Docker Compose orchestration files
        - apache: Apache web server configurations

    Example:
        >>> cg = ConfigGenerator()
        >>> cg.generate("nginx", reverse_proxy=True, target_port=3000)
        >>> # Creates nginx configuration file

    Attributes:
        template_dir: Directory containing configuration templates
        output_dir: Directory where generated configs will be saved
        backup_dir: Directory where config backups are stored
        validate_configs: Whether to validate configs before writing
        create_backups: Whether to backup existing configs
    """

    # Default output paths for different config types
    DEFAULT_PATHS = {
        "nginx": "/etc/nginx/sites-available/app.conf",
        "postgres": "/etc/postgresql/postgresql.conf",
        "redis": "/etc/redis/redis.conf",
        "docker-compose": "./docker-compose.yml",
        "apache": "/etc/apache2/sites-available/app.conf",
    }

    # Template file extensions
    TEMPLATE_EXTENSIONS = {
        "nginx": "nginx.conf.template",
        "postgres": "postgresql.conf.template",
        "redis": "redis.conf.template",
        "docker-compose": "docker-compose.yml.template",
        "apache": "apache.conf.template",
    }

    def __init__(
        self,
        template_dir: Optional[str] = None,
        output_dir: Optional[str] = None,
        backup_dir: Optional[str] = None,
        validate_configs: bool = True,
        create_backups: bool = True,
    ):
        """
        Initialize ConfigGenerator.

        Args:
            template_dir: Directory containing templates (defaults to package templates)
            output_dir: Base directory for generated configs (defaults to current directory)
            backup_dir: Directory for backups (defaults to ~/.cortex/backups)
            validate_configs: Enable validation before writing (default: True)
            create_backups: Enable backup of existing configs (default: True)
        """
        if template_dir is None:
            # Use package templates directory
            package_dir = Path(__file__).parent
            template_dir = str(package_dir / "templates")

        self.template_dir = Path(template_dir)
        self.output_dir = Path(output_dir) if output_dir else Path.cwd()
        self.backup_dir = (
            Path(backup_dir) if backup_dir else Path.home() / ".cortex" / "backups"
        )
        self.validate_configs = validate_configs
        self.create_backups = create_backups

        # Initialize Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

        # Ensure directories exist
        self._ensure_directories()

    def _ensure_directories(self):
        """Create necessary directories if they don't exist."""
        self.template_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if self.create_backups:
            self.backup_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        config_type: str,
        output_path: Optional[str] = None,
        dry_run: bool = False,
        **kwargs,
    ) -> str:
        """
        Generate a configuration file from template.

        Args:
            config_type: Type of config (nginx, postgres, redis, docker-compose, apache)
            output_path: Custom output path (uses default if not provided)
            dry_run: If True, return config without writing to file
            **kwargs: Template variables for substitution

        Returns:
            Generated configuration content as string

        Raises:
            ConfigError: If config generation fails
            ValidationError: If validation fails
            TemplateError: If template processing fails

        Example:
            >>> cg = ConfigGenerator()
            >>> config = cg.generate(
            ...     "nginx",
            ...     reverse_proxy=True,
            ...     target_port=3000,
            ...     server_name="example.com"
            ... )
        """
        # Validate config type
        if config_type not in self.TEMPLATE_EXTENSIONS:
            raise ConfigError(
                f"Unsupported config type: {config_type}. "
                f"Supported types: {', '.join(self.TEMPLATE_EXTENSIONS.keys())}"
            )

        # Load and render template
        try:
            config_content = self._render_template(config_type, kwargs)
        except Exception as e:
            raise TemplateError(f"Failed to render template for {config_type}: {e}")

        # Validate configuration
        if self.validate_configs:
            warnings = self._validate_config(config_type, config_content, kwargs)
            if warnings:
                print(f"⚠️  Validation warnings for {config_type}:")
                for warning in warnings:
                    print(f"   - {warning}")

        # Return without writing if dry run
        if dry_run:
            return config_content

        # Determine output path
        if output_path is None:
            output_path = self._get_default_path(config_type)
        output_path = Path(output_path)

        # Backup existing file if requested
        if self.create_backups and output_path.exists():
            self._backup_file(output_path)

        # Write configuration file
        self._write_config(output_path, config_content)

        print(f"✅ Generated {config_type} configuration: {output_path}")
        return config_content

    def _render_template(self, config_type: str, params: Dict[str, Any]) -> str:
        """
        Render template with provided parameters.

        Args:
            config_type: Type of configuration
            params: Template parameters

        Returns:
            Rendered configuration content

        Raises:
            TemplateError: If template cannot be loaded or rendered
        """
        template_file = self.TEMPLATE_EXTENSIONS[config_type]

        try:
            template = self.env.get_template(template_file)
            return template.render(**params)
        except TemplateNotFound:
            raise TemplateError(
                f"Template not found: {template_file} in {self.template_dir}"
            )
        except Exception as e:
            raise TemplateError(f"Failed to render template {template_file}: {e}")

    def _validate_config(
        self, config_type: str, config_content: str, params: Dict[str, Any]
    ) -> List[str]:
        """
        Validate generated configuration.

        Args:
            config_type: Type of configuration
            config_content: Generated configuration content
            params: Parameters used for generation

        Returns:
            List of validation warnings

        Raises:
            ValidationError: If validation fails critically
        """
        try:
            validator = get_validator(config_type)
            return validator.validate(config_content, params)
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(f"Validation failed for {config_type}: {e}")

    def _backup_file(self, file_path: Path):
        """
        Create backup of existing configuration file.

        Args:
            file_path: Path to file to backup

        Raises:
            BackupError: If backup fails
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{file_path.name}.{timestamp}.backup"
            backup_path = self.backup_dir / backup_name

            shutil.copy2(file_path, backup_path)
            print(f"📦 Backed up existing config to: {backup_path}")

        except Exception as e:
            raise BackupError(f"Failed to backup {file_path}: {e}")

    def _write_config(self, output_path: Path, content: str):
        """
        Write configuration content to file.

        Args:
            output_path: Path where config should be written
            content: Configuration content

        Raises:
            ConfigError: If writing fails
        """
        try:
            # Create parent directories if needed
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            output_path.write_text(content, encoding="utf-8")

        except PermissionError:
            raise ConfigError(
                f"Permission denied writing to {output_path}. "
                f"Try running with sudo or write to a different location."
            )
        except Exception as e:
            raise ConfigError(f"Failed to write config to {output_path}: {e}")

    def _get_default_path(self, config_type: str) -> str:
        """
        Get default output path for config type.

        Args:
            config_type: Type of configuration

        Returns:
            Default path for this config type
        """
        default_path = self.DEFAULT_PATHS.get(config_type)
        if not default_path:
            # Fallback to current directory
            extension = self.TEMPLATE_EXTENSIONS[config_type].replace(".template", "")
            default_path = str(self.output_dir / extension)

        # For system paths that require root, write to current directory instead
        # Check if running as root on Unix-like systems
        if default_path.startswith("/etc/"):
            try:
                if os.geteuid() != 0:  # Unix-like systems
                    filename = Path(default_path).name
                    default_path = str(self.output_dir / filename)
            except AttributeError:
                # Windows doesn't have geteuid, write to output_dir
                filename = Path(default_path).name
                default_path = str(self.output_dir / filename)

        return default_path

    def list_templates(self) -> List[str]:
        """
        List available configuration templates.

        Returns:
            List of available config types
        """
        return list(self.TEMPLATE_EXTENSIONS.keys())

    def get_template_info(self, config_type: str) -> Dict[str, Any]:
        """
        Get information about a specific template.

        Args:
            config_type: Type of configuration

        Returns:
            Dictionary with template information

        Raises:
            ConfigError: If config type not found
        """
        if config_type not in self.TEMPLATE_EXTENSIONS:
            raise ConfigError(f"Unknown config type: {config_type}")

        return {
            "type": config_type,
            "template_file": self.TEMPLATE_EXTENSIONS[config_type],
            "default_path": self.DEFAULT_PATHS.get(config_type, "N/A"),
            "validator_available": config_type in ["nginx", "postgres", "redis", "docker-compose", "apache"],
        }

    def restore_backup(self, config_type: str, backup_file: str, output_path: Optional[str] = None):
        """
        Restore a configuration from backup.

        Args:
            config_type: Type of configuration
            backup_file: Name of backup file
            output_path: Custom output path (uses default if not provided)

        Raises:
            BackupError: If restore fails
        """
        try:
            backup_path = self.backup_dir / backup_file
            if not backup_path.exists():
                raise BackupError(f"Backup file not found: {backup_path}")

            if output_path is None:
                output_path = self._get_default_path(config_type)
            
            output_path = Path(output_path)
            shutil.copy2(backup_path, output_path)

            print(f"✅ Restored {config_type} configuration from: {backup_file}")

        except Exception as e:
            raise BackupError(f"Failed to restore backup: {e}")

    def list_backups(self) -> List[str]:
        """
        List all available backup files.

        Returns:
            List of backup file names
        """
        if not self.backup_dir.exists():
            return []

        backups = sorted(
            [f.name for f in self.backup_dir.iterdir() if f.is_file()],
            reverse=True,
        )
        return backups

