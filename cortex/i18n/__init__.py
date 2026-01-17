"""
Internationalization (i18n) module for Cortex Linux CLI.

Provides multi-language support with:
- Message translation with interpolation
- OS language auto-detection
- Language preference persistence
- Locale-aware date/time and number formatting

Usage:
    from cortex.i18n import t, get_translator, set_language, get_language

    # Simple translation
    print(t("install.success"))

    # Translation with variables
    print(t("install.package_installed", package="docker", version="24.0.5"))

    # Change language
    set_language("es")

Supported languages:
    - en: English (default)
    - es: Spanish
    - fr: French
    - de: German
    - zh: Chinese (Simplified)
"""

from cortex.i18n.config import LanguageConfig
from cortex.i18n.detector import detect_os_language
from cortex.i18n.formatter import LocaleFormatter
from cortex.i18n.translator import (
    SUPPORTED_LANGUAGES,
    get_language,
    get_language_info,
    get_supported_languages,
    get_translator,
    set_language,
    t,
)

__all__ = [
    # Core translation
    "t",
    "get_translator",
    "set_language",
    "get_language",
    "get_language_info",
    "get_supported_languages",
    "SUPPORTED_LANGUAGES",
    # Configuration
    "LanguageConfig",
    # Detection
    "detect_os_language",
    # Formatting
    "LocaleFormatter",
]
