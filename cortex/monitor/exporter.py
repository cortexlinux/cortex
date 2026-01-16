"""
Data export functionality for monitoring system.
Handles JSON and CSV export formats.
"""

import csv
import json
import logging
import os
import time
from collections.abc import Callable
from typing import Any, Optional

# Set up logging
logger = logging.getLogger(__name__)


def export_to_json(
    history: list[dict[str, Any]],
    peak_usage: dict[str, float],
    output_file: str,
    include_recommendations: bool = False,
    get_recommendations_func: Callable[[], list[str]] | None = None,
) -> None:
    """
    Export monitoring data to a JSON file.

    Args:
        history: List of monitoring samples
        peak_usage: Peak resource usage dictionary
        output_file: Path to output JSON file
        include_recommendations: Whether to include performance recommendations
        get_recommendations_func: Function to generate recommendations (optional)

    Raises:
        OSError: If file cannot be written
        ValueError: If output_file is invalid
    """
    try:
        # Ensure output directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)

        payload = {
            "metadata": {
                "export_timestamp": time.time(),
                "export_date": time.ctime(),
                "samples_count": len(history),
                "format_version": "1.0",
            },
            "peak_usage": peak_usage,
            "samples": history,
        }

        # Add recommendations if requested
        if include_recommendations and get_recommendations_func:
            try:
                recommendations = get_recommendations_func()
                payload["recommendations"] = recommendations
                logger.debug("Added recommendations to JSON export")
            except Exception as exc:
                logger.warning("Failed to generate recommendations: %s", exc)
                # Continue without recommendations

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)

        logger.info("JSON export successful: %s", output_file)

    except Exception as exc:
        logger.error("JSON export failed: %s", exc)
        raise


def export_to_csv(
    history: list[dict[str, Any]],
    output_file: str,
) -> None:
    """
    Export monitoring history to a CSV file.

    Args:
        history: List of monitoring samples
        output_file: Path to output CSV file

    Raises:
        OSError: If file cannot be written
        ValueError: If output_file is invalid
    """
    try:
        # Ensure output directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)

        if not history:
            # Create file with standard headers
            with open(output_file, "w", newline="", encoding="utf-8") as f:
                # Use standard field names for empty data
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "timestamp",
                        "cpu_percent",
                        "memory_percent",
                        "disk_percent",
                        "alerts",
                    ],
                )
                writer.writeheader()
            logger.info("Empty CSV export created: %s", output_file)
            return

        # Get all possible fieldnames from all samples
        fieldnames_set = set()
        for sample in history:
            fieldnames_set.update(sample.keys())
        fieldnames = sorted(fieldnames_set)

        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for sample in history:
                # Convert any non-serializable values to strings
                row = {}
                for key in fieldnames:
                    value = sample.get(key)
                    if isinstance(value, list):
                        # Convert lists (like alerts) to semicolon-separated strings
                        row[key] = "; ".join(str(item) for item in value)
                    elif value is not None:
                        row[key] = str(value)
                    else:
                        row[key] = ""
                writer.writerow(row)

        logger.info("CSV export successful: %s (%d rows)", output_file, len(history))

    except Exception as exc:
        logger.error("CSV export failed: %s", exc)
        raise


def export_monitoring_data(
    monitor,
    format_type: str,
    output_file: str,
    include_recommendations: bool = True,
) -> bool:
    """
    Convenience function to export monitoring data from a ResourceMonitor instance.

    Args:
        monitor: ResourceMonitor instance with get_history() and get_peak_usage() methods
        format_type: 'json' or 'csv'
        output_file: Path to output file
        include_recommendations: Whether to include recommendations (JSON only)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        history = monitor.get_history()
        peak_usage = monitor.get_peak_usage()

        if format_type.lower() == "json":
            export_to_json(
                history,
                peak_usage,
                output_file,
                include_recommendations=include_recommendations,
                get_recommendations_func=monitor.get_recommendations,
            )
        elif format_type.lower() == "csv":
            export_to_csv(history, output_file)
        else:
            logger.error("Unsupported export format: %s", format_type)
            return False

        return True

    except Exception as exc:
        logger.error("Export failed: %s", exc)
        return False


# Alternative simplified API
def export_json(
    history: list[dict[str, Any]],
    peak_usage: dict[str, float],
    output_file: str,
    **kwargs: Any,
) -> bool:
    """
    Simplified JSON export function that returns success/failure.

    Args:
        history: List of monitoring samples
        peak_usage: Peak resource usage dictionary
        output_file: Path to output JSON file
        **kwargs: Additional arguments passed to export_to_json

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        export_to_json(history, peak_usage, output_file, **kwargs)
        return True
    except Exception:
        return False


def export_csv(
    history: list[dict[str, Any]],
    output_file: str,
) -> bool:
    """
    Simplified CSV export function that returns success/failure.

    Args:
        history: List of monitoring samples
        output_file: Path to output CSV file

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        export_to_csv(history, output_file)
        return True
    except Exception:
        return False
