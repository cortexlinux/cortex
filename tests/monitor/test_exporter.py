import csv
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from cortex.monitor.exporter import (
    export_csv,
    export_json,
    export_monitoring_data,
    export_to_csv,
    export_to_json,
)
from cortex.monitor.resource_monitor import ResourceMonitor


class TestExporter:
    """Test cases for monitoring data export functionality."""

    def test_export_to_json(self, tmp_path):
        """Test JSON export with sample data."""
        history = [
            {
                "timestamp": 1234567890.0,
                "cpu_percent": 50.0,
                "memory_percent": 60.0,
                "disk_percent": 30.0,
                "alerts": [],
            },
            {
                "timestamp": 1234567891.0,
                "cpu_percent": 90.0,
                "memory_percent": 85.0,
                "disk_percent": 35.0,
                "alerts": ["⚠ High CPU usage detected (90.0% > 85.0%)"],
            },
        ]

        peak_usage = {
            "cpu_percent": 90.0,
            "memory_percent": 85.0,
            "disk_percent": 35.0,
        }

        output_file = tmp_path / "test_output.json"

        # This should not raise an exception
        export_to_json(history, peak_usage, str(output_file))

        assert output_file.exists()

        # Verify JSON content
        with open(output_file) as f:
            data = json.load(f)

        assert "metadata" in data
        assert "peak_usage" in data
        assert "samples" in data
        assert data["peak_usage"]["cpu_percent"] == pytest.approx(90.0, rel=1e-9)
        assert len(data["samples"]) == 2

    def test_export_to_csv(self, tmp_path):
        """Test CSV export with sample data."""
        history = [
            {
                "timestamp": 1234567890.0,
                "cpu_percent": 50.0,
                "memory_percent": 60.0,
                "disk_percent": 30.0,
            },
            {
                "timestamp": 1234567891.0,
                "cpu_percent": 90.0,
                "memory_percent": 85.0,
                "disk_percent": 35.0,
                "alerts": ["CPU alert"],
            },
        ]

        output_file = tmp_path / "test_output.csv"

        # This should not raise an exception
        export_to_csv(history, str(output_file))

        assert output_file.exists()

        # Verify CSV content
        with open(output_file) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        # CSV stores as strings, convert to float for comparison
        assert float(rows[0]["cpu_percent"]) == pytest.approx(50.0, rel=1e-9)
        assert float(rows[1]["cpu_percent"]) == pytest.approx(90.0, rel=1e-9)

    def test_export_to_csv_empty_history(self, tmp_path):
        """Test CSV export with empty history."""
        history = []
        output_file = tmp_path / "empty.csv"

        export_to_csv(history, str(output_file))

        assert output_file.exists()

        # Should create file with just headers
        with open(output_file) as f:
            content = f.read()

        assert "timestamp" in content

    def test_export_to_json_with_recommendations(self, tmp_path):
        """Test JSON export with recommendations."""
        history = [{"cpu_percent": 90.0}]
        peak_usage = {"cpu_percent": 90.0}

        def mock_recommendations():
            return ["High CPU usage detected"]

        output_file = tmp_path / "test_with_recs.json"

        export_to_json(
            history,
            peak_usage,
            str(output_file),
            include_recommendations=True,
            get_recommendations_func=mock_recommendations,
        )

        with open(output_file) as f:
            data = json.load(f)

        assert "recommendations" in data
        assert len(data["recommendations"]) == 1

    def test_export_monitoring_data_json(self, tmp_path):
        """Test export_monitoring_data with JSON format."""
        monitor = ResourceMonitor()

        # Mock the methods since ResourceMonitor might not have real data
        monitor.get_history = MagicMock(
            return_value=[
                {
                    "timestamp": 1234567890.0,
                    "cpu_percent": 75.0,
                    "memory_percent": 65.0,
                    "alerts": [],
                }
            ]
        )
        monitor.get_peak_usage = MagicMock(
            return_value={"cpu_percent": 75.0, "memory_percent": 65.0}
        )
        monitor.get_recommendations = MagicMock(return_value=[])

        output_file = tmp_path / "monitor_data.json"
        result = export_monitoring_data(monitor, "json", str(output_file))

        assert result is True
        assert output_file.exists()

    def test_export_monitoring_data_csv(self, tmp_path):
        """Test export_monitoring_data with CSV format."""
        monitor = ResourceMonitor()

        # Mock the methods
        monitor.get_history = MagicMock(
            return_value=[
                {
                    "timestamp": 1234567890.0,
                    "cpu_percent": 75.0,
                    "memory_percent": 65.0,
                }
            ]
        )
        monitor.get_peak_usage = MagicMock(return_value={})

        output_file = tmp_path / "monitor_data.csv"
        result = export_monitoring_data(monitor, "csv", str(output_file))

        assert result is True
        assert output_file.exists()

    def test_export_monitoring_data_invalid_format(self):
        """Test export_monitoring_data with invalid format."""
        monitor = ResourceMonitor()

        # Mock minimal methods
        monitor.get_history = MagicMock(return_value=[])
        monitor.get_peak_usage = MagicMock(return_value={})

        with tempfile.NamedTemporaryFile() as tmp:
            result = export_monitoring_data(monitor, "invalid", tmp.name)

        assert result is False

    def test_export_json_handles_complex_data(self, tmp_path):
        """Test JSON export handles complex data types."""
        history = [
            {
                "timestamp": 1234567890.0,
                "cpu_percent": 50.0,
                "alerts": ["Alert 1", "Alert 2"],
                "nested": {"key": "value"},
            }
        ]

        peak_usage = {"cpu_percent": 50.0}

        output_file = tmp_path / "complex.json"
        export_to_json(history, peak_usage, str(output_file))

        assert output_file.exists()

        with open(output_file) as f:
            data = json.load(f)

        # Should handle lists and nested dicts
        assert len(data["samples"][0]["alerts"]) == 2

    def test_export_csv_handles_missing_fields(self, tmp_path):
        """Test CSV export handles samples with different fields."""
        history = [
            {"timestamp": 1, "cpu_percent": 50.0},
            {"timestamp": 2, "cpu_percent": 60.0, "memory_percent": 70.0},
            {"timestamp": 3, "disk_percent": 40.0},
        ]

        output_file = tmp_path / "mixed_fields.csv"
        export_to_csv(history, str(output_file))

        assert output_file.exists()

        with open(output_file) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Should have all 3 rows
        assert len(rows) == 3
        # Should have all fieldnames
        assert "cpu_percent" in reader.fieldnames
        assert "memory_percent" in reader.fieldnames
        assert "disk_percent" in reader.fieldnames

    def test_export_csv_alerts_conversion(self, tmp_path):
        """Test CSV export converts alert lists to strings."""
        history = [
            {
                "timestamp": 1234567890.0,
                "cpu_percent": 90.0,
                "alerts": ["CPU alert", "Memory alert"],
            }
        ]

        output_file = tmp_path / "alerts.csv"
        export_to_csv(history, str(output_file))

        with open(output_file) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Alerts should be converted to semicolon-separated string
        assert "CPU alert; Memory alert" in rows[0]["alerts"]

    def test_export_monitoring_data_no_history(self, tmp_path):
        """Test export_monitoring_data with no history."""
        monitor = ResourceMonitor()

        # Mock methods to return empty data
        monitor.get_history = MagicMock(return_value=[])
        monitor.get_peak_usage = MagicMock(return_value={})
        monitor.get_recommendations = MagicMock(return_value=[])

        output_file = tmp_path / "empty.json"
        result = export_monitoring_data(monitor, "json", str(output_file))

        assert result is True
        assert output_file.exists()

        # Should create valid JSON even with empty history
        with open(output_file) as f:
            data = json.load(f)

        assert data["metadata"]["samples_count"] == 0

    def test_export_to_json_handles_write_error(self, tmp_path):
        """Test export_to_json handles file write errors."""
        history = [{"timestamp": 1.0, "cpu_percent": 50.0}]
        peak_usage = {"cpu_percent": 50.0}

        # Test that it raises OSError as documented
        output_file = tmp_path / "test.json"

        # Make the file read-only to cause a write error
        import os

        output_file.touch()
        os.chmod(output_file, 0o444)  # Read-only

        try:
            # Should raise OSError
            with pytest.raises(OSError):
                export_to_json(history, peak_usage, str(output_file))
        finally:
            # Restore permissions for cleanup
            os.chmod(output_file, 0o755)

    def test_export_to_csv_handles_write_error(self, tmp_path):
        """Test export_to_csv handles file write errors."""
        history = [{"timestamp": 1.0, "cpu_percent": 50.0}]

        # Test that it raises OSError as documented
        output_file = tmp_path / "test.csv"

        # Make the file read-only to cause a write error
        import os

        output_file.touch()
        os.chmod(output_file, 0o444)  # Read-only

        try:
            # Should raise OSError
            with pytest.raises(OSError):
                export_to_csv(history, str(output_file))
        finally:
            # Restore permissions for cleanup
            os.chmod(output_file, 0o755)

    def test_export_monitoring_data_invalid_format_handling(self):
        """Test export_monitoring_data with invalid format."""
        monitor = ResourceMonitor()

        # Mock methods
        monitor.get_history = MagicMock(return_value=[{"timestamp": 1.0}])
        monitor.get_peak_usage = MagicMock(return_value={})

        # Test with invalid format - should return False
        result = export_monitoring_data(monitor, "invalid_format", "test.txt")
        assert result is False

    def test_export_monitoring_data_empty_monitor(self, tmp_path):
        """Test export_monitoring_data with empty monitor."""
        monitor = ResourceMonitor()

        # Mock methods to return empty data
        monitor.get_history = MagicMock(return_value=[])
        monitor.get_peak_usage = MagicMock(return_value={})
        monitor.get_recommendations = MagicMock(return_value=[])

        output_file = tmp_path / "test.json"
        result = export_monitoring_data(monitor, "json", str(output_file))

        # Should succeed even with empty monitor
        assert result is True

    def test_export_monitoring_data_invalid_path(self):
        """Test export_monitoring_data with invalid path."""
        monitor = ResourceMonitor()

        # Mock methods
        monitor.get_history = MagicMock(return_value=[{"timestamp": 1.0}])
        monitor.get_peak_usage = MagicMock(return_value={})

        # Test with None path - should return False
        result = export_monitoring_data(monitor, "json", "")
        assert result is False

        # Test with empty path - should return False
        result = export_monitoring_data(monitor, "json", "")
        assert result is False

    def test_export_monitoring_data_export_functions_fail(self, monkeypatch):
        """Test when underlying export functions raise exceptions."""
        monitor = ResourceMonitor()

        # Mock methods
        monitor.get_history = MagicMock(return_value=[{"timestamp": 1.0}])
        monitor.get_peak_usage = MagicMock(return_value={})

        # Make export_to_json raise an exception
        def mock_export_to_json(*args, **kwargs):
            raise OSError("Simulated write error")

        monkeypatch.setattr("cortex.monitor.exporter.export_to_json", mock_export_to_json)

        # Should catch the exception and return False
        result = export_monitoring_data(monitor, "json", "test.json")
        assert result is False

    def test_export_json_simplified_api(self, tmp_path):
        """Test the simplified export_json API."""
        history = [{"timestamp": 1.0, "cpu_percent": 50.0}]
        peak_usage = {"cpu_percent": 50.0}

        output_file = tmp_path / "simple.json"
        result = export_json(history, peak_usage, str(output_file))

        assert result is True
        assert output_file.exists()

    def test_export_csv_simplified_api(self, tmp_path):
        """Test the simplified export_csv API."""
        history = [{"timestamp": 1.0, "cpu_percent": 50.0}]

        output_file = tmp_path / "simple.csv"
        result = export_csv(history, str(output_file))

        assert result is True
        assert output_file.exists()

    def test_export_json_simplified_api_failure(self, monkeypatch):
        """Test the simplified export_json API returns False on failure."""

        # Mock export_to_json to raise an exception
        def mock_export_to_json(*args, **kwargs):
            raise OSError("Simulated error")

        monkeypatch.setattr("cortex.monitor.exporter.export_to_json", mock_export_to_json)

        history = [{"timestamp": 1.0}]
        peak_usage = {}

        result = export_json(history, peak_usage, "test.json")
        assert result is False

    def test_export_csv_simplified_api_failure(self, monkeypatch):
        """Test the simplified export_csv API returns False on failure."""

        # Mock export_to_csv to raise an exception
        def mock_export_to_csv(*args, **kwargs):
            raise OSError("Simulated error")

        monkeypatch.setattr("cortex.monitor.exporter.export_to_csv", mock_export_to_csv)

        history = [{"timestamp": 1.0}]

        result = export_csv(history, "test.csv")
        assert result is False

    def test_export_monitoring_data_missing_methods(self):
        class BadMonitor:
            pass

        assert export_monitoring_data(BadMonitor(), "json", "out.json") is False

    def test_export_monitoring_data_invalid_format_type(self):
        monitor = ResourceMonitor()
        assert export_monitoring_data(monitor, 123, "out.json") is False

    # NEW TESTS TO INCREASE COVERAGE

    def test_export_to_json_invalid_output_file(self):
        """Test export_to_json with invalid output_file."""
        history = [{"timestamp": 1.0}]
        peak_usage = {}

        with pytest.raises(ValueError):
            export_to_json(history, peak_usage, "")

        with pytest.raises(ValueError):
            export_to_json(history, peak_usage, None)

    def test_export_to_json_invalid_history_type(self):
        """Test export_to_json with invalid history type."""
        peak_usage = {}

        with pytest.raises(TypeError):
            export_to_json("not a list", peak_usage, "test.json")

        with pytest.raises(TypeError):
            export_to_json({"not": "a list"}, peak_usage, "test.json")

    def test_export_to_json_invalid_peak_usage_type(self):
        """Test export_to_json with invalid peak_usage type."""
        history = [{"timestamp": 1.0}]

        with pytest.raises(TypeError):
            export_to_json(history, "not a dict", "test.json")

        with pytest.raises(TypeError):
            export_to_json(history, ["not", "a", "dict"], "test.json")

    def test_export_to_csv_invalid_output_file(self):
        """Test export_to_csv with invalid output_file."""
        history = [{"timestamp": 1.0}]

        with pytest.raises(ValueError):
            export_to_csv(history, "")

        with pytest.raises(ValueError):
            export_to_csv(history, None)

    def test_export_to_csv_invalid_history_type(self):
        """Test export_to_csv with invalid history type."""
        with pytest.raises(TypeError):
            export_to_csv("not a list", "test.csv")

        with pytest.raises(TypeError):
            export_to_csv({"not": "a list"}, "test.csv")

    def test_export_to_csv_invalid_sample_type(self):
        """Test export_to_csv with invalid sample in history."""
        history = [{"timestamp": 1.0}, "not a dict", {"timestamp": 2.0}]

        output_file = "test.csv"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            output_file = f.name

        try:
            with pytest.raises(ValueError):
                export_to_csv(history, output_file)
        finally:
            os.unlink(output_file)

    def test_export_to_csv_empty_fieldnames(self):
        """Test export_to_csv with empty fieldnames."""
        history = [{}]  # Empty dict

        output_file = "test.csv"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            output_file = f.name

        try:
            with pytest.raises(ValueError):
                export_to_csv(history, output_file)
        finally:
            os.unlink(output_file)

    def test_export_to_json_with_recommendations_non_list(self, tmp_path):
        """Test JSON export when recommendations function returns non-list."""
        history = [{"cpu_percent": 90.0}]
        peak_usage = {"cpu_percent": 90.0}

        def mock_recommendations():
            return "not a list"  # Should trigger warning

        output_file = tmp_path / "test.json"

        with patch("cortex.monitor.exporter.logger") as mock_logger:
            export_to_json(
                history,
                peak_usage,
                str(output_file),
                include_recommendations=True,
                get_recommendations_func=mock_recommendations,
            )

            # Verify warning was logged
            assert mock_logger.warning.called

    def test_export_to_json_with_recommendations_exception(self, tmp_path):
        """Test JSON export when recommendations function raises exception."""
        history = [{"cpu_percent": 90.0}]
        peak_usage = {"cpu_percent": 90.0}

        def mock_recommendations():
            raise AttributeError("Simulated attribute error")

        output_file = tmp_path / "test.json"

        with patch("cortex.monitor.exporter.logger") as mock_logger:
            export_to_json(
                history,
                peak_usage,
                str(output_file),
                include_recommendations=True,
                get_recommendations_func=mock_recommendations,
            )

            # Verify warning was logged but export succeeded
            assert mock_logger.warning.called
            assert output_file.exists()

    def test_export_to_json_serialization_error(self, tmp_path):
        """Test JSON export with unserializable data."""
        history = [{"timestamp": 1.0, "func": lambda x: x}]  # Can't serialize function

        class BadObject:
            def __repr__(self):
                raise TypeError("Can't serialize")

        peak_usage = {"obj": BadObject()}

        output_file = tmp_path / "test.json"

        with pytest.raises(ValueError):
            export_to_json(history, peak_usage, str(output_file))

    def test_export_to_csv_csv_error(self, tmp_path):
        """Test CSV export with CSV formatting error."""
        history = [{"timestamp": 1.0}]
        output_file = tmp_path / "test.csv"

        # Mock csv.DictWriter to raise csv.Error
        with patch("csv.DictWriter") as mock_writer:
            mock_writer.side_effect = csv.Error("Simulated CSV error")

            with pytest.raises(ValueError):
                export_to_csv(history, str(output_file))

    def test_export_monitoring_data_with_recommendations_disabled(self, tmp_path):
        """Test export_monitoring_data with recommendations disabled."""
        monitor = ResourceMonitor()

        monitor.get_history = MagicMock(return_value=[{"timestamp": 1.0}])
        monitor.get_peak_usage = MagicMock(return_value={})
        monitor.get_recommendations = MagicMock(return_value=["rec1", "rec2"])

        output_file = tmp_path / "test.json"

        # Test with recommendations disabled
        result = export_monitoring_data(
            monitor, "json", str(output_file), include_recommendations=False
        )

        assert result is True
        assert output_file.exists()

        with open(output_file) as f:
            data = json.load(f)

        # Recommendations should not be included
        assert "recommendations" not in data

    def test_export_monitoring_data_no_recommendations_method(self, tmp_path):
        """Test export_monitoring_data when monitor has no get_recommendations method."""
        monitor = ResourceMonitor()

        monitor.get_history = MagicMock(return_value=[{"timestamp": 1.0}])
        monitor.get_peak_usage = MagicMock(return_value={})
        # Don't mock get_recommendations

        output_file = tmp_path / "test.json"

        result = export_monitoring_data(monitor, "json", str(output_file))

        assert result is True
        assert output_file.exists()

    def test_export_monitoring_data_raises_attribute_error(self):
        """Test export_monitoring_data when monitor missing required methods."""

        class BadMonitor:
            pass

        # The function catches AttributeError and returns False
        result = export_monitoring_data(BadMonitor(), "json", "test.json")
        assert result is False  # Should return False, not raise

    def test_export_monitoring_data_raises_other_exceptions(self, tmp_path):
        """Test export_monitoring_data catches other exceptions."""
        monitor = ResourceMonitor()

        monitor.get_history = MagicMock(side_effect=RuntimeError("Simulated error"))
        monitor.get_peak_usage = MagicMock(return_value={})

        output_file = tmp_path / "test.json"

        result = export_monitoring_data(monitor, "json", str(output_file))

        assert result is False

    def test_export_json_with_kwargs(self, tmp_path):
        """Test simplified export_json with additional kwargs."""
        history = [{"timestamp": 1.0}]
        peak_usage = {}

        def mock_recommendations():
            return ["Test recommendation"]

        output_file = tmp_path / "test.json"

        result = export_json(
            history,
            peak_usage,
            str(output_file),
            include_recommendations=True,
            get_recommendations_func=mock_recommendations,
        )

        assert result is True
        assert output_file.exists()

    def test_export_json_simplified_catches_attribute_error(self, monkeypatch):
        """Test export_json catches AttributeError."""

        def mock_export_to_json(*args, **kwargs):
            raise AttributeError("Simulated attribute error")

        monkeypatch.setattr("cortex.monitor.exporter.export_to_json", mock_export_to_json)

        result = export_json([{}], {}, "test.json")
        assert result is False

    def test_export_csv_simplified_catches_type_error(self, monkeypatch):
        """Test export_csv catches TypeError."""

        def mock_export_to_csv(*args, **kwargs):
            raise TypeError("Simulated type error")

        monkeypatch.setattr("cortex.monitor.exporter.export_to_csv", mock_export_to_csv)

        result = export_csv([{}], "test.csv")
        assert result is False

    def test_export_to_json_with_directory_creation(self, tmp_path):
        """Test export_to_json creates directory if needed."""
        history = [{"timestamp": 1.0}]
        peak_usage = {}

        # Create a file in a non-existent directory
        output_file = tmp_path / "new_dir" / "subdir" / "test.json"

        export_to_json(history, peak_usage, str(output_file))

        assert output_file.exists()
        assert output_file.parent.exists()

    def test_export_to_csv_with_directory_creation(self, tmp_path):
        """Test export_to_csv creates directory if needed."""
        history = [{"timestamp": 1.0}]

        # Create a file in a non-existent directory
        output_file = tmp_path / "new_dir" / "subdir" / "test.csv"

        export_to_csv(history, str(output_file))

        assert output_file.exists()
        assert output_file.parent.exists()

    def test_export_to_json_handles_none_values(self, tmp_path):
        """Test JSON export handles None values in recommendations."""
        history = [{"timestamp": 1.0}]
        peak_usage = {}

        def mock_recommendations():
            return None

        output_file = tmp_path / "test.json"

        with patch("cortex.monitor.exporter.logger") as mock_logger:
            export_to_json(
                history,
                peak_usage,
                str(output_file),
                include_recommendations=True,
                get_recommendations_func=mock_recommendations,
            )

            # Should log warning
            assert mock_logger.warning.called

    def test_export_to_csv_processes_sample_error(self, tmp_path, caplog):
        """Test CSV export continues when processing a sample fails."""
        history = [
            {"timestamp": 1.0, "cpu_percent": 50.0},
            {"timestamp": 2.0, "cpu_percent": 60.0},  # This will cause error
            {"timestamp": 3.0, "cpu_percent": 70.0},
        ]

        # Create a mock sample that raises error during processing
        class BadSample(dict):
            def get(self, key):
                if key == "timestamp":
                    return 2.0
                raise AttributeError("Simulated attribute error")

        history[1] = BadSample()

        output_file = tmp_path / "test.csv"

        # Should not raise exception
        export_to_csv(history, str(output_file))

        assert output_file.exists()

        # Should have logged warning
        assert "Error processing sample" in caplog.text

    def test_export_monitoring_data_case_insensitive_format(self, tmp_path):
        """Test export_monitoring_data handles case-insensitive format."""
        monitor = ResourceMonitor()

        monitor.get_history = MagicMock(return_value=[{"timestamp": 1.0}])
        monitor.get_peak_usage = MagicMock(return_value={})

        # Test uppercase format
        output_file = tmp_path / "test.json"
        result = export_monitoring_data(monitor, "JSON", str(output_file))
        assert result is True

        # Test mixed case
        output_file2 = tmp_path / "test2.json"
        result2 = export_monitoring_data(monitor, "Json", str(output_file2))
        assert result2 is True

    def test_export_to_json_logs_success(self, tmp_path, caplog):
        """Test export_to_json logs success message."""
        history = [{"timestamp": 1.0}]
        peak_usage = {}
        output_file = tmp_path / "test.json"

        with caplog.at_level("INFO"):
            export_to_json(history, peak_usage, str(output_file))

        assert "JSON export successful" in caplog.text

    def test_export_to_csv_logs_success(self, tmp_path, caplog):
        """Test export_to_csv logs success message."""
        history = [{"timestamp": 1.0}]
        output_file = tmp_path / "test.csv"

        with caplog.at_level("INFO"):
            export_to_csv(history, str(output_file))

        assert "CSV export successful" in caplog.text

    def test_export_monitoring_data_with_none_monitor(self):
        """Test export_monitoring_data with None monitor."""
        result = export_monitoring_data(None, "json", "test.json")
        assert result is False

    def test_export_to_json_with_recommendations_unexpected_error(self, tmp_path):
        """Test JSON export when recommendations function raises unexpected error."""
        history = [{"cpu_percent": 90.0}]
        peak_usage = {"cpu_percent": 90.0}

        def mock_recommendations():
            raise Exception("Simulated unexpected error")

        output_file = tmp_path / "test.json"

        # Should not raise exception, just log warning
        export_to_json(
            history,
            peak_usage,
            str(output_file),
            include_recommendations=True,
            get_recommendations_func=mock_recommendations,
        )

        assert output_file.exists()
