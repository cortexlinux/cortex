"""
Configuration management for Intelligent Tutor.

Handles API keys, settings, and environment variables securely.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

# Load environment variables from .env file
load_dotenv()

# Default settings (named constants with clear purpose)
DEFAULT_TUTOR_TOPICS_COUNT = 5  # Default topic count when actual count unavailable
DEFAULT_MODEL_NAME = "claude-sonnet-4-20250514"
DEFAULT_CACHE_TTL_HOURS = 24


class Config(BaseModel):
    """
    Configuration settings for Intelligent Tutor.

    Attributes:
        anthropic_api_key: Anthropic API key for Claude access.
        openai_api_key: Optional OpenAI API key for fallback.
        data_dir: Directory for storing tutor data.
        debug: Enable debug mode for verbose logging.
        model_name: LLM model name to use.
        cache_ttl_hours: Cache time-to-live in hours.
    """

    anthropic_api_key: str | None = Field(
        default=None, description="Anthropic API key for Claude access"
    )
    openai_api_key: str | None = Field(
        default=None, description="Optional OpenAI API key for fallback"
    )
    data_dir: Path = Field(
        default=Path.home() / ".cortex", description="Directory for storing tutor data"
    )
    debug: bool = Field(default=False, description="Enable debug mode for verbose logging")
    db_path: Path | None = Field(default=None, description="Path to SQLite database")
    model_name: str = Field(default=DEFAULT_MODEL_NAME, description="LLM model name to use")
    cache_ttl_hours: int = Field(
        default=DEFAULT_CACHE_TTL_HOURS, description="Cache time-to-live in hours"
    )

    def model_post_init(self, __context) -> None:
        """Initialize computed fields after model creation."""
        if self.db_path is None:
            self.db_path = self.data_dir / "tutor_progress.db"

    @field_validator("data_dir", mode="before")
    @classmethod
    def expand_data_dir(cls, v: str | Path) -> Path:
        """Expand user home directory in path."""
        if isinstance(v, str):
            return Path(v).expanduser()
        return v.expanduser()

    @classmethod
    def from_env(cls, require_api_key: bool = True) -> "Config":
        """
        Create configuration from environment variables.

        Args:
            require_api_key: If True, raises error when API key missing.

        Returns:
            Config: Configuration instance with values from environment.

        Raises:
            ValueError: If required API key is not set and require_api_key=True.
        """
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key and require_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable is required. "
                "Set it in your environment or create a .env file."
            )

        data_dir_str = os.getenv("TUTOR_DATA_DIR", str(Path.home() / ".cortex"))
        data_dir = Path(data_dir_str).expanduser()

        cache_ttl_str = os.getenv("TUTOR_CACHE_TTL_HOURS", str(DEFAULT_CACHE_TTL_HOURS))
        try:
            cache_ttl = int(cache_ttl_str)
        except ValueError:
            cache_ttl = DEFAULT_CACHE_TTL_HOURS

        return cls(
            anthropic_api_key=api_key,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            data_dir=data_dir,
            debug=os.getenv("TUTOR_DEBUG", "false").lower() == "true",
            model_name=os.getenv("TUTOR_MODEL_NAME", DEFAULT_MODEL_NAME),
            cache_ttl_hours=cache_ttl,
        )

    def ensure_data_dir(self) -> None:
        """
        Ensure the data directory exists with proper permissions.

        Creates the directory if it doesn't exist with 0o700 permissions
        for security (owner read/write/execute only).
        """
        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, mode=0o700)

    def get_db_path(self) -> Path:
        """
        Get the full path to the SQLite database.

        Returns:
            Path: Full path to tutor_progress.db
        """
        self.ensure_data_dir()
        return self.db_path

    def validate_api_key(self) -> bool:
        """
        Validate that the API key is properly configured.

        Returns:
            bool: True if API key is valid format, False otherwise.
        """
        if not self.anthropic_api_key:
            return False
        # Anthropic API keys start with 'sk-ant-'
        return self.anthropic_api_key.startswith("sk-ant-")


# Global configuration instance (lazy loaded)
_config: Config | None = None


def get_config() -> Config:
    """
    Get the global configuration instance.

    Returns:
        Config: Global configuration singleton.

    Raises:
        ValueError: If configuration cannot be loaded.
    """
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def reset_config() -> None:
    """Reset the global configuration (useful for testing)."""
    global _config
    _config = None
