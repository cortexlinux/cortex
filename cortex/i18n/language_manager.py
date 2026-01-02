"""
Language Manager for Cortex Linux i18n

Handles language detection and switching with priority-based fallback.
Supports CLI arguments, environment variables, config files, and system locale.

Author: Cortex Linux Team
License: Apache 2.0
"""

import locale
import logging
import os

logger = logging.getLogger(__name__)


class LanguageManager:
    """
    Detects and manages language preferences.

    Detection Priority Order:
    1. CLI argument (--language/-L)
    2. Environment variable (CORTEX_LANGUAGE)
    3. Config file preference
    4. System locale
    5. Fallback to English

    Example:
        >>> manager = LanguageManager(prefs_manager)
        >>> lang = manager.detect_language(cli_arg='es')
        >>> print(lang)
        'es'
    """

    # Supported languages with display names
    SUPPORTED_LANGUAGES: dict[str, str] = {
        "en": "English",
        "es": "Español",
        "hi": "हिन्दी",
        "ja": "日本語",
        "ar": "العربية",
        "pt": "Português",
        "fr": "Français",
        "de": "Deutsch",
        "it": "Italiano",
        "ru": "Русский",
        "zh": "中文",
        "ko": "한국어",
    }

    # Map system locale codes to cortex language codes
    LOCALE_MAPPING: dict[str, str] = {
        "en": "en",
        "en_US": "en",
        "en_GB": "en",
        "es": "es",
        "es_ES": "es",
        "es_MX": "es",
        "es_AR": "es",
        "hi": "hi",
        "hi_IN": "hi",
        "ja": "ja",
        "ja_JP": "ja",
        "ar": "ar",
        "ar_SA": "ar",
        "ar_AE": "ar",
        "pt": "pt",
        "pt_BR": "pt",
        "pt_PT": "pt",
        "fr": "fr",
        "fr_FR": "fr",
        "fr_CA": "fr",
        "de": "de",
        "de_DE": "de",
        "de_AT": "de",
        "de_CH": "de",
        "it": "it",
        "it_IT": "it",
        "ru": "ru",
        "ru_RU": "ru",
        "zh": "zh",
        "zh_CN": "zh",
        "zh_SG": "zh",
        "ko": "ko",
        "ko_KR": "ko",
    }

    def __init__(self, prefs_manager=None):
        """
        Initialize language manager.

        Args:
            prefs_manager: PreferencesManager instance for config access
        """
        self.prefs_manager = prefs_manager

    def detect_language(self, cli_arg: str | None = None) -> str:
        """
        Detect language with priority fallback chain.

        Priority:
        1. CLI argument (--language or -L flag)
        2. CORTEX_LANGUAGE environment variable
        3. Preferences file (~/.cortex/preferences.yaml)
        4. System locale settings
        5. English fallback

        Args:
            cli_arg: Language code from CLI argument (highest priority)

        Returns:
            Validated language code
        """
        # Priority 1: CLI argument
        if cli_arg and self.is_supported(cli_arg):
            logger.debug(f"Using CLI language: {cli_arg}")
            return cli_arg
        elif cli_arg:
            logger.warning(f"Language '{cli_arg}' not supported. Falling back to detection.")

        # Priority 2: Environment variable
        env_lang = os.environ.get("CORTEX_LANGUAGE", "").strip().lower()
        if env_lang and self.is_supported(env_lang):
            logger.debug(f"Using CORTEX_LANGUAGE env var: {env_lang}")
            return env_lang
        elif env_lang:
            logger.warning(f"Language '{env_lang}' in CORTEX_LANGUAGE not supported.")

        # Priority 3: Config file preference
        if self.prefs_manager:
            try:
                prefs = self.prefs_manager.load()
                config_lang = getattr(prefs, "language", "").strip().lower()
                if config_lang and self.is_supported(config_lang):
                    logger.debug(f"Using config file language: {config_lang}")
                    return config_lang
            except Exception as e:
                logger.debug(f"Could not read config language: {e}")

        # Priority 4: System locale
        sys_lang = self.get_system_language()
        if sys_lang and self.is_supported(sys_lang):
            logger.debug(f"Using system language: {sys_lang}")
            return sys_lang

        # Priority 5: English fallback
        logger.debug("Falling back to English")
        return "en"

    def get_system_language(self) -> str | None:
        """
        Extract language from system locale settings.

        Returns:
            Language code if detected, None otherwise
        """
        try:
            # Get system locale
            system_locale, _ = locale.getdefaultlocale()

            if not system_locale:
                logger.debug("Could not determine system locale")
                return None

            # Normalize locale (e.g., 'en_US' -> 'en', 'en_US.UTF-8' -> 'en')
            base_locale = system_locale.split(".")[0]  # Remove encoding
            base_locale = base_locale.replace("-", "_")  # Normalize separator

            # Look up in mapping
            if base_locale in self.LOCALE_MAPPING:
                return self.LOCALE_MAPPING[base_locale]

            # Try just the language part
            lang_code = base_locale.split("_")[0].lower()
            if lang_code in self.LOCALE_MAPPING:
                return self.LOCALE_MAPPING[lang_code]

            if lang_code in self.SUPPORTED_LANGUAGES:
                return lang_code

            logger.debug(f"System locale '{system_locale}' not mapped")
            return None

        except Exception as e:
            logger.debug(f"Error detecting system language: {e}")
            return None

    def is_supported(self, language: str) -> bool:
        """
        Check if language is supported.

        Args:
            language: Language code

        Returns:
            True if language is in SUPPORTED_LANGUAGES
        """
        return language.lower() in self.SUPPORTED_LANGUAGES

    def get_available_languages(self) -> dict[str, str]:
        """
        Get all supported languages.

        Returns:
            Dict of language codes to display names
        """
        return self.SUPPORTED_LANGUAGES.copy()

    def get_language_name(self, language: str) -> str:
        """
        Get display name for a language.

        Args:
            language: Language code

        Returns:
            Display name (e.g., 'Español' for 'es')
        """
        return self.SUPPORTED_LANGUAGES.get(language.lower(), language)

    def format_language_list(self) -> str:
        """
        Format language list as human-readable string.

        Returns:
            Formatted string like "English, Español, हिन्दी, 日本語"
        """
        names = [self.SUPPORTED_LANGUAGES[code] for code in sorted(self.SUPPORTED_LANGUAGES)]
        return ", ".join(names)
