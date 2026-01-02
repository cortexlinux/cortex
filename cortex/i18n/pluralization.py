"""
Pluralization Rules for Cortex Linux i18n

Implements language-specific pluralization rules following CLDR standards.
Supports different plural forms for languages with varying pluralization patterns.

Author: Cortex Linux Team
License: Apache 2.0
"""

from collections.abc import Callable


def _arabic_plural_rule(n: int) -> str:
    """
    Arabic pluralization rule (6 plural forms per CLDR standard).

    Arabic has distinct plural forms for:
    - zero (0)
    - one (1)
    - two (2)
    - few (3-10)
    - many (11-99)
    - other (100+)

    Args:
        n: Count to pluralize

    Returns:
        Plural form key
    """
    if n == 0:
        return "zero"
    elif n == 1:
        return "one"
    elif n == 2:
        return "two"
    elif 3 <= n <= 10:
        return "few"
    elif 11 <= n <= 99:
        return "many"
    else:
        return "other"


class PluralRules:
    """
    Defines pluralization rules for different languages.

    Different languages have different numbers of plural forms:

    - English: one vs. other
      Examples: 1 package, 2 packages

    - Spanish: one vs. other
      Examples: 1 paquete, 2 paquetes

    - Russian: one, few, many
      Examples: 1, 2-4, 5+

    - Arabic: zero, one, two, few, many, other
      Examples: 0, 1, 2, 3-10, 11-99, 100+

    - Japanese: No plural distinction (all use 'other')

    - Hindi: one vs. other
      Examples: 1 pैकेज, 2 pैकेज
    """

    RULES: dict[str, Callable[[int], str]] = {
        "en": lambda n: "one" if n == 1 else "other",
        "es": lambda n: "one" if n == 1 else "other",
        "fr": lambda n: "one" if n <= 1 else "other",
        "ja": lambda n: "other",  # Japanese doesn't distinguish
        "ar": _arabic_plural_rule,
        "hi": lambda n: "one" if n == 1 else "other",
        "pt": lambda n: "one" if n == 1 else "other",
    }

    @classmethod
    def get_plural_form(cls, language: str, count: int) -> str:
        """
        Get plural form key for language and count.

        Args:
            language: Language code (e.g., 'en', 'es', 'ar')
            count: Numeric count for pluralization

        Returns:
            Plural form key ('one', 'few', 'many', 'other', etc.)

        Example:
            >>> PluralRules.get_plural_form('en', 1)
            'one'
            >>> PluralRules.get_plural_form('en', 5)
            'other'
            >>> PluralRules.get_plural_form('ar', 0)
            'zero'
        """
        # Default to English rules if language not found
        rule = cls.RULES.get(language, cls.RULES["en"])
        return rule(count)

    @classmethod
    def supports_language(cls, language: str) -> bool:
        """
        Check if pluralization rules exist for a language.

        Args:
            language: Language code

        Returns:
            True if language has defined rules
        """
        return language in cls.RULES


# Common pluralization patterns for reference

ENGLISH_RULES = {
    "plural_forms": 2,
    "forms": ["one", "other"],
    "examples": {
        1: "one",
        2: "other",
        5: "other",
        100: "other",
    },
}

SPANISH_RULES = {
    "plural_forms": 2,
    "forms": ["one", "other"],
    "examples": {
        1: "one",
        2: "other",
        100: "other",
    },
}

RUSSIAN_RULES = {
    "plural_forms": 3,
    "forms": ["one", "few", "many"],
    "examples": {
        1: "one",
        2: "few",
        5: "many",
        21: "one",
        102: "many",
    },
}

ARABIC_RULES = {
    "plural_forms": 6,
    "forms": ["zero", "one", "two", "few", "many", "other"],
    "examples": {
        0: "zero",
        1: "one",
        2: "two",
        5: "few",
        100: "many",
        1000: "other",
    },
}

JAPANESE_RULES = {
    "plural_forms": 1,
    "forms": ["other"],
    "examples": {
        1: "other",
        2: "other",
        100: "other",
    },
}

HINDI_RULES = {
    "plural_forms": 2,
    "forms": ["one", "other"],
    "examples": {
        1: "one",
        2: "other",
        100: "other",
    },
}
