"""
Custom exceptions for the configuration system.
"""


class ConfigError(Exception):
    """Base exception for configuration-related errors."""
    pass


class ValidationError(ConfigError):
    """Raised when configuration validation fails."""
    pass


class TemplateError(ConfigError):
    """Raised when template processing fails."""
    pass


class BackupError(ConfigError):
    """Raised when backup operation fails."""
    pass

