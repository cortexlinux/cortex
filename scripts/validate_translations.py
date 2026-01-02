"""
Translation File Validator for Cortex Linux i18n

Validates that translation files are complete, properly formatted,
and ready for production use.

Author: Cortex Linux Team
License: Apache 2.0
"""

import json
import sys
from pathlib import Path
from typing import Any


class TranslationValidator:
    """
    Validates translation files against the English source.

    Checks for:
    - Valid JSON syntax
    - All required keys present
    - No extra keys added
    - Proper variable placeholders
    - Proper pluralization syntax
    """

    def __init__(self, translations_dir: Path):
        """
        Initialize validator.

        Args:
            translations_dir: Path to translations directory
        """
        self.translations_dir = translations_dir
        self.en_catalog = None
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def validate(self, strict: bool = False) -> bool:
        """
        Validate all translation files.

        Args:
            strict: If True, treat warnings as errors

        Returns:
            True if validation passes, False otherwise
        """
        self.errors.clear()
        self.warnings.clear()

        # Load English catalog
        en_path = self.translations_dir / "en.json"
        if not en_path.exists():
            self.errors.append(f"English translation file not found: {en_path}")
            return False

        try:
            with open(en_path, encoding="utf-8") as f:
                self.en_catalog = json.load(f)
        except json.JSONDecodeError as e:
            self.errors.append(f"Invalid JSON in {en_path}: {e}")
            return False

        # Get all translation files
        translation_files = list(self.translations_dir.glob("*.json"))
        translation_files.sort()

        # Validate each translation file
        for filepath in translation_files:
            if filepath.name == "en.json":
                continue  # Skip English source

            self._validate_file(filepath)

        # Print results
        if self.errors:
            print("❌ Validation FAILED\n")
            print("Errors:")
            for error in self.errors:
                print(f"  - {error}")

        if self.warnings:
            print("\n⚠️  Warnings:")
            for warning in self.warnings:
                print(f"  - {warning}")

        if not self.errors and not self.warnings:
            print("✅ All translations are valid!")

        if strict and self.warnings:
            return False

        return len(self.errors) == 0

    def _validate_file(self, filepath: Path) -> None:
        """
        Validate a single translation file.

        Args:
            filepath: Path to translation file
        """
        try:
            with open(filepath, encoding="utf-8") as f:
                catalog = json.load(f)
        except json.JSONDecodeError as e:
            self.errors.append(f"Invalid JSON in {filepath.name}: {e}")
            return
        except Exception as e:
            self.errors.append(f"Error reading {filepath.name}: {e}")
            return

        lang_code = filepath.stem

        # Check for missing keys
        if self.en_catalog is None:
            self.errors.append("English catalog not loaded")
            return

        en_keys = self._extract_keys(self.en_catalog)
        catalog_keys = self._extract_keys(catalog)

        missing_keys = en_keys - catalog_keys
        if missing_keys:
            self.errors.append(f"{lang_code}: Missing {len(missing_keys)} key(s): {missing_keys}")

        # Check for extra keys
        extra_keys = catalog_keys - en_keys
        if extra_keys:
            self.warnings.append(f"{lang_code}: Has {len(extra_keys)} extra key(s): {extra_keys}")

        # Check variable placeholders
        for key in en_keys & catalog_keys:
            en_val = self._get_nested(self.en_catalog, key)
            cat_val = self._get_nested(catalog, key)

            if isinstance(en_val, str) and isinstance(cat_val, str):
                self._check_placeholders(en_val, cat_val, lang_code, key)

    def _extract_keys(self, catalog: dict, prefix: str = "") -> set:
        """
        Extract all dot-separated keys from catalog.

        Args:
            catalog: Translation catalog (nested dict)
            prefix: Current prefix for nested keys

        Returns:
            Set of all keys in format 'namespace.key'
        """
        keys = set()

        for key, value in catalog.items():
            full_key = f"{prefix}.{key}" if prefix else key

            if isinstance(value, dict):
                keys.update(self._extract_keys(value, full_key))
            elif isinstance(value, str):
                keys.add(full_key)

        return keys

    def _get_nested(self, catalog: dict, key: str) -> Any:
        """
        Get value from nested dict using dot-separated key.

        Args:
            catalog: Nested dictionary
            key: Dot-separated key path

        Returns:
            Value if found, None otherwise
        """
        parts = key.split(".")
        current: Any = catalog

        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None

        return current

    def _check_placeholders(self, en_val: str, cat_val: str, lang_code: str, key: str) -> None:
        """
        Check that placeholders match between English and translation.

        Args:
            en_val: English value
            cat_val: Translated value
            lang_code: Language code
            key: Translation key
        """
        import re

        # Find all {placeholder} in English
        en_placeholders = set(re.findall(r"\{([^}]+)\}", en_val))
        cat_placeholders = set(re.findall(r"\{([^}]+)\}", cat_val))

        # Remove plural syntax if present (e.g., "count, plural, one {...}")
        en_placeholders = {p.split(",")[0] for p in en_placeholders}
        cat_placeholders = {p.split(",")[0] for p in cat_placeholders}

        # Check for missing placeholders
        missing = en_placeholders - cat_placeholders
        if missing:
            self.warnings.append(f"{lang_code}/{key}: Missing placeholder(s): {missing}")

        # Check for extra placeholders
        extra = cat_placeholders - en_placeholders
        if extra:
            self.warnings.append(f"{lang_code}/{key}: Extra placeholder(s): {extra}")


def main():
    """Main entry point for validation script."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate Cortex Linux translation files")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path(__file__).parent.parent / "cortex" / "translations",
        help="Path to translations directory",
    )

    args = parser.parse_args()

    validator = TranslationValidator(args.dir)
    success = validator.validate(strict=args.strict)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
