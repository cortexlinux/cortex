"""
Core i18n (Internationalization) Module for Cortex Linux

Provides translation, language management, pluralization, and formatting
for multi-language CLI support.

Author: Cortex Linux Team
License: Apache 2.0
"""

import json
import locale
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class Translator:
    """
    Main translator class providing message translation and formatting.

    Features:
    - Lazy loading of translation catalogs
    - Nested key access (e.g., 'install.success')
    - Variable interpolation with {key} syntax
    - Pluralization support via pluralization rules
    - RTL language detection
    - Graceful fallback to English

    Example:
        translator = Translator('es')
        msg = translator.get('install.success', package='nginx')
        # Returns: "nginx instalado exitosamente"
    """

    # Right-to-left languages
    RTL_LANGUAGES = {"ar", "he", "ur", "yi", "fa", "ps", "sd"}

    def __init__(self, language: str = "en"):
        """
        Initialize translator.

        Args:
            language: Language code (e.g., 'en', 'es', 'hi', 'ja', 'ar')
        """
        self.language = language
        self._catalogs: dict[str, dict[str, Any]] = {}
        self._default_language = "en"
        self._translations_dir = Path(__file__).parent.parent / "translations"

    def get(self, key: str, **kwargs) -> str:
        """
        Get translated message with variable interpolation.

        Args:
            key: Dot-separated key path (e.g., 'install.success')
            **kwargs: Variables for interpolation (e.g., package='nginx')

        Returns:
            Translated and formatted message. Falls back to English if not found.
            If all lookups fail, returns a bracketed key placeholder.

        Example:
            >>> translator = Translator('es')
            >>> translator.get('install.success', package='nginx')
            'nginx instalado exitosamente'
        """
        message = self._lookup_message(key)

        if message is None:
            # Fallback chain: try default language
            if self.language != self._default_language:
                message = self._lookup_message(key, language=self._default_language)

            # Last resort: return placeholder
            if message is None:
                logger.warning(f"Translation missing: {key} ({self.language})")
                return f"[{key}]"

        # Interpolate variables
        return self._interpolate(message, **kwargs)

    def get_plural(self, key: str, count: int, **kwargs) -> str:
        """
        Get pluralized translation.

        Handles pluralization based on language-specific rules.
        Expects message in format: "text {variable, plural, one {singular} other {plural}}"

        Args:
            key: Translation key with plural form
            count: Number for pluralization decision
            **kwargs: Additional format variables

        Returns:
            Correctly pluralized message

        Example:
            >>> translator.get_plural('install.downloading', 5, package_count=5)
            'Descargando 5 paquetes'
        """
        message = self.get(key, **kwargs)

        # Parse plural form if present
        if "{" in message and "plural" in message:
            return self._parse_pluralization(message, count, self.language)

        return message

    def is_rtl(self) -> bool:
        """
        Check if current language is right-to-left.

        Returns:
            True if language is RTL (e.g., Arabic, Hebrew)
        """
        return self.language in self.RTL_LANGUAGES

    def set_language(self, language: str) -> bool:
        """
        Switch to different language.

        Args:
            language: Language code

        Returns:
            True if language loaded successfully, False otherwise
        """
        translation_file = self._translations_dir / f"{language}.json"

        if not translation_file.exists():
            logger.warning(f"Language '{language}' not found, using English")
            self.language = self._default_language
            return False

        try:
            self._load_catalog(language)
            self.language = language
            return True
        except Exception as e:
            logger.error(f"Failed to load language '{language}': {e}")
            self.language = self._default_language
            return False

    def _lookup_message(self, key: str, language: str | None = None) -> str | None:
        """
        Look up a message in the translation catalog.

        Args:
            key: Dot-separated key path
            language: Language to look up (defaults to current language)

        Returns:
            Message if found, None otherwise
        """
        lang = language or self.language

        # Load catalog if not already loaded
        if lang not in self._catalogs:
            try:
                self._load_catalog(lang)
            except Exception as e:
                logger.debug(f"Failed to load catalog for '{lang}': {e}")
                return None

        catalog = self._catalogs.get(lang, {})

        # Navigate nested keys (e.g., 'install.success' -> catalog['install']['success'])
        parts = key.split(".")
        current: dict[str, Any] | str | None = catalog

        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None

        return current if isinstance(current, str) else None

    def _load_catalog(self, language: str) -> None:
        """
        Load translation catalog from JSON file.

        Args:
            language: Language code

        Raises:
            FileNotFoundError: If translation file doesn't exist
            json.JSONDecodeError: If JSON is invalid
        """
        catalog_file = self._translations_dir / f"{language}.json"

        if not catalog_file.exists():
            raise FileNotFoundError(f"Translation file not found: {catalog_file}")

        try:
            with open(catalog_file, encoding="utf-8") as f:
                catalog = json.load(f)
                self._catalogs[language] = catalog
                logger.debug(f"Loaded catalog for language: {language}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {catalog_file}: {e}")
            raise

    def _interpolate(self, text: str, **kwargs) -> str:
        """
        Replace {key} placeholders with values from kwargs.

        Args:
            text: Text with {key} placeholders
            **kwargs: Replacement values

        Returns:
            Interpolated text
        """
        if not kwargs:
            return text

        result = text
        for key, value in kwargs.items():
            placeholder = f"{{{key}}}"
            result = result.replace(placeholder, str(value))

        return result

    def _parse_pluralization(self, message: str, count: int, language: str) -> str:
        """
        Parse and apply pluralization rules to message.

        Expected format: "text {variable, plural, one {singular} other {plural}}"

        Args:
            message: Message with pluralization syntax
            count: Count to determine singular/plural
            language: Language for pluralization rules

        Returns:
            Message with appropriate plural form applied
        """
        if "plural" not in message or "{" not in message:
            return message

        try:
            # Find the outermost plural pattern
            # Pattern: {variable, plural, one {...} other {...}}

            # Find all braces and match them
            parts: list[str] = []
            brace_count = 0
            plural_start = -1

            for i, char in enumerate(message):
                if char == "{":
                    if brace_count == 0 and i < len(message) - 10:
                        # Check if this might be a plural block
                        snippet = message[i : i + 30]
                        if "plural" in snippet:
                            plural_start = i
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0 and plural_start >= 0:
                        # Found matching closing brace
                        plural_block = message[plural_start + 1 : i]

                        # Check for one and other
                        if "one" in plural_block and "other" in plural_block:
                            # Extract the selected form
                            if count == 1:
                                # Extract 'one' form: one {text}
                                one_idx = plural_block.find("one")
                                one_brace = plural_block.find("{", one_idx)
                                one_close = plural_block.find("}", one_brace)
                                if one_brace >= 0 and one_close >= 0:
                                    one_text = plural_block[one_brace + 1 : one_close]
                                    result = one_text.replace("#", str(count)).strip()
                                    return message[:plural_start] + result + message[i + 1 :]
                            else:
                                # Extract 'other' form: other {text}
                                other_idx = plural_block.find("other")
                                other_brace = plural_block.find("{", other_idx)
                                other_close = plural_block.find("}", other_brace)
                                if other_brace >= 0 and other_close >= 0:
                                    other_text = plural_block[other_brace + 1 : other_close]
                                    result = other_text.replace("#", str(count)).strip()
                                    return message[:plural_start] + result + message[i + 1 :]

                        plural_start = -1

        except Exception as e:
            logger.debug(f"Error parsing pluralization: {e}")

        return message

        return message


# Singleton instance for convenience
_default_translator: Translator | None = None


def get_translator(language: str = "en") -> Translator:
    """
    Get or create a translator instance.

    Args:
        language: Language code

    Returns:
        Translator instance
    """
    global _default_translator
    if _default_translator is None:
        _default_translator = Translator(language)
    elif language != _default_translator.language:
        _default_translator.set_language(language)

    return _default_translator


def translate(key: str, language: str = "en", **kwargs) -> str:
    """
    Convenience function to translate a message without creating translator.

    Args:
        key: Translation key
        language: Language code
        **kwargs: Format variables

    Returns:
        Translated message
    """
    translator = get_translator(language)
    return translator.get(key, **kwargs)
