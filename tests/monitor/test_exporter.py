import csv
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cortex.monitor.exporter import export_monitoring_data, export_to_csv, export_to_json
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
        assert data["peak_usage"]["cpu_percent"] == 90.0
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
        assert rows[0]["cpu_percent"] == "50.0"
        assert rows[1]["cpu_percent"] == "90.0"

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
        result = export_monitoring_data(monitor, "json", None)
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
        from cortex.monitor.exporter import export_json

        history = [{"timestamp": 1.0, "cpu_percent": 50.0}]
        peak_usage = {"cpu_percent": 50.0}

        output_file = tmp_path / "simple.json"
        result = export_json(history, peak_usage, str(output_file))

        assert result is True
        assert output_file.exists()

    def test_export_csv_simplified_api(self, tmp_path):
        """Test the simplified export_csv API."""
        from cortex.monitor.exporter import export_csv

        history = [{"timestamp": 1.0, "cpu_percent": 50.0}]

        output_file = tmp_path / "simple.csv"
        result = export_csv(history, str(output_file))

        assert result is True
        assert output_file.exists()

    def test_export_json_simplified_api_failure(self, monkeypatch):
        """Test the simplified export_json API returns False on failure."""
        from cortex.monitor.exporter import export_json

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
        from cortex.monitor.exporter import export_csv

        # Mock export_to_csv to raise an exception
        def mock_export_to_csv(*args, **kwargs):
            raise OSError("Simulated error")

        monkeypatch.setattr("cortex.monitor.exporter.export_to_csv", mock_export_to_csv)

        history = [{"timestamp": 1.0}]

        result = export_csv(history, "test.csv")
        assert result is False
