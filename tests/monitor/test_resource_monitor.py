import time
from unittest.mock import MagicMock, patch

import psutil
import pytest

from cortex.monitor.resource_monitor import ResourceMonitor


@pytest.fixture
def monitor():
    return ResourceMonitor(interval=1.0)


def test_initial_state(monitor):
    """Test that monitor initializes with correct defaults."""
    assert monitor.interval == 1.0
    assert monitor.history == []
    assert all(value == 0.0 for value in monitor.peak_usage.values())
    assert monitor._disk_before is None
    assert monitor._net_before is None


def test_collect_metrics_basic(monkeypatch, monitor):
    """Test metrics collection with mocked psutil calls."""
    # Mock CPU
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 42.0)

    # Mock memory
    mock_memory = MagicMock()
    mock_memory.used = 8 * 1024**3
    mock_memory.total = 16 * 1024**3
    mock_memory.percent = 50.0
    monkeypatch.setattr(psutil, "virtual_memory", lambda: mock_memory)

    # Mock disk usage
    mock_disk = MagicMock()
    mock_disk.used = 120 * 1024**3
    mock_disk.total = 500 * 1024**3
    mock_disk.percent = 24.0
    monkeypatch.setattr(psutil, "disk_usage", lambda _: mock_disk)

    # Mock disk IO
    mock_disk_io = MagicMock(read_bytes=1000, write_bytes=2000)
    monkeypatch.setattr(psutil, "disk_io_counters", lambda: mock_disk_io)

    # Mock network IO
    mock_net = MagicMock(bytes_sent=3000, bytes_recv=4000)
    monkeypatch.setattr(psutil, "net_io_counters", lambda: mock_net)

    metrics = monitor.collect_metrics()

    assert metrics["cpu_percent"] == 42.0
    assert metrics["memory_used_gb"] == 8.0
    assert metrics["memory_total_gb"] == 16.0
    assert metrics["memory_percent"] == 50.0
    assert metrics["disk_used_gb"] == 120.0
    assert metrics["disk_total_gb"] == 500.0
    assert metrics["disk_percent"] == 24.0

    # First sample should have 0 rates
    assert metrics["disk_read_mb"] == 0.0
    assert metrics["disk_write_mb"] == 0.0
    assert metrics["network_up_mb"] == 0.0
    assert metrics["network_down_mb"] == 0.0


def test_collect_metrics_with_previous_values(monkeypatch):
    """Test rate calculations when previous values exist."""
    monitor = ResourceMonitor(interval=1.0)

    # Set up previous values
    mock_prev_disk = MagicMock(read_bytes=1000, write_bytes=2000)
    mock_prev_net = MagicMock(bytes_sent=3000, bytes_recv=4000)
    monitor._disk_before = mock_prev_disk
    monitor._net_before = mock_prev_net

    # Mock current values with differences
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 50.0)

    mock_memory = MagicMock()
    mock_memory.used = 8 * 1024**3
    mock_memory.total = 16 * 1024**3
    mock_memory.percent = 50.0
    monkeypatch.setattr(psutil, "virtual_memory", lambda: mock_memory)

    monkeypatch.setattr(
        psutil,
        "disk_usage",
        lambda _: MagicMock(used=120 * 1024**3, total=500 * 1024**3, percent=24.0),
    )

    # Current values: increased by 1MB (1024*1024 bytes)
    monkeypatch.setattr(
        psutil,
        "disk_io_counters",
        lambda: MagicMock(read_bytes=1000 + 1024 * 1024, write_bytes=2000 + 1024 * 1024),
    )

    monkeypatch.setattr(
        psutil,
        "net_io_counters",
        lambda: MagicMock(bytes_sent=3000 + 1024 * 1024, bytes_recv=4000 + 1024 * 1024),
    )

    metrics = monitor.collect_metrics()

    # Should calculate 1 MB/s (1 MB difference over 1 second interval)
    assert metrics["disk_read_mb"] == pytest.approx(1.0, rel=0.01)
    assert metrics["disk_write_mb"] == pytest.approx(1.0, rel=0.01)
    assert metrics["network_up_mb"] == pytest.approx(1.0, rel=0.01)
    assert metrics["network_down_mb"] == pytest.approx(1.0, rel=0.01)


def test_update_and_peak_usage(monitor):
    """Test that update() stores metrics and tracks peaks correctly."""
    metrics1 = {
        "cpu_percent": 30.0,
        "memory_percent": 40.0,
        "memory_used_gb": 6.0,
        "disk_percent": 10.0,
        "disk_used_gb": 50.0,
        "disk_read_mb": 1.0,
        "disk_write_mb": 2.0,
        "network_up_mb": 0.5,
        "network_down_mb": 1.5,
    }

    metrics2 = {
        "cpu_percent": 80.0,  # Higher than metrics1
        "memory_percent": 70.0,
        "memory_used_gb": 12.0,
        "disk_percent": 30.0,
        "disk_used_gb": 150.0,
        "disk_read_mb": 5.0,
        "disk_write_mb": 6.0,
        "network_up_mb": 2.0,
        "network_down_mb": 3.0,
    }

    monitor.update(metrics1)
    monitor.update(metrics2)

    # Check peaks are updated to highest values
    assert monitor.peak_usage["cpu_percent"] == 80.0
    assert monitor.peak_usage["memory_percent"] == 70.0
    assert monitor.peak_usage["memory_used_gb"] == 12.0
    assert monitor.peak_usage["disk_percent"] == 30.0
    assert monitor.peak_usage["disk_used_gb"] == 150.0
    assert monitor.peak_usage["disk_read_mb"] == 5.0
    assert monitor.peak_usage["network_up_mb"] == 2.0

    # Check history is stored
    assert len(monitor.history) == 2
    assert monitor.history[0] == metrics1
    assert monitor.history[1] == metrics2


def test_sample_adds_history(monkeypatch, monitor):
    """Test that sample() collects metrics and updates history."""
    mock_metrics = {
        "timestamp": time.time(),
        "cpu_percent": 10.0,
        "memory_percent": 20.0,
        "memory_used_gb": 4.0,
        "memory_total_gb": 16.0,
        "disk_percent": 5.0,
        "disk_used_gb": 30.0,
        "disk_total_gb": 500.0,
        "disk_read_mb": 0.1,
        "disk_write_mb": 0.2,
        "network_up_mb": 0.01,
        "network_down_mb": 0.02,
    }

    monkeypatch.setattr(monitor, "collect_metrics", lambda: mock_metrics)

    metrics = monitor.sample()

    assert len(monitor.history) == 1
    assert monitor.history[0] == mock_metrics
    assert metrics == mock_metrics
    assert monitor.peak_usage["cpu_percent"] == 10.0


def test_get_summary(monitor):
    """Test get_summary() returns formatted output."""
    now = time.time()

    monitor.history.append(
        {
            "timestamp": now,
            "cpu_percent": 55.5,
            "memory_used_gb": 8.2,
            "memory_total_gb": 16.0,
            "memory_percent": 51.0,
            "disk_used_gb": 120.0,
            "disk_total_gb": 500.0,
            "disk_percent": 24.0,
            "disk_read_mb": 0.0,
            "disk_write_mb": 0.0,
            "network_up_mb": 0.8,
            "network_down_mb": 2.5,
        }
    )

    monitor.peak_usage["cpu_percent"] = 95.0
    monitor.peak_usage["memory_used_gb"] = 13.2

    summary = monitor.get_summary()

    assert "current" in summary
    current = summary["current"]

    # Check raw values exist
    assert current["cpu_percent"] == 55.5
    assert current["memory_used_gb"] == 8.2
    assert current["memory_total_gb"] == 16.0
    assert current["disk_used_gb"] == 120.0

    assert "%" in current["cpu"]

    assert "8.2/16.0" in current["memory"]
    assert "120/500" in current["disk"]

    # Network should show both upload and download
    assert "2.5" in current["network"]
    assert "0.8" in current["network"]


def test_get_summary_empty_history(monitor):
    """Test get_summary() with empty history returns empty dict."""
    summary = monitor.get_summary()
    assert summary == {}  # Your code returns {} for empty history


def test_get_peak_usage(monitor):
    """Test get_peak_usage() returns peak values."""
    monitor.peak_usage = {
        "cpu_percent": 90.0,
        "memory_percent": 85.0,
        "memory_used_gb": 14.0,
    }

    peaks = monitor.get_peak_usage()
    assert peaks["cpu_percent"] == 90.0
    assert peaks["memory_percent"] == 85.0
    assert peaks["memory_used_gb"] == 14.0


def test_get_history(monitor):
    """Test get_history() returns all collected metrics."""
    metrics1 = {"cpu_percent": 10.0}
    metrics2 = {"cpu_percent": 20.0}

    monitor.history = [metrics1, metrics2]

    history = monitor.get_history()
    assert len(history) == 2
    assert history[0] == metrics1
    assert history[1] == metrics2


def test_clear_history_resets_state(monitor):
    """Test clear_history() resets all tracking."""
    # Set up some state
    monitor.history.append({"cpu_percent": 10.0})
    monitor.history.append({"cpu_percent": 20.0})
    monitor.peak_usage["cpu_percent"] = 90.0
    monitor.peak_usage["memory_percent"] = 80.0

    mock_disk = MagicMock()
    mock_net = MagicMock()
    monitor._disk_before = mock_disk
    monitor._net_before = mock_net

    monitor.clear_history()

    # Verify everything is reset
    assert monitor.history == []
    assert all(value == 0.0 for value in monitor.peak_usage.values())
    assert monitor._disk_before is None
    assert monitor._net_before is None


def test_monitor_with_duration(monitor):
    """Test monitor() respects duration parameter."""
    with patch.object(monitor, "sample") as mock_sample:
        with patch("time.time", side_effect=[0.0, 0.5, 1.5, 3.0]):
            with patch("time.sleep") as mock_sleep:
                monitor.monitor(duration=2.0)

                # Should sample twice (at t=0.0 and t=1.5) before duration is exceeded at t=3.0
                assert mock_sample.call_count == 2
                mock_sleep.assert_called_with(1.0)


def test_monitor_keyboard_interrupt(monitor):
    """Test monitor() handles KeyboardInterrupt gracefully."""
    call_count = 0

    def mock_sample():
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise KeyboardInterrupt

    with patch.object(monitor, "sample", side_effect=mock_sample):
        with patch("time.sleep"):
            monitor.monitor()

    assert call_count == 2  # Should stop after interrupt


# ADD THESE NEW TESTS TO COVER MISSING METHODS:


def test_get_formatted_summary(monitor):
    """Test get_formatted_summary() returns only formatted data."""
    now = time.time()
    monitor.history.append(
        {
            "timestamp": now,
            "cpu_percent": 55.5,
            "memory_used_gb": 8.2,
            "memory_total_gb": 16.0,
            "memory_percent": 51.0,
            "disk_used_gb": 120.0,
            "disk_total_gb": 500.0,
            "disk_percent": 24.0,
            "disk_read_mb": 0.0,
            "disk_write_mb": 0.0,
            "network_up_mb": 0.8,
            "network_down_mb": 2.5,
        }
    )

    formatted = monitor.get_formatted_summary()
    assert formatted != {}
    assert "current" in formatted
    assert "cpu" in formatted["current"]
    assert "memory" in formatted["current"]
    assert "disk" in formatted["current"]
    assert "network" in formatted["current"]


def test_get_recent_alerts(monitor):
    """Test get_recent_alerts() returns samples with alerts."""
    # Add samples with and without alerts
    monitor.history = [
        {"timestamp": 1000, "alerts": ["CPU alert"], "cpu_percent": 90},
        {"timestamp": 2000, "alerts": [], "cpu_percent": 50},
        {"timestamp": 3000, "alerts": ["Memory alert"], "cpu_percent": 60},
    ]

    recent_alerts = monitor.get_recent_alerts(last_n_samples=3)
    assert len(recent_alerts) == 2  # Only 2 samples have alerts
    assert recent_alerts[0]["timestamp"] == 1000
    assert recent_alerts[1]["timestamp"] == 3000


def test_get_recommendations(monitor):
    """Test get_recommendations() generates recommendations."""
    # Set high peak usage to trigger recommendations
    monitor.peak_usage = {
        "cpu_percent": 90.0,
        "memory_percent": 95.0,
        "disk_percent": 10.0,
        "network_up_mb": 60.0,
        "network_down_mb": 70.0,
    }

    recommendations = monitor.get_recommendations()
    assert len(recommendations) > 0
    assert any("CPU" in rec for rec in recommendations)
    assert any("memory" in rec.lower() for rec in recommendations)
    assert any("network" in rec.lower() for rec in recommendations)


def test_get_stats(monitor):
    """Test get_stats() returns statistics."""
    # Add some history
    monitor.history = [
        {"cpu_percent": 10.0, "memory_percent": 20.0, "disk_percent": 30.0, "timestamp": 1000},
        {"cpu_percent": 20.0, "memory_percent": 40.0, "disk_percent": 60.0, "timestamp": 2000},
    ]

    stats = monitor.get_stats()
    assert stats != {}
    assert "averages" in stats
    assert stats["averages"]["cpu_percent"] == 15.0
    assert stats["averages"]["memory_percent"] == 30.0
    assert stats["samples"] == 2


def test_check_alerts(monitor):
    """Test check_alerts() detects threshold violations."""
    # Set thresholds
    monitor.cpu_threshold = 80.0
    monitor.memory_threshold = 90.0
    monitor.disk_threshold = 95.0

    # Test with metrics below thresholds
    metrics_low = {
        "cpu_percent": 50.0,
        "memory_percent": 60.0,
        "disk_percent": 70.0,
    }
    alerts_low = monitor.check_alerts(metrics_low)
    assert len(alerts_low) == 0

    # Test with metrics above thresholds
    metrics_high = {
        "cpu_percent": 90.0,
        "memory_percent": 95.0,
        "disk_percent": 99.0,
    }
    alerts_high = monitor.check_alerts(metrics_high)
    assert len(alerts_high) == 3
    assert any("CPU" in alert for alert in alerts_high)
    assert any("memory" in alert.lower() for alert in alerts_high)
    assert any("disk" in alert.lower() for alert in alerts_high)
