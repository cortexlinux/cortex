"""
Tests for the live monitor UI module.
"""

import threading
import time
from unittest.mock import MagicMock, Mock, patch

import pytest
from rich.live import Live
from rich.panel import Panel

from cortex.monitor.live_monitor_ui import LiveMonitorUI, MonitorUI, bar


class TestBarFunction:
    """Tests for the bar() function."""

    def test_bar_normal_percentage(self):
        """Test bar with normal percentage values."""
        # Test 0%
        assert bar(0, 10) == "░░░░░░░░░░"
        # Test 50%
        assert bar(50, 10) == "█████░░░░░"
        # Test 100%
        assert bar(100, 10) == "██████████"
        # Test 25%
        assert bar(25, 8) == "██░░░░░░"

    def test_bar_edge_cases(self):
        """Test bar with edge cases."""
        # Test negative percentage (should clamp to 0)
        assert bar(-10, 10) == "░░░░░░░░░░"
        # Test >100 percentage (should clamp to 100)
        assert bar(150, 10) == "██████████"
        # Test different widths
        assert bar(50, 20) == "██████████░░░░░░░░░░"
        assert bar(30, 4) == "█░░░"

    def test_bar_precise_values(self):
        """Test bar with precise percentage values."""
        # Test rounding
        assert bar(33, 10) == "███░░░░░░░"  # 33% of 10 = 3.3 → 3 filled
        assert bar(67, 10) == "██████░░░░"  # 67% of 10 = 6.7 → 6 filled


class TestMonitorUI:
    """Tests for MonitorUI class (static formatting methods)."""

    def test_create_progress_bar(self):
        """Test create_progress_bar method."""
        # Test basic usage
        assert MonitorUI.create_progress_bar(0, 10) == "░░░░░░░░░░"
        assert MonitorUI.create_progress_bar(100, 10) == "██████████"
        assert MonitorUI.create_progress_bar(50, 10) == "█████░░░░░"

        # Test with different width
        assert MonitorUI.create_progress_bar(50, 4) == "██░░"

    @patch("cortex.monitor.live_monitor_ui.psutil.cpu_count")
    def test_format_system_health(self, mock_cpu_count):
        """Test format_system_health method."""
        mock_cpu_count.return_value = 4

        metrics = {
            "cpu_percent": 45.0,
            "memory_used_gb": 8.2,
            "memory_total_gb": 16.0,
            "memory_percent": 51.0,
            "disk_used_gb": 120.0,
            "disk_total_gb": 500.0,
            "disk_percent": 24.0,
            "network_down_mb": 2.5,
            "network_up_mb": 0.8,
        }

        expected_output = (
            "  CPU:     45% (4 cores)\n"
            "  RAM:     8.2/16.0 GB (51%)\n"
            "  Disk:    120/500 GB (24%)\n"
            "  Network: 2.5 MB/s ↓  0.8 MB/s ↑"
        )

        result = MonitorUI.format_system_health(metrics)
        assert result == expected_output
        mock_cpu_count.assert_called_once_with(logical=True)

    @patch("cortex.monitor.live_monitor_ui.psutil.cpu_count")
    def test_format_system_health_rounded_values(self, mock_cpu_count):
        """Test format_system_health with rounding."""
        mock_cpu_count.return_value = 8

        metrics = {
            "cpu_percent": 45.678,
            "memory_used_gb": 8.234,
            "memory_total_gb": 16.0,
            "memory_percent": 51.456,
            "disk_used_gb": 120.5,
            "disk_total_gb": 500.0,
            "disk_percent": 24.123,
            "network_down_mb": 2.567,
            "network_up_mb": 0.834,
        }

        result = MonitorUI.format_system_health(metrics)
        # 45.678 rounds to 46%
        assert "46%" in result
        assert "8.2/16.0" in result  # One decimal for memory
        assert "120/500" in result  # No decimals for disk
        assert "2.6 MB/s" in result  # One decimal for network

    def test_format_installation_metrics(self):
        """Test format_installation_metrics method."""
        # Calculate memory_percent from used/total
        memory_percent = (12.5 / 16.0) * 100  # = 78.125

        metrics = {
            "cpu_percent": 80.0,
            "memory_used_gb": 12.5,
            "memory_total_gb": 16.0,
            "memory_percent": memory_percent,
            "disk_used_gb": 2.1,
            "disk_total_gb": 3.5,
        }

        result = MonitorUI.format_installation_metrics(metrics)

        # Check expected content
        assert "80% (compilation)" in result
        assert "12.5/16.0 GB" in result
        assert "2.1/3.5 GB" in result
        # Should include progress bars
        assert "█" in result  # Progress bar characters
        assert "░" in result

    def test_format_peak_usage(self):
        """Test format_peak_usage method."""
        peak_metrics = {"cpu_percent": 95.0, "memory_used_gb": 13.2}

        result = MonitorUI.format_peak_usage(peak_metrics)
        assert result == "📊 Peak usage: CPU 95%, RAM 13.2 GB"

        # Test with rounding
        peak_metrics2 = {"cpu_percent": 95.678, "memory_used_gb": 13.245}
        result2 = MonitorUI.format_peak_usage(peak_metrics2)
        assert result2 == "📊 Peak usage: CPU 96%, RAM 13.2 GB"

    def test_format_installation_complete(self):
        """Test format_installation_complete method."""
        result = MonitorUI.format_installation_complete()
        assert result == "✓  Installation complete"

    def test_format_installing_header(self):
        """Test format_installing_header method."""
        result = MonitorUI.format_installing_header("CUDA")
        assert result == "Installing CUDA..."

        result2 = MonitorUI.format_installing_header("TensorFlow")
        assert result2 == "Installing TensorFlow..."


class TestLiveMonitorUI:
    """Tests for LiveMonitorUI class."""

    def test_initialization(self):
        """Test LiveMonitorUI initialization."""
        mock_monitor = MagicMock()
        mock_monitor.history = []

        ui = LiveMonitorUI(mock_monitor, title="Test Installation")

        assert ui.monitor == mock_monitor
        assert ui.title == "Test Installation"
        assert ui._stop_event is not None
        assert ui._thread is None
        assert isinstance(ui._stop_event, threading.Event)

    def test_initialization_default_title(self):
        """Test LiveMonitorUI initialization with default title."""
        mock_monitor = MagicMock()
        mock_monitor.history = []

        ui = LiveMonitorUI(mock_monitor)

        assert ui.title == "Installing..."

    def test_render_no_history(self):
        """Test _render when monitor has no history."""
        mock_monitor = MagicMock()
        mock_monitor.history = []

        ui = LiveMonitorUI(mock_monitor)
        panel = ui._render()

        assert isinstance(panel, Panel)
        # Check that it shows "Collecting metrics..."
        assert panel.renderable == "Collecting metrics..."

    def test_render_with_history(self):
        """Test _render when monitor has history."""
        mock_monitor = MagicMock()
        mock_monitor.history = [
            {
                "cpu_percent": 45.0,
                "memory_used_gb": 8.2,
                "memory_total_gb": 16.0,
                "memory_percent": 51.25,
                "disk_used_gb": 120.0,
                "disk_total_gb": 500.0,
                "disk_percent": 24.0,
                "network_down_mb": 2.5,
                "network_up_mb": 0.8,
            }
        ]

        ui = LiveMonitorUI(mock_monitor, title="Test Render")
        panel = ui._render()

        assert isinstance(panel, Panel)
        assert panel.border_style == "cyan"

        # Get the text content
        text = str(panel.renderable)
        assert "Test Render" in text
        assert "45%" in text
        assert "8.2/16.0" in text
        assert "120.0/500.0" in text
        assert "2.5" in text  # Network download
        assert "0.8" in text  # Network upload

    def test_render_zero_total_memory(self):
        """Test _render when total memory is zero (edge case)."""
        mock_monitor = MagicMock()
        mock_monitor.history = [
            {
                "cpu_percent": 45.0,
                "memory_used_gb": 8.2,
                "memory_total_gb": 0.0,  # Zero total!
                "memory_percent": 0.0,
                "disk_used_gb": 120.0,
                "disk_total_gb": 0.0,  # Zero total!
                "disk_percent": 0.0,
            }
        ]

        ui = LiveMonitorUI(mock_monitor)
        panel = ui._render()

        text = str(panel.renderable)
        # Should show "total unavailable" for RAM and Disk
        assert "total unavailable" in text

    def test_render_no_network_metrics(self):
        """Test _render when network metrics are missing."""
        mock_monitor = MagicMock()
        mock_monitor.history = [
            {
                "cpu_percent": 45.0,
                "memory_used_gb": 8.2,
                "memory_total_gb": 16.0,
                "memory_percent": 51.25,
                "disk_used_gb": 120.0,
                "disk_total_gb": 500.0,
                "disk_percent": 24.0,
                # No network metrics
            }
        ]

        ui = LiveMonitorUI(mock_monitor)
        panel = ui._render()

        text = str(panel.renderable)
        # Should not crash when network metrics are missing
        assert "CPU:" in text
        assert "RAM:" in text
        assert "Disk:" in text
        # Should not show Net: line when no network metrics
        assert "Net:" not in text

    @patch("cortex.monitor.live_monitor_ui.Live")
    @patch("cortex.monitor.live_monitor_ui.time.sleep")
    def test_start_stop(self, mock_sleep, mock_live_class):
        """Test start and stop methods."""
        mock_monitor = MagicMock()
        mock_monitor.history = []

        # Mock Live context manager
        mock_live = MagicMock()
        mock_live_class.return_value.__enter__.return_value = mock_live
        mock_live_class.return_value.__exit__.return_value = None

        ui = LiveMonitorUI(mock_monitor)

        # Track sleep calls
        sleep_calls = []

        def sleep_side_effect(seconds):
            sleep_calls.append(seconds)
            # Stop after first sleep
            if len(sleep_calls) == 1:
                ui._stop_event.set()

        mock_sleep.side_effect = sleep_side_effect

        ui.start()

        # Wait for thread to start and finish
        if ui._thread:
            ui._thread.join(timeout=2.0)

        # Stop the UI
        ui.stop()

        # Verify Live was used
        mock_live_class.assert_called_once()
        mock_live.update.assert_called()

        # Verify sleep was called at least once
        assert len(sleep_calls) >= 1
        assert sleep_calls[0] == 0.5

    def test_start_already_running(self):
        """Test starting when already running."""
        mock_monitor = MagicMock()
        mock_monitor.history = []

        ui = LiveMonitorUI(mock_monitor)

        # Create a mock thread that appears alive
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        ui._thread = mock_thread

        # Should not start new thread
        ui.start()
        # No assertion needed - just checking it doesn't crash

    def test_stop_no_thread(self):
        """Test stop when no thread exists."""
        mock_monitor = MagicMock()
        mock_monitor.history = []

        ui = LiveMonitorUI(mock_monitor)
        ui._thread = None

        # Should not crash
        ui.stop()


class TestLiveMonitorUIThreadSafety:
    """Thread safety tests for LiveMonitorUI."""

    @patch("cortex.monitor.live_monitor_ui.threading.Thread")
    def test_multiple_start_stop(self, mock_thread_class):
        """Test starting and stopping multiple times."""
        mock_monitor = MagicMock()
        mock_monitor.history = []

        ui = LiveMonitorUI(mock_monitor)

        # Mock thread instance
        mock_thread_instance = MagicMock()
        mock_thread_class.return_value = mock_thread_instance

        # Start first time
        ui.start()
        mock_thread_class.assert_called_once()
        mock_thread_instance.start.assert_called_once()

        # Stop
        ui.stop()

        # Reset mocks
        mock_thread_class.reset_mock()
        mock_thread_instance.reset_mock()

        # Start again
        ui.start()
        mock_thread_class.assert_called_once()
        mock_thread_instance.start.assert_called_once()


# Test the bar function directly (not through MonitorUI)
class TestBarFunctionDirect:
    """Direct tests for the bar function."""

    def test_bar_direct_calls(self):
        """Test the bar function directly."""
        # Test exact matches
        assert bar(0) == "░░░░░░░░░░"  # Default width=10
        assert bar(100) == "██████████"
        assert bar(50) == "█████░░░░░"

        # Test custom width
        assert bar(50, 4) == "██░░"
        assert bar(75, 8) == "██████░░"

        # Test clamping
        assert bar(-10) == "░░░░░░░░░░"
        assert bar(110) == "██████████"

        # Test floating point
        assert bar(33.3, 10) == "███░░░░░░░"  # 3.33 → 3
        assert bar(66.6, 10) == "██████░░░░"  # 6.66 → 6


# Integration tests
class TestLiveMonitorUIIntegration:
    """Integration-style tests for LiveMonitorUI."""

    def test_real_monitor_integration(self):
        """Test with a real ResourceMonitor instance."""
        from cortex.monitor.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()
        ui = LiveMonitorUI(monitor)

        # Basic initialization test
        assert ui.monitor == monitor
        assert ui.title == "Installing..."

        # Render should work even with empty monitor
        panel = ui._render()
        assert isinstance(panel, Panel)
        assert panel.renderable == "Collecting metrics..."

    @patch("cortex.monitor.live_monitor_ui.Live")
    @patch("cortex.monitor.live_monitor_ui.time.sleep")
    def test_full_ui_cycle(self, mock_sleep, mock_live_class):
        """Test a complete UI start/display/stop cycle."""
        from cortex.monitor.resource_monitor import ResourceMonitor

        monitor = ResourceMonitor()

        # Add some dummy history
        monitor.history = [
            {
                "cpu_percent": 30.0,
                "memory_used_gb": 4.2,
                "memory_total_gb": 16.0,
                "memory_percent": 26.25,
                "disk_used_gb": 100.0,
                "disk_total_gb": 500.0,
                "disk_percent": 20.0,
            }
        ]

        ui = LiveMonitorUI(monitor, title="Integration Test")

        # Mock Live
        mock_live = MagicMock()
        mock_live_class.return_value.__enter__.return_value = mock_live

        # Make sleep stop the loop quickly
        def quick_stop(seconds):
            ui._stop_event.set()

        mock_sleep.side_effect = quick_stop

        # Start UI
        ui.start()

        # Wait briefly
        if ui._thread:
            ui._thread.join(timeout=1.0)

        # Stop
        ui.stop()

        # Verify UI rendered something
        mock_live_class.assert_called_once()
        mock_live.update.assert_called()
