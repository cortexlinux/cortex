"""
Tests for the live monitor UI module.
"""

import re
import time
from unittest.mock import patch

import pytest
from rich.panel import Panel

from cortex.monitor.live_monitor_ui import LiveMonitorUI, MonitorUI, bar
from cortex.monitor.resource_monitor import ResourceMonitor


class TestBarFunction:
    """Tests for the bar() function."""

    def test_bar_normal_percentage(self):
        assert bar(0, 10) == "░░░░░░░░░░"
        assert bar(50, 10) == "█████░░░░░"
        assert bar(100, 10) == "██████████"
        assert bar(25, 8) == "██░░░░░░"

    def test_bar_edge_cases(self):
        assert bar(-10, 10) == "░░░░░░░░░░"
        assert bar(150, 10) == "██████████"
        assert bar(50, 20) == "██████████░░░░░░░░░░"
        assert bar(30, 4) == "█░░░"

    def test_bar_precise_values(self):
        assert bar(33, 10) == "███░░░░░░░"
        assert bar(67, 10) == "██████░░░░"


class TestMonitorUI:
    """Tests for MonitorUI formatting helpers."""

    def test_create_progress_bar(self):
        assert MonitorUI.create_progress_bar(0, 10) == "░░░░░░░░░░"
        assert MonitorUI.create_progress_bar(100, 10) == "██████████"
        assert MonitorUI.create_progress_bar(50, 4) == "██░░"

    def test_format_system_health(self):
        metrics = {
            "cpu_percent": 45.0,
            "cpu_cores": 4,
            "memory_used_gb": 8.2,
            "memory_total_gb": 16.0,
            "memory_percent": 51.0,
            "disk_used_gb": 120.0,
            "disk_total_gb": 500.0,
            "disk_percent": 24.0,
            "network_down_mb": 2.5,
            "network_up_mb": 0.8,
        }

        output = MonitorUI.format_system_health(metrics)
        assert "CPU:" in output
        assert "RAM:" in output
        assert "Disk:" in output
        assert "Network:" in output

    def test_format_installation_metrics(self):
        metrics = {
            "cpu_percent": 80.0,
            "memory_used_gb": 12.5,
            "memory_total_gb": 16.0,
            "memory_percent": 78.125,
            "disk_used_gb": 2.1,
            "disk_total_gb": 3.5,
        }

        output = MonitorUI.format_installation_metrics(metrics)
        assert "80%" in output
        assert "12.5/16.0" in output
        assert "2.1/3.5" in output
        assert "█" in output

    def test_format_peak_usage(self):
        peak = {"cpu_percent": 95.0, "memory_used_gb": 13.2}
        assert MonitorUI.format_peak_usage(peak) == "📊 Peak usage: CPU 95%, RAM 13.2 GB"

    def test_format_installation_complete(self):
        assert MonitorUI.format_installation_complete() == "✓  Installation complete"


class TestLiveMonitorUI:
    """Tests for LiveMonitorUI behavior."""

    def test_get_latest_metrics_empty(self):
        monitor = ResourceMonitor()
        ui = LiveMonitorUI(monitor)
        assert ui._get_latest_metrics() is None

    def test_get_latest_metrics_present(self):
        monitor = ResourceMonitor()
        monitor.history.append(
            {
                "cpu_percent": 10.0,
                "memory_used_gb": 2.0,
                "memory_total_gb": 8.0,
                "memory_percent": 25.0,
                "disk_used_gb": 10.0,
                "disk_total_gb": 100.0,
                "disk_percent": 10.0,
            }
        )

        ui = LiveMonitorUI(monitor)
        metrics = ui._get_latest_metrics()
        assert metrics["cpu_percent"] == 10.0

    def test_render_no_history(self):
        monitor = ResourceMonitor()
        ui = LiveMonitorUI(monitor)
        panel = ui._render()
        assert isinstance(panel, Panel)
        assert "Collecting metrics" in str(panel.renderable)

    def test_render_with_metrics(self):
        monitor = ResourceMonitor()
        monitor.history.append(
            {
                "cpu_percent": 50.0,
                "memory_used_gb": 4.0,
                "memory_total_gb": 8.0,
                "memory_percent": 50.0,
                "disk_used_gb": 20.0,
                "disk_total_gb": 100.0,
                "disk_percent": 20.0,
                "network_up_mb": 1.0,
                "network_down_mb": 2.0,
            }
        )

        ui = LiveMonitorUI(monitor)
        panel = ui._render()
        content = str(panel.renderable)

        assert "CPU" in content
        assert "RAM" in content
        assert "Disk" in content

    def test_start_and_stop(self):
        monitor = ResourceMonitor()
        ui = LiveMonitorUI(monitor)

        with patch("time.sleep", return_value=None):
            ui.start()
            time.sleep(0.05)
            ui.stop()

        assert ui._thread is None
