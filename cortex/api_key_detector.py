"""Auto-detect API keys from common locations.

This module scans common configuration files and locations to find
API keys for supported LLM providers, making onboarding easier.

Implements Issue #255: Auto-detect API keys from common locations
"""

import os
import re
import logging
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class Provider(Enum):
    """Supported LLM providers."""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


@dataclass
class DetectedKey:
    """Represents a detected API key.

    Attributes:
        provider: The LLM provider (anthropic, openai)
        key: The actual API key value
        source: Where the key was found
        env_var: The environment variable name for this key
    """
    provider: Provider
    key: str
    source: str
    env_var: str

    @property
    def masked_key(self) -> str:
        """Return a masked version of the key for display."""
        if len(self.key) <= 12:
            return "*" * len(self.key)
        return f"{self.key[:8]}...{self.key[-4:]}"


# Patterns to match API keys in files
KEY_PATTERNS = {
    Provider.ANTHROPIC: [
        # Environment variable exports
        r'(?:export\s+)?ANTHROPIC_API_KEY\s*=\s*["\']?(sk-ant-[a-zA-Z0-9_-]+)["\']?',
        # Direct assignment
        r'ANTHROPIC_API_KEY\s*[:=]\s*["\']?(sk-ant-[a-zA-Z0-9_-]+)["\']?',
    ],
    Provider.OPENAI: [
        # Environment variable exports
        r'(?:export\s+)?OPENAI_API_KEY\s*=\s*["\']?(sk-[a-zA-Z0-9_-]+)["\']?',
        # Direct assignment
        r'OPENAI_API_KEY\s*[:=]\s*["\']?(sk-[a-zA-Z0-9_-]+)["\']?',
    ],
}

# Environment variable names for each provider
ENV_VAR_NAMES = {
    Provider.ANTHROPIC: "ANTHROPIC_API_KEY",
    Provider.OPENAI: "OPENAI_API_KEY",
}

# Common locations to search for API keys
SEARCH_LOCATIONS = [
    # Shell configuration files
    "~/.bashrc",
    "~/.bash_profile",
    "~/.zshrc",
    "~/.zprofile",
    "~/.profile",
    # Environment files
    "~/.env",
    "./.env",
    "./.env.local",
    # Config directories
    "~/.config/cortex/.env",
    "~/.config/cortex/config",
    "~/.cortex/.env",
    "~/.cortex/config",
    # Project-specific
    "./cortex.env",
]


class APIKeyDetector:
    """Detects API keys from various sources."""

    def __init__(self, additional_paths: Optional[List[str]] = None):
        """Initialize the detector.

        Args:
            additional_paths: Extra file paths to search
        """
        self.search_paths = [Path(p).expanduser() for p in SEARCH_LOCATIONS]
        if additional_paths:
            self.search_paths.extend([Path(p).expanduser() for p in additional_paths])

    def _extract_key_from_content(
        self,
        content: str,
        provider: Provider
    ) -> Optional[str]:
        """Extract API key from file content.

        Args:
            content: File content to search
            provider: Provider to search for

        Returns:
            API key if found, None otherwise
        """
        for pattern in KEY_PATTERNS[provider]:
            match = re.search(pattern, content, re.MULTILINE)
            if match:
                return match.group(1)
        return None

    def _search_file(self, filepath: Path) -> List[DetectedKey]:
        """Search a single file for API keys.

        Args:
            filepath: Path to the file to search

        Returns:
            List of detected keys
        """
        detected = []

        if not filepath.exists() or not filepath.is_file():
            return detected

        try:
            content = filepath.read_text(encoding='utf-8', errors='ignore')

            for provider in Provider:
                key = self._extract_key_from_content(content, provider)
                if key:
                    detected.append(DetectedKey(
                        provider=provider,
                        key=key,
                        source=str(filepath),
                        env_var=ENV_VAR_NAMES[provider]
                    ))
                    logger.debug(f"Found {provider.value} key in {filepath}")

        except PermissionError:
            logger.debug(f"Permission denied reading {filepath}")
        except Exception as e:
            logger.debug(f"Error reading {filepath}: {e}")

        return detected

    def detect_from_environment(self) -> List[DetectedKey]:
        """Check environment variables for API keys.

        Returns:
            List of detected keys from environment
        """
        detected = []

        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        if anthropic_key and anthropic_key.startswith("sk-ant-"):
            detected.append(DetectedKey(
                provider=Provider.ANTHROPIC,
                key=anthropic_key,
                source="environment variable",
                env_var="ANTHROPIC_API_KEY"
            ))

        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key and openai_key.startswith("sk-"):
            detected.append(DetectedKey(
                provider=Provider.OPENAI,
                key=openai_key,
                source="environment variable",
                env_var="OPENAI_API_KEY"
            ))

        return detected

    def detect_from_files(self) -> List[DetectedKey]:
        """Search all configured paths for API keys.

        Returns:
            List of detected keys from files
        """
        detected = []

        for filepath in self.search_paths:
            found = self._search_file(filepath)
            detected.extend(found)

        return detected

    def detect_all(self) -> List[DetectedKey]:
        """Detect API keys from all sources.

        Checks environment variables first, then files.
        Returns unique keys (same key from multiple sources is deduplicated).

        Returns:
            List of all detected keys
        """
        all_keys = []
        seen_keys = set()

        # Environment variables take priority
        for key in self.detect_from_environment():
            if key.key not in seen_keys:
                all_keys.append(key)
                seen_keys.add(key.key)

        # Then check files
        for key in self.detect_from_files():
            if key.key not in seen_keys:
                all_keys.append(key)
                seen_keys.add(key.key)

        return all_keys

    def get_best_key(self, preferred_provider: Optional[Provider] = None) -> Optional[DetectedKey]:
        """Get the best available API key.

        Args:
            preferred_provider: Preferred provider if multiple keys available

        Returns:
            Best detected key, or None if no keys found
        """
        keys = self.detect_all()

        if not keys:
            return None

        # If preferred provider specified and available, use it
        if preferred_provider:
            for key in keys:
                if key.provider == preferred_provider:
                    return key

        # Default priority: Anthropic > OpenAI (Cortex is optimized for Claude)
        for provider in [Provider.ANTHROPIC, Provider.OPENAI]:
            for key in keys:
                if key.provider == provider:
                    return key

        return keys[0] if keys else None


def auto_configure_api_key(
    preferred_provider: Optional[str] = None,
    set_env: bool = True
) -> Optional[DetectedKey]:
    """Auto-detect and optionally configure an API key.

    This is the main entry point for API key auto-detection.
    It searches common locations and can set the environment variable.

    Args:
        preferred_provider: Preferred provider ('anthropic' or 'openai')
        set_env: Whether to set the environment variable if key is found

    Returns:
        DetectedKey if found, None otherwise

    Example:
        key = auto_configure_api_key()
        if key:
            print(f"Found {key.provider.value} key from {key.source}")
    """
    detector = APIKeyDetector()

    provider = None
    if preferred_provider:
        try:
            provider = Provider(preferred_provider.lower())
        except ValueError:
            logger.warning(f"Unknown provider: {preferred_provider}")

    key = detector.get_best_key(preferred_provider=provider)

    if key and set_env:
        # Set the environment variable for the current process
        os.environ[key.env_var] = key.key
        logger.info(f"Auto-configured {key.env_var} from {key.source}")

    return key


def get_detection_summary() -> Dict[str, any]:
    """Get a summary of API key detection results.

    Returns:
        Dictionary with detection summary for display
    """
    detector = APIKeyDetector()
    keys = detector.detect_all()

    summary = {
        "found": len(keys) > 0,
        "count": len(keys),
        "keys": [],
        "searched_locations": [str(p) for p in detector.search_paths if p.exists()]
    }

    for key in keys:
        summary["keys"].append({
            "provider": key.provider.value,
            "source": key.source,
            "masked_key": key.masked_key,
            "env_var": key.env_var
        })

    return summary


def validate_detected_key(key: DetectedKey) -> Tuple[bool, Optional[str]]:
    """Validate a detected API key format.

    Args:
        key: The detected key to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if key.provider == Provider.ANTHROPIC:
        if not key.key.startswith("sk-ant-"):
            return False, "Anthropic key should start with 'sk-ant-'"
        if len(key.key) < 20:
            return False, "Anthropic key appears too short"

    elif key.provider == Provider.OPENAI:
        if not key.key.startswith("sk-"):
            return False, "OpenAI key should start with 'sk-'"
        if len(key.key) < 20:
            return False, "OpenAI key appears too short"

    return True, None
