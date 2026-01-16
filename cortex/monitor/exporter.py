"""
Data export functionality for monitoring system.
Handles JSON and CSV export formats.
This module provides data export capabilities for system monitoring data,
supporting both JSON (for structured analysis) and CSV (for spreadsheet
import) formats. It handles data serialization, file operations, and
error handling with specific exceptions.
"""

import csv
import json
import logging
import os
import time
from collections.abc import Callable
from typing import Any

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
        OSError: If file cannot be written or directory cannot be created
        ValueError: If output_file is empty or None
        TypeError: If history or peak_usage have wrong types
        AttributeError: If get_recommendations_func is invalid when called
    """
    # Input validation
    if not output_file or not isinstance(output_file, str):
        raise ValueError(f"Invalid output_file: {output_file!r}")

    if not isinstance(history, list):
        raise TypeError(f"history must be a list, got {type(history).__name__}")

    if not isinstance(peak_usage, dict):
        raise TypeError(f"peak_usage must be a dict, got {type(peak_usage).__name__}")

    try:
        # Ensure output directory exists
        output_dir = os.path.dirname(os.path.abspath(output_file))
        if output_dir:  # Only create if there's a directory component
            os.makedirs(output_dir, exist_ok=True)

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
                if isinstance(recommendations, list):
                    payload["recommendations"] = recommendations
                    logger.debug("Added recommendations to JSON export")
                else:
                    logger.warning(
                        "get_recommendations_func returned non-list: %s",
                        type(recommendations).__name__,
                    )
            except AttributeError as exc:
                logger.warning("Failed to call recommendations function: %s", exc)
            except (TypeError, ValueError) as exc:
                logger.warning("Error generating recommendations: %s", exc)
            except Exception as exc:
                logger.warning("Unexpected error generating recommendations: %s", exc)
                # Continue without recommendations - don't fail the export

        # Write JSON with proper encoding
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)

        logger.info("JSON export successful: %s", output_file)

    except OSError as exc:
        logger.error("File system error during JSON export to %s: %s", output_file, exc)
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error("Data serialization error during JSON export: %s", exc)
        raise ValueError(f"Data cannot be serialized to JSON: {exc}") from exc


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
        OSError: If file cannot be written or directory cannot be created
        ValueError: If output_file is empty or None, or history has inconsistent structure
        TypeError: If history has wrong type
    """
    # Input validation
    if not output_file or not isinstance(output_file, str):
        raise ValueError(f"Invalid output_file: {output_file!r}")

    if not isinstance(history, list):
        raise TypeError(f"history must be a list, got {type(history).__name__}")

    try:
        # Ensure output directory exists
        output_dir = os.path.dirname(os.path.abspath(output_file))
        if output_dir:  # Only create if there's a directory component
            os.makedirs(output_dir, exist_ok=True)

        if not history:
            # Create file with standard headers for empty data
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
            if not isinstance(sample, dict):
                raise ValueError(f"Sample must be a dict, got {type(sample).__name__}")
            fieldnames_set.update(sample.keys())

        if not fieldnames_set:
            raise ValueError("No fieldnames found in history data")

        fieldnames = sorted(fieldnames_set)

        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for i, sample in enumerate(history):
                try:
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
                except (KeyError, AttributeError) as exc:
                    logger.warning("Error processing sample %d: %s", i, exc)
                    # Skip problematic sample but continue export

        logger.info("CSV export successful: %s (%d rows)", output_file, len(history))

    except OSError as exc:
        logger.error("File system error during CSV export to %s: %s", output_file, exc)
        raise
    except csv.Error as exc:
        logger.error("CSV formatting error: %s", exc)
        raise ValueError(f"CSV formatting error: {exc}") from exc


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
        format_type: 'json' or 'csv' (case-insensitive)
        output_file: Path to output file (must be non-empty string)
        include_recommendations: Whether to include recommendations (JSON only)
    Returns:
        bool: True if successful, False otherwise
    Raises:
        AttributeError: If monitor doesn't have required methods
        ValueError: If format_type is unsupported or output_file is invalid
    """
    # Input validation
    if not output_file or not isinstance(output_file, str):
        logger.error("Invalid output file: %s", output_file)
        return False

    if not isinstance(format_type, str):
        logger.error("Format type must be a string, got %s", type(format_type).__name__)
        return False

    format_type_lower = format_type.lower()
    if format_type_lower not in ("json", "csv"):
        logger.error("Unsupported export format: %s", format_type)
        return False

    try:
        # Validate monitor has required methods
        if not hasattr(monitor, "get_history"):
            raise AttributeError("monitor missing get_history() method")
        if not hasattr(monitor, "get_peak_usage"):
            raise AttributeError("monitor missing get_peak_usage() method")

        history = monitor.get_history()
        peak_usage = monitor.get_peak_usage()

        if format_type_lower == "json":
            # Get recommendations function if available and requested
            get_recommendations_func = None
            if include_recommendations and hasattr(monitor, "get_recommendations"):
                get_recommendations_func = monitor.get_recommendations

            export_to_json(
                history,
                peak_usage,
                output_file,
                include_recommendations=include_recommendations,
                get_recommendations_func=get_recommendations_func,
            )
        else:  # csv
            export_to_csv(history, output_file)

        return True

    except (OSError, ValueError, TypeError, AttributeError) as exc:
        logger.error("Export failed for %s: %s", output_file, exc)
        return False
    except Exception as exc:
        logger.error("Unexpected error during export: %s", exc)
        return False


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
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        logger.error("Simplified JSON export failed: %s", exc)
        return False
    except Exception as exc:
        logger.error("Unexpected error in simplified JSON export: %s", exc)
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
    except (OSError, ValueError, TypeError) as exc:
        logger.error("Simplified CSV export failed: %s", exc)
        return False
    except Exception as exc:
        logger.error("Unexpected error in simplified CSV export: %s", exc)
        return False
