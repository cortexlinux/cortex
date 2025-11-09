"""
Validators for different configuration file types.
"""

import re
from typing import Dict, Any, List
from .exceptions import ValidationError


class ConfigValidator:
    """Base class for configuration validators."""

    def validate(self, config: str, params: Dict[str, Any]) -> List[str]:
        """
        Validate configuration content.

        Args:
            config: The generated configuration content
            params: Parameters used to generate the config

        Returns:
            List of validation warnings (empty if valid)

        Raises:
            ValidationError: If validation fails critically
        """
        raise NotImplementedError("Subclasses must implement validate()")


class NginxValidator(ConfigValidator):
    """Validator for nginx configuration files."""

    def validate(self, config: str, params: Dict[str, Any]) -> List[str]:
        warnings = []

        # Check for basic nginx structure
        if "server {" not in config and "http {" not in config:
            raise ValidationError("Invalid nginx config: missing server or http block")

        # Validate listen directive
        if "listen" not in config:
            warnings.append("No listen directive found")

        # Validate server_name if provided
        if params.get("server_name") and "server_name" not in config:
            warnings.append("server_name parameter provided but not in config")

        # Check for SSL if configured
        if params.get("ssl_enabled") and "ssl_certificate" not in config:
            raise ValidationError("SSL enabled but no ssl_certificate directive found")

        # Validate port numbers
        port_matches = re.findall(r'listen\s+(\d+)', config)
        for port in port_matches:
            port_num = int(port)
            if port_num < 1 or port_num > 65535:
                raise ValidationError(f"Invalid port number: {port_num}")

        return warnings


class PostgresValidator(ConfigValidator):
    """Validator for PostgreSQL configuration files."""

    def validate(self, config: str, params: Dict[str, Any]) -> List[str]:
        warnings = []

        # Check for common postgres settings
        critical_settings = ["max_connections", "shared_buffers"]
        found_settings = sum(1 for setting in critical_settings if setting in config)

        if found_settings == 0:
            warnings.append("No common PostgreSQL settings found")

        # Validate port if specified
        if params.get("port"):
            port = params["port"]
            if not (1024 <= port <= 65535):
                raise ValidationError(f"Invalid PostgreSQL port: {port}")

        # Check for memory settings format
        memory_settings = re.findall(r"shared_buffers\s*=\s*'?(\d+\w+)'?", config)
        for setting in memory_settings:
            if not re.match(r'\d+(MB|GB|kB)', setting):
                warnings.append(f"Unusual memory format: {setting}")

        return warnings


class RedisValidator(ConfigValidator):
    """Validator for Redis configuration files."""

    def validate(self, config: str, params: Dict[str, Any]) -> List[str]:
        warnings = []

        # Check for basic redis directives
        if "bind" not in config and "port" not in config:
            warnings.append("Neither bind nor port directive found")

        # Validate port
        port_match = re.search(r'port\s+(\d+)', config)
        if port_match:
            port = int(port_match.group(1))
            if port < 1 or port > 65535:
                raise ValidationError(f"Invalid Redis port: {port}")

        # Check for persistence settings
        if params.get("persistence") and "save" not in config and "appendonly" not in config:
            warnings.append("Persistence enabled but no save or appendonly directive found")

        # Validate maxmemory format if present
        maxmem_match = re.search(r'maxmemory\s+(\S+)', config)
        if maxmem_match:
            maxmem = maxmem_match.group(1)
            if not re.match(r'\d+(kb|mb|gb)?$', maxmem, re.IGNORECASE):
                raise ValidationError(f"Invalid maxmemory format: {maxmem}")

        return warnings


class DockerComposeValidator(ConfigValidator):
    """Validator for Docker Compose files."""

    def validate(self, config: str, params: Dict[str, Any]) -> List[str]:
        warnings = []

        # Check for version
        if "version:" not in config:
            warnings.append("No version specified (recommended for compatibility)")

        # Check for services
        if "services:" not in config:
            raise ValidationError("Invalid docker-compose: no services defined")

        # Validate version format
        version_match = re.search(r"version:\s*['\"]?(\d+(?:\.\d+)?)['\"]?", config)
        if version_match:
            version = float(version_match.group(1))
            if version < 2.0 or version > 3.9:
                warnings.append(f"Unusual docker-compose version: {version}")

        # Check for networks if multiple services
        service_count = config.count("    image:") + config.count("    build:")
        if service_count > 1 and "networks:" not in config:
            warnings.append("Multiple services but no networks defined")

        # Validate image format
        image_matches = re.findall(r'image:\s*(\S+)', config)
        for image in image_matches:
            if not re.match(r'^[\w\-\.\/]+:?[\w\.\-]*$', image):
                warnings.append(f"Unusual image format: {image}")

        return warnings


class ApacheValidator(ConfigValidator):
    """Validator for Apache configuration files."""

    def validate(self, config: str, params: Dict[str, Any]) -> List[str]:
        warnings = []

        # Check for VirtualHost
        if "<VirtualHost" not in config:
            warnings.append("No VirtualHost directive found")

        # Check for DocumentRoot (required for static sites, not for reverse proxy)
        if not params.get("reverse_proxy") and "DocumentRoot" not in config:
            raise ValidationError("Invalid Apache config: missing DocumentRoot")

        # Validate Listen directive
        listen_matches = re.findall(r'Listen\s+(?:\d+\.\d+\.\d+\.\d+:)?(\d+)', config)
        for port in listen_matches:
            port_num = int(port)
            if port_num < 1 or port_num > 65535:
                raise ValidationError(f"Invalid port number: {port_num}")

        # Check for SSL configuration
        if params.get("ssl_enabled"):
            ssl_directives = ["SSLEngine", "SSLCertificateFile", "SSLCertificateKeyFile"]
            missing = [d for d in ssl_directives if d not in config]
            if missing:
                raise ValidationError(f"SSL enabled but missing directives: {', '.join(missing)}")

        return warnings


# Validator registry
VALIDATORS = {
    "nginx": NginxValidator(),
    "postgres": PostgresValidator(),
    "redis": RedisValidator(),
    "docker-compose": DockerComposeValidator(),
    "apache": ApacheValidator(),
}


def get_validator(config_type: str) -> ConfigValidator:
    """Get validator for a specific config type."""
    validator = VALIDATORS.get(config_type)
    if not validator:
        raise ValueError(f"No validator found for config type: {config_type}")
    return validator

