"""
Tests for the ResourceMonitor core monitoring logic.
"""

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
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 42.0)

    mock_memory = MagicMock()
    mock_memory.used = 8 * 1024**3
    mock_memory.total = 16 * 1024**3
    mock_memory.percent = 50.0
    monkeypatch.setattr(psutil, "virtual_memory", lambda: mock_memory)

    mock_disk = MagicMock()
    mock_disk.used = 120 * 1024**3
    mock_disk.total = 500 * 1024**3
    mock_disk.percent = 24.0
    monkeypatch.setattr(psutil, "disk_usage", lambda _: mock_disk)

    mock_disk_io = MagicMock(read_bytes=1000, write_bytes=2000)
    monkeypatch.setattr(psutil, "disk_io_counters", lambda: mock_disk_io)

    mock_net = MagicMock(bytes_sent=3000, bytes_recv=4000)
    monkeypatch.setattr(psutil, "net_io_counters", lambda: mock_net)

    metrics = monitor.collect_metrics()

    assert metrics["cpu_percent"] == pytest.approx(42.0)
    assert metrics["memory_used_gb"] == pytest.approx(8.0)
    assert metrics["memory_total_gb"] == pytest.approx(16.0)
    assert metrics["memory_percent"] == pytest.approx(50.0)
    assert metrics["disk_used_gb"] == pytest.approx(120.0)
    assert metrics["disk_total_gb"] == pytest.approx(500.0)
    assert metrics["disk_percent"] == pytest.approx(24.0)

    # First sample has zero rates
    assert metrics["disk_read_mb"] == 0.0
    assert metrics["disk_write_mb"] == 0.0
    assert metrics["network_up_mb"] == 0.0
    assert metrics["network_down_mb"] == 0.0


def test_collect_metrics_with_previous_values(monkeypatch):
    """Test rate calculations when previous values exist."""
    monitor = ResourceMonitor(interval=1.0)

    monitor._disk_before = MagicMock(read_bytes=1000, write_bytes=2000)
    monitor._net_before = MagicMock(bytes_sent=3000, bytes_recv=4000)

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

    monkeypatch.setattr(
        psutil,
        "disk_io_counters",
        lambda: MagicMock(read_bytes=1000 + 1024**2, write_bytes=2000 + 1024**2),
    )

    monkeypatch.setattr(
        psutil,
        "net_io_counters",
        lambda: MagicMock(bytes_sent=3000 + 1024**2, bytes_recv=4000 + 1024**2),
    )

    metrics = monitor.collect_metrics()

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
        "cpu_percent": 80.0,
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

    assert monitor.peak_usage["cpu_percent"] == 80.0
    assert monitor.peak_usage["memory_percent"] == 70.0
    assert monitor.peak_usage["memory_used_gb"] == 12.0
    assert monitor.peak_usage["disk_percent"] == 30.0
    assert monitor.peak_usage["disk_used_gb"] == 150.0
    assert monitor.peak_usage["disk_read_mb"] == 5.0
    assert monitor.peak_usage["network_up_mb"] == 2.0

    assert len(monitor.history) == 2


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
    assert metrics == mock_metrics
    assert monitor.peak_usage["cpu_percent"] == 10.0


def test_get_summary(monitor):
    """Test get_summary() returns raw numeric data."""
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

    summary = monitor.get_summary()
    current = summary["current"]

    assert current["cpu_percent"] == pytest.approx(55.5)
    assert current["memory_used_gb"] == pytest.approx(8.2)
    assert current["disk_used_gb"] == pytest.approx(120.0)
    assert current["network_down_mb"] == pytest.approx(2.5)
    assert current["network_up_mb"] == pytest.approx(0.8)


def test_get_summary_empty_history(monitor):
    """Test get_summary() with empty history."""
    assert monitor.get_summary() == {}


def test_get_peak_usage(monitor):
    """Test get_peak_usage() returns a copy."""
    monitor.peak_usage["cpu_percent"] = 90.0
    peaks = monitor.get_peak_usage()

    assert peaks["cpu_percent"] == 90.0
    peaks["cpu_percent"] = 0.0
    assert monitor.peak_usage["cpu_percent"] == 90.0


def test_get_history(monitor):
    """Test get_history() returns stored history."""
    monitor.history = [{"cpu_percent": 10.0}, {"cpu_percent": 20.0}]
    history = monitor.get_history()

    assert len(history) == 2
    assert history[0]["cpu_percent"] == 10.0


def test_clear_history_resets_state(monitor):
    """Test clear_history() resets all internal state."""
    monitor.history = [{"cpu_percent": 10.0}]
    monitor.peak_usage["cpu_percent"] = 90.0
    monitor._disk_before = MagicMock()
    monitor._net_before = MagicMock()

    monitor.clear_history()

    assert monitor.history == []
    assert all(value == 0.0 for value in monitor.peak_usage.values())
    assert monitor._disk_before is None
    assert monitor._net_before is None


def test_monitor_with_duration(monitor):
    """Test monitor() respects duration."""
    with patch.object(monitor, "sample") as mock_sample:
        with patch("time.time", side_effect=[0.0, 0.5, 1.5, 3.0]):
            with patch("time.sleep"):
                monitor.monitor(duration=2.0)

    assert mock_sample.call_count == 2


def test_monitor_keyboard_interrupt(monitor):
    """Test monitor() stops on KeyboardInterrupt."""
    calls = 0

    def side_effect():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt

    with patch.object(monitor, "sample", side_effect=side_effect):
        with patch("time.sleep"):
            monitor.monitor()

    assert calls == 2


def test_get_recent_alerts(monitor):
    """Test get_recent_alerts() returns only alert samples."""
    monitor.history = [
        {"timestamp": 1000, "alerts": ["CPU alert"], "cpu_percent": 90},
        {"timestamp": 2000, "alerts": [], "cpu_percent": 50},
        {"timestamp": 3000, "alerts": ["Memory alert"], "cpu_percent": 60},
    ]

    alerts = monitor.get_recent_alerts(last_n_samples=3)
    assert len(alerts) == 2
    assert alerts[0]["timestamp"] == 1000
    assert alerts[1]["timestamp"] == 3000


def test_get_recommendations(monitor):
    """Test recommendations are generated from peak usage."""
    monitor.peak_usage = {
        "cpu_percent": 90.0,
        "memory_percent": 95.0,
        "disk_percent": 10.0,
        "network_up_mb": 60.0,
        "network_down_mb": 70.0,
    }

    recs = monitor.get_recommendations()

    assert any("CPU" in r for r in recs)
    assert any("memory" in r.lower() for r in recs)
    assert any("network" in r.lower() for r in recs)


def test_get_stats(monitor):
    """Test get_stats() returns averages and metadata."""
    monitor.history = [
        {"cpu_percent": 10.0, "memory_percent": 20.0, "disk_percent": 30.0, "timestamp": 1000},
        {"cpu_percent": 20.0, "memory_percent": 40.0, "disk_percent": 60.0, "timestamp": 2000},
    ]

    stats = monitor.get_stats()

    assert stats["averages"]["cpu_percent"] == pytest.approx(15.0)
    assert stats["averages"]["memory_percent"] == pytest.approx(30.0)
    assert stats["samples"] == 2


def test_check_alerts(monitor):
    """Test alert detection logic."""
    monitor.cpu_threshold = 80.0
    monitor.memory_threshold = 90.0
    monitor.disk_threshold = 95.0

    low = {"cpu_percent": 50.0, "memory_percent": 60.0, "disk_percent": 70.0}
    assert monitor.check_alerts(low) == []

    high = {"cpu_percent": 90.0, "memory_percent": 95.0, "disk_percent": 99.0}
    alerts = monitor.check_alerts(high)

    assert len(alerts) == 3
