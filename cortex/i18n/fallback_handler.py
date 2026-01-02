"""
Fallback Handler for Cortex Linux i18n

Manages graceful fallback behavior when translations are missing.
Logs warnings and tracks missing keys for translation completion.

Author: Cortex Linux Team
License: Apache 2.0
"""

import csv
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class FallbackHandler:
    """
    Manages fallback behavior when translations are missing.

    Fallback Strategy:
    1. Return translated message in target language if available
    2. Fall back to English translation if target language unavailable
    3. Generate placeholder message using key name
    4. Log warning for missing translations
    5. Track missing keys for reporting

    Example:
        >>> handler = FallbackHandler()
        >>> result = handler.handle_missing('install.new_key', 'es')
        >>> print(result)
        '[install.new_key]'
        >>> handler.get_missing_translations()
        {'install.new_key'}
    """

    def __init__(self, logger=None):
        """
        Initialize fallback handler.

        Args:
            logger: Logger instance for warnings (uses module logger if None)
        """
        self.logger = logger or globals()["logger"]
        self.missing_keys: set[str] = set()
        self._session_start = datetime.now()

    def handle_missing(self, key: str, language: str) -> str:
        """
        Handle missing translation gracefully.

        When a translation key is not found, this returns a fallback
        and logs a warning for the development team.

        Args:
            key: Translation key that was not found (e.g., 'install.success')
            language: Target language that was missing the key (e.g., 'es')

        Returns:
            Fallback message: placeholder like '[install.success]'
        """
        # Track this missing key
        self.missing_keys.add(key)

        # Log warning
        self.logger.warning(f"Missing translation: {key} (language: {language})")

        # Return placeholder
        return f"[{key}]"

    def get_missing_translations(self) -> set[str]:
        """
        Get all missing translation keys encountered.

        Returns:
            Set of missing translation keys
        """
        return self.missing_keys.copy()

    def has_missing_translations(self) -> bool:
        """
        Check if any translations were missing.

        Returns:
            True if missing_keys is not empty
        """
        return len(self.missing_keys) > 0

    def missing_count(self) -> int:
        """
        Get count of missing translations.

        Returns:
            Number of unique missing keys
        """
        return len(self.missing_keys)

    def export_missing_for_translation(self, output_path: Path | None = None) -> str:
        """
        Export missing translations as CSV for translator team.

        Creates a CSV file with columns: key, namespace, suggested_placeholder
        This helps translator teams quickly identify gaps in translations.

        Args:
            output_path: Path to write CSV (uses secure user temp dir if None)

        Returns:
            CSV content as string

        Example:
            >>> handler.export_missing_for_translation()
            '''
            key,namespace
            install.new_command,install
            config.new_option,config
            '''
        """
        if output_path is None:
            # Use secure user-specific temporary directory
            # This avoids /tmp which is world-writable (security vulnerability)
            # Use cross-platform approach for username
            try:
                username = os.getlogin()
            except (OSError, AttributeError):
                # Fallback if getlogin() fails or on systems without os.getlogin()
                username = os.environ.get("USERNAME") or os.environ.get("USER") or "cortex_user"

            temp_dir = Path(tempfile.gettempdir()) / f"cortex_{username}"
            temp_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

            filename = f"cortex_missing_translations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            output_path = temp_dir / filename

        # Build CSV content
        csv_lines = ["key,namespace"]

        for key in sorted(self.missing_keys):
            # Extract namespace from key (e.g., 'install.success' -> 'install')
            parts = key.split(".")
            namespace = parts[0] if len(parts) > 0 else "unknown"
            csv_lines.append(f'"{key}","{namespace}"')

        csv_content = "\n".join(csv_lines)

        # Write to file with secure permissions
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

            # Create file with secure permissions (owner read/write only)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(csv_content)

            # Explicitly set file permissions to 0o600 (owner read/write only)
            os.chmod(output_path, 0o600)

            self.logger.info(f"Exported missing translations to: {output_path}")
        except Exception as e:
            self.logger.error(f"Failed to export missing translations: {e}")

        return csv_content

    def clear(self) -> None:
        """Clear the set of missing translations (useful for testing)."""
        self.missing_keys.clear()

    def report_summary(self) -> str:
        """
        Generate a summary report of missing translations.

        Returns:
            Human-readable report string
        """
        count = len(self.missing_keys)
        duration = datetime.now() - self._session_start

        report = f"""
Missing Translations Report
============================
Duration: {duration}
Total Missing Keys: {count}
"""

        if count > 0:
            # Group by namespace
            namespaces: dict[str, list[str]] = {}
            for key in sorted(self.missing_keys):
                namespace = key.split(".")[0]
                if namespace not in namespaces:
                    namespaces[namespace] = []
                namespaces[namespace].append(key)

            for namespace in sorted(namespaces.keys()):
                keys = namespaces[namespace]
                report += f"\n{namespace}: {len(keys)} missing\n"
                for key in sorted(keys):
                    report += f"  - {key}\n"
        else:
            report += "\nNo missing translations found!\n"

        return report


# Singleton instance
_fallback_handler: FallbackHandler | None = None


def get_fallback_handler() -> FallbackHandler:
    """
    Get or create singleton fallback handler.

    Returns:
        FallbackHandler instance
    """
    global _fallback_handler
    if _fallback_handler is None:
        _fallback_handler = FallbackHandler()
    return _fallback_handler
