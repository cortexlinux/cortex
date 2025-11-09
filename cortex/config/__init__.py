"""
Configuration File Template System
===================================

Generate common configuration files from templates with validation and backup support.

Supported configuration types:
- nginx: Web server and reverse proxy configurations
- postgres: PostgreSQL database configurations
- redis: Redis cache server configurations
- docker-compose: Docker Compose orchestration files
- apache: Apache web server configurations
"""

from .generator import ConfigGenerator
from .exceptions import (
    ConfigError,
    ValidationError,
    TemplateError,
    BackupError,
)

__all__ = [
    "ConfigGenerator",
    "ConfigError",
    "ValidationError",
    "TemplateError",
    "BackupError",
]

