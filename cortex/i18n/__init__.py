"""
I18N Module Initialization

Provides convenient access to i18n components for the rest of Cortex.

Author: Cortex Linux Team
License: Apache 2.0
"""

from cortex.i18n.fallback_handler import FallbackHandler, get_fallback_handler
from cortex.i18n.language_manager import LanguageManager
from cortex.i18n.pluralization import PluralRules
from cortex.i18n.translator import Translator, get_translator, translate

__all__ = [
    "Translator",
    "LanguageManager",
    "PluralRules",
    "FallbackHandler",
    "get_translator",
    "get_fallback_handler",
    "translate",
]

__version__ = "0.1.0"
