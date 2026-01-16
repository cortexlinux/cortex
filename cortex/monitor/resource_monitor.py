"""
Core resource monitoring system.
Collects and tracks CPU, memory, disk, and network usage.
"""

import logging
import time
from typing import Any

import psutil

# Default alert threshold constants
DEFAULT_CPU_ALERT_THRESHOLD = 85.0
DEFAULT_MEMORY_ALERT_THRESHOLD = 90.0
DEFAULT_DISK_ALERT_THRESHOLD = 95.0
DEFAULT_MAX_HISTORY_SIZE = 1000  # Optional: prevent unbounded growth

# Set up logging
logger = logging.getLogger(__name__)


class ResourceMonitor:
    """Collects and tracks system resource usage."""

    def __init__(
        self,
        interval: float = 1.0,
        cpu_threshold: float = DEFAULT_CPU_ALERT_THRESHOLD,
        memory_threshold: float = DEFAULT_MEMORY_ALERT_THRESHOLD,
        disk_threshold: float = DEFAULT_DISK_ALERT_THRESHOLD,
        max_history_size: int | None = DEFAULT_MAX_HISTORY_SIZE,
    ) -> None:
        """
        Initialize the resource monitor.

        Args:
            interval: Time interval (in seconds) between measurements.
            cpu_threshold: CPU usage percentage threshold for alerts.
            memory_threshold: Memory usage percentage threshold for alerts.
            disk_threshold: Disk usage percentage threshold for alerts.
            max_history_size: Maximum number of samples to keep in history.
                              None means unlimited (not recommended for long runs).
        """
        self.interval = interval
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        self.disk_threshold = disk_threshold
        self.max_history_size = max_history_size
        self.history: list[dict[str, Any]] = []

        self.peak_usage: dict[str, float] = {
            "cpu_percent": 0.0,
            "memory_percent": 0.0,
            "memory_used_gb": 0.0,
            "disk_percent": 0.0,
            "disk_used_gb": 0.0,
            "disk_read_mb": 0.0,
            "disk_write_mb": 0.0,
            "network_up_mb": 0.0,
            "network_down_mb": 0.0,
        }

        # Avoid private psutil types using Any
        self._disk_before: Any = None
        self._net_before: Any = None

    def collect_metrics(self) -> dict[str, Any]:
        """Collect a single snapshot of system metrics."""
        timestamp = time.time()

        # CPU Usage
        cpu_percent = psutil.cpu_percent(interval=None)

        # Memory Usage
        memory = psutil.virtual_memory()
        memory_used_gb = memory.used / (1024**3)
        memory_total_gb = memory.total / (1024**3)
        memory_percent = memory.percent

        # Disk Usage (space)
        disk_space = psutil.disk_usage("/")
        disk_used_gb = disk_space.used / (1024**3)
        disk_total_gb = disk_space.total / (1024**3)
        disk_percent = disk_space.percent

        # Disk I/O (activity)
        disk_io = psutil.disk_io_counters()

        # Network I/O
        net_io = psutil.net_io_counters()

        # Calculate rates (divide by interval for MB/s)
        disk_read_mb = 0.0
        disk_write_mb = 0.0
        network_up_mb = 0.0
        network_down_mb = 0.0

        if self._disk_before:
            disk_read_mb = (
                (disk_io.read_bytes - self._disk_before.read_bytes) / (1024**2) / self.interval
            )
            disk_write_mb = (
                (disk_io.write_bytes - self._disk_before.write_bytes) / (1024**2) / self.interval
            )

        if self._net_before:
            network_up_mb = (
                (net_io.bytes_sent - self._net_before.bytes_sent) / (1024**2) / self.interval
            )
            network_down_mb = (
                (net_io.bytes_recv - self._net_before.bytes_recv) / (1024**2) / self.interval
            )

        # Store current for next calculation
        self._disk_before = disk_io
        self._net_before = net_io

        return {
            "timestamp": timestamp,
            "cpu_percent": cpu_percent,
            "memory_used_gb": memory_used_gb,
            "memory_total_gb": memory_total_gb,
            "memory_percent": memory_percent,
            "disk_used_gb": disk_used_gb,
            "disk_total_gb": disk_total_gb,
            "disk_percent": disk_percent,
            "disk_read_mb": disk_read_mb,
            "disk_write_mb": disk_write_mb,
            "network_up_mb": network_up_mb,
            "network_down_mb": network_down_mb,
        }

    def check_alerts(self, metrics: dict[str, Any]) -> list[str]:
        """
        Check resource usage against alert thresholds.

        Args:
            metrics: Dictionary of collected metrics

        Returns:
            List of alert messages (empty if no alerts)
        """
        alerts = []

        if metrics.get("cpu_percent", 0) >= self.cpu_threshold:
            alerts.append(
                f"⚠ High CPU usage detected ({metrics['cpu_percent']:.1f}% > {self.cpu_threshold}%)"
            )

        if metrics.get("memory_percent", 0) >= self.memory_threshold:
            alerts.append(
                f"⚠ High memory usage detected ({metrics['memory_percent']:.1f}% > {self.memory_threshold}%)"
            )

        if metrics.get("disk_percent", 0) >= self.disk_threshold:
            alerts.append(
                f"⚠ Low disk space detected ({metrics['disk_percent']:.1f}% > {self.disk_threshold}%)"
            )

        return alerts

    def update(self, metrics: dict[str, Any]) -> None:
        """Store metrics and update peak usage."""
        # Apply history size limit if configured
        if self.max_history_size and len(self.history) >= self.max_history_size:
            self.history.pop(0)  # Remove oldest sample

        self.history.append(metrics)

        for key in self.peak_usage:
            if key in metrics:
                self.peak_usage[key] = max(self.peak_usage[key], metrics[key])

    def sample(self) -> dict[str, Any]:
        """Collect and store one monitoring sample with alerts."""
        metrics = self.collect_metrics()
        alerts = self.check_alerts(metrics)
        metrics["alerts"] = alerts
        self.update(metrics)
        return metrics

    def monitor(self, duration: float | None = None) -> dict[str, Any]:
        """
        Continuously monitor system resources.

        Args:
            duration: Time in seconds to monitor. If None, runs until interrupted.

        Returns:
            Summary of the monitoring session
        """
        start_time = time.time()

        try:
            while True:
                if duration and (time.time() - start_time) >= duration:
                    break

                self.sample()
                time.sleep(self.interval)

        except KeyboardInterrupt:
            logger.info("Monitoring interrupted by user")
        except Exception as exc:
            logger.error("Monitoring error: %s", exc)
            raise

        return self.get_summary()

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of current and peak usage (with both raw and formatted data)."""
        if not self.history:
            return {}

        latest = self.history[-1]

        # Create the summary with raw data
        summary = {
            "current": {
                # Raw numeric values (for calculations)
                "cpu_percent": latest["cpu_percent"],
                "memory_used_gb": latest["memory_used_gb"],
                "memory_total_gb": latest["memory_total_gb"],
                "memory_percent": latest["memory_percent"],
                "disk_used_gb": latest["disk_used_gb"],
                "disk_total_gb": latest["disk_total_gb"],
                "disk_percent": latest["disk_percent"],
                "network_down_mb": latest["network_down_mb"],
                "network_up_mb": latest["network_up_mb"],
                "disk_read_mb": latest["disk_read_mb"],
                "disk_write_mb": latest["disk_write_mb"],
                # Formatted strings (for display)
                "cpu": f"{latest['cpu_percent']:.0f}%",
                "memory": f"{latest['memory_used_gb']:.1f}/{latest['memory_total_gb']:.1f} GB ({latest['memory_percent']:.0f}%)",
                "disk": f"{latest['disk_used_gb']:.0f}/{latest['disk_total_gb']:.0f} GB ({latest['disk_percent']:.0f}%)",
                "network": f"{latest['network_down_mb']:.1f} MB/s ↓  {latest['network_up_mb']:.1f} MB/s ↑",
            },
            "peak": self.peak_usage.copy(),
            "samples": len(self.history),
            "duration": (
                self.history[-1]["timestamp"] - self.history[0]["timestamp"]
                if len(self.history) > 1
                else 0
            ),
            "thresholds": {
                "cpu": self.cpu_threshold,
                "memory": self.memory_threshold,
                "disk": self.disk_threshold,
            },
        }

        return summary

    def get_formatted_summary(self) -> dict[str, Any]:
        """
        Get a formatted summary for display purposes.
        This should be moved to UI layer eventually.
        """
        summary = self.get_summary()
        if not summary:
            return {}

        return {
            "current": {
                "cpu": summary["current"]["cpu"],
                "memory": summary["current"]["memory"],
                "disk": summary["current"]["disk"],
                "network": summary["current"]["network"],
            },
            "peak": summary["peak"],
            "samples": summary["samples"],
            "thresholds": summary["thresholds"],
        }

    def get_peak_usage(self) -> dict[str, float]:
        """Return peak resource usage."""
        return self.peak_usage.copy()

    def get_history(self, limit: int | None = None) -> list[dict[str, Any]]:
        """
        Return collected resource history.

        Args:
            limit: Maximum number of recent samples to return. If None, return all.

        Returns:
            List of monitoring samples
        """
        if limit and limit < len(self.history):
            return self.history[-limit:].copy()
        return self.history.copy()

    def clear_history(self) -> None:
        """Clear monitoring history and reset peak values."""
        self.history.clear()
        self.peak_usage = dict.fromkeys(self.peak_usage, 0.0)
        self._disk_before = None
        self._net_before = None

    def get_recent_alerts(self, last_n_samples: int = 10) -> list[dict[str, Any]]:
        """
        Get recent samples that triggered alerts.

        Args:
            last_n_samples: Number of recent samples to check (default: 10)

        Returns:
            List of samples with alerts, each containing timestamp and alert messages
        """
        if not self.history:
            return []

        recent_samples = self.history[-last_n_samples:]
        return [
            {
                "timestamp": sample["timestamp"],
                "alerts": sample.get("alerts", []),
                "cpu_percent": sample.get("cpu_percent", 0),
                "memory_percent": sample.get("memory_percent", 0),
                "disk_percent": sample.get("disk_percent", 0),
            }
            for sample in recent_samples
            if sample.get("alerts")
        ]

    def get_recommendations(self) -> list[str]:
        """
        Generate performance recommendations based on peak resource usage.

        Returns:
            List of human-readable performance recommendations
        """
        recommendations = []

        cpu_peak = self.peak_usage.get("cpu_percent", 0)
        memory_peak = self.peak_usage.get("memory_percent", 0)
        disk_peak = self.peak_usage.get("disk_percent", 0)

        if cpu_peak >= self.cpu_threshold:
            recommendations.append(
                f"High CPU usage detected ({cpu_peak:.1f}%) — consider running installations during lower system load."
            )

        if memory_peak >= self.memory_threshold:
            recommendations.append(
                f"High memory usage detected ({memory_peak:.1f}%) — consider closing background applications or increasing RAM."
            )

        if disk_peak >= self.disk_threshold:
            recommendations.append(
                f"Disk usage was very high ({disk_peak:.1f}%) — ensure sufficient free disk space before installation."
            )

        # Network recommendations
        network_up_peak = self.peak_usage.get("network_up_mb", 0)
        network_down_peak = self.peak_usage.get("network_down_mb", 0)

        if network_up_peak > 50 or network_down_peak > 50:
            recommendations.append(
                f"High network usage detected (↑{network_up_peak:.1f} MB/s, ↓{network_down_peak:.1f} MB/s) — "
                "large downloads/uploads may slow other network operations."
            )

        if not recommendations:
            recommendations.append(
                "System resources were within optimal limits during installation."
            )

        return recommendations

    def get_stats(self) -> dict[str, Any]:
        """
        Get comprehensive monitoring statistics.

        Returns:
            Dictionary with various statistics about the monitoring session
        """
        if not self.history:
            return {}

        cpu_values = [sample["cpu_percent"] for sample in self.history]
        memory_values = [sample["memory_percent"] for sample in self.history]
        disk_values = [sample["disk_percent"] for sample in self.history]

        def safe_average(values: list[float]) -> float:
            return sum(values) / len(values) if values else 0.0

        return {
            "averages": {
                "cpu_percent": safe_average(cpu_values),
                "memory_percent": safe_average(memory_values),
                "disk_percent": safe_average(disk_values),
            },
            "samples": len(self.history),
            "duration_seconds": (
                self.history[-1]["timestamp"] - self.history[0]["timestamp"]
                if len(self.history) > 1
                else 0
            ),
            "interval_seconds": self.interval,
            "history_size": len(self.history),
            "max_history_size": self.max_history_size,
        }
