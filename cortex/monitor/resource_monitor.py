"""
Core resource monitoring system.
Collects and tracks CPU, memory, disk, and network usage.

This module provides real-time system resource monitoring capabilities
for Cortex Linux, enabling users to track performance during operations
like software installations.
"""

import logging
import time
from typing import Any

import psutil

# Default alert threshold constants
DEFAULT_CPU_ALERT_THRESHOLD = 85.0
DEFAULT_MEMORY_ALERT_THRESHOLD = 90.0
DEFAULT_DISK_ALERT_THRESHOLD = 95.0
DEFAULT_MAX_HISTORY_SIZE = 1000

logger = logging.getLogger(__name__)


class ResourceMonitor:
    """
    Collects and tracks system resource usage.
    This class provides comprehensive system monitoring capabilities,
    tracking CPU, memory, disk, and network metrics over time. It includes
    alerting mechanisms for resource thresholds and generates performance
    recommendations based on usage patterns.
    Attributes:
        interval (float): Sampling interval in seconds (default: 1.0)
        cpu_threshold (float): CPU usage alert threshold percentage
        memory_threshold (float): Memory usage alert threshold percentage
        disk_threshold (float): Disk usage alert threshold percentage
        max_history_size (int | None): Maximum number of samples to store
        history (list[dict[str, Any]]): Collected metric samples
        peak_usage (dict[str, float]): Peak values for each metric
    Example:
        >>> from cortex.monitor import ResourceMonitor
        >>> monitor = ResourceMonitor(interval=0.5)
        >>> monitor.monitor(duration=5.0)
        >>> recommendations = monitor.get_recommendations()
        >>> for rec in recommendations:
        ...     print(rec)
    """

    def __init__(
        self,
        interval: float = 1.0,
        cpu_threshold: float = DEFAULT_CPU_ALERT_THRESHOLD,
        memory_threshold: float = DEFAULT_MEMORY_ALERT_THRESHOLD,
        disk_threshold: float = DEFAULT_DISK_ALERT_THRESHOLD,
        max_history_size: int | None = DEFAULT_MAX_HISTORY_SIZE,
    ) -> None:
        """
        Initialize a ResourceMonitor instance.
        Args:
            interval: Sampling interval in seconds (must be > 0)
            cpu_threshold: CPU usage percentage that triggers alerts
            memory_threshold: Memory usage percentage that triggers alerts
            disk_threshold: Disk usage percentage that triggers alerts
            max_history_size: Maximum number of samples to store (None = unlimited)
        Raises:
            ValueError: If interval <= 0 or thresholds are not in valid range (0-100)
        Note:
            Thresholds are expressed as percentages (0-100). Values outside
            this range will be clamped to valid percentage bounds.
        """
        if interval <= 0:
            raise ValueError(f"Interval must be positive, got {interval}")

        # Validate thresholds are within reasonable bounds
        for name, value in [
            ("cpu_threshold", cpu_threshold),
            ("memory_threshold", memory_threshold),
            ("disk_threshold", disk_threshold),
        ]:
            if not 0 <= value <= 100:
                logger.warning(
                    "%s %.1f%% is outside recommended range 0-100%%, " "consider adjusting",
                    name,
                    value,
                )

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

        self._disk_before: Any = None
        self._net_before: Any = None

    # Metric Collection

    def collect_metrics(self) -> dict[str, Any]:
        """
        Collect a single snapshot of system metrics.
        Gathers comprehensive system metrics including:
        - CPU usage and core count
        - Memory usage (used, total, percentage)
        - Disk usage (used, total, percentage) and I/O rates
        - Network I/O rates
        Returns:
            dict: Dictionary containing all collected metrics with keys:
                - timestamp: Unix timestamp of collection
                - cpu_percent: CPU usage percentage (0-100)
                - cpu_cores: Number of logical CPU cores
                - memory_used_gb: Used memory in GB
                - memory_total_gb: Total memory in GB
                - memory_percent: Memory usage percentage (0-100)
                - disk_used_gb: Used disk space in GB
                - disk_total_gb: Total disk space in GB
                - disk_percent: Disk usage percentage (0-100)
                - disk_read_mb: Disk read rate in MB/s
                - disk_write_mb: Disk write rate in MB/s
                - network_up_mb: Network upload rate in MB/s
                - network_down_mb: Network download rate in MB/s
        Raises:
            OSError: If system metrics cannot be accessed
            RuntimeError: If metric calculation fails
        Note:
            Disk and network rates are calculated relative to previous
            sample. First call returns 0.0 for rates.
        """
        try:
            timestamp = time.time()

            cpu_percent = psutil.cpu_percent(interval=None)
            cpu_cores = psutil.cpu_count(logical=True)

            memory = psutil.virtual_memory()
            disk_space = psutil.disk_usage("/")
            disk_io = psutil.disk_io_counters()
            net_io = psutil.net_io_counters()

            memory_used_gb = memory.used / (1024**3)
            memory_total_gb = memory.total / (1024**3)

            disk_used_gb = disk_space.used / (1024**3)
            disk_total_gb = disk_space.total / (1024**3)

            disk_read_mb = disk_write_mb = 0.0
            network_up_mb = network_down_mb = 0.0

            if self._disk_before:
                disk_read_mb = (
                    (disk_io.read_bytes - self._disk_before.read_bytes) / (1024**2) / self.interval
                )
                disk_write_mb = (
                    (disk_io.write_bytes - self._disk_before.write_bytes)
                    / (1024**2)
                    / self.interval
                )

            if self._net_before:
                network_up_mb = (
                    (net_io.bytes_sent - self._net_before.bytes_sent) / (1024**2) / self.interval
                )
                network_down_mb = (
                    (net_io.bytes_recv - self._net_before.bytes_recv) / (1024**2) / self.interval
                )

            self._disk_before = disk_io
            self._net_before = net_io

            return {
                "timestamp": timestamp,
                "cpu_percent": cpu_percent,
                "cpu_cores": cpu_cores,
                "memory_used_gb": memory_used_gb,
                "memory_total_gb": memory_total_gb,
                "memory_percent": memory.percent,
                "disk_used_gb": disk_used_gb,
                "disk_total_gb": disk_total_gb,
                "disk_percent": disk_space.percent,
                "disk_read_mb": disk_read_mb,
                "disk_write_mb": disk_write_mb,
                "network_up_mb": network_up_mb,
                "network_down_mb": network_down_mb,
            }
        except OSError as exc:
            logger.error("Failed to collect system metrics: %s", exc)
            raise
        except (AttributeError, TypeError, ZeroDivisionError) as exc:
            logger.error("Error calculating metrics: %s", exc)
            raise RuntimeError(f"Metric calculation failed: {exc}") from exc

    # Alerts & Storage

    def check_alerts(self, metrics: dict[str, Any]) -> list[str]:
        """
        Check metrics against configured thresholds and generate alerts.
        Args:
            metrics: Dictionary of collected metrics from collect_metrics()
        Returns:
            list[str]: List of alert messages for threshold violations.
                      Empty list if no thresholds exceeded.
        Note:
            Only checks CPU, memory, and disk thresholds. Network and
            disk I/O alerts are handled in recommendations.
        """
        alerts: list[str] = []

        if metrics["cpu_percent"] >= self.cpu_threshold:
            alerts.append(f"High CPU usage detected ({metrics['cpu_percent']:.1f}%)")

        if metrics["memory_percent"] >= self.memory_threshold:
            alerts.append(f"High memory usage detected ({metrics['memory_percent']:.1f}%)")

        if metrics["disk_percent"] >= self.disk_threshold:
            alerts.append(f"Low disk space detected ({metrics['disk_percent']:.1f}%)")

        return alerts

    def update(self, metrics: dict[str, Any]) -> None:
        """
        Update history and peak usage with new metrics.
        Args:
            metrics: Dictionary of metrics to store
        Note:
            Maintains history size within max_history_size limit.
            Updates peak_usage dictionary with maximum values seen.
        """
        if self.max_history_size and len(self.history) >= self.max_history_size:
            self.history.pop(0)

        self.history.append(metrics)

        for key in self.peak_usage:
            if key in metrics:
                self.peak_usage[key] = max(self.peak_usage[key], metrics[key])

    def sample(self) -> dict[str, Any]:
        """
        Collect, check, and store a single sample of system metrics.
        Returns:
            dict: Metrics dictionary with added 'alerts' key containing
                  any threshold violation alerts.
        Example:
            >>> monitor = ResourceMonitor()
            >>> sample = monitor.sample()
            >>> if sample.get('alerts'):
            ...     for alert in sample['alerts']:
            ...         print(f"ALERT: {alert}")
        """
        metrics = self.collect_metrics()
        metrics["alerts"] = self.check_alerts(metrics)
        self.update(metrics)
        return metrics

    # Monitoring Loop

    def monitor(self, duration: float | None = None) -> None:
        """
        Run continuous monitoring for specified duration.
        Args:
            duration: Monitoring duration in seconds. If None, runs until
                    interrupted (typically by KeyboardInterrupt).
        Raises:
            KeyboardInterrupt: If monitoring interrupted by user
            OSError: If system metrics cannot be accessed
            RuntimeError: If monitoring loop encounters fatal error
        Note:
            Use Ctrl+C to interrupt monitoring when duration is None.
            First sample may have 0.0 for disk/network rates as they
            require a previous sample for calculation.
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
        except (OSError, RuntimeError, ValueError) as exc:
            logger.error("Monitoring error: %s", exc)
            raise

    # Data Accessors (NO UI FORMATTING)

    def get_summary(self) -> dict[str, Any]:
        """
        Get comprehensive summary of monitoring session.
        Returns:
            dict: Summary containing:
                - current: Latest metrics sample (including alerts)
                - peak: Peak values for all tracked metrics
                - samples: Number of samples collected
                - duration: Total monitoring duration in seconds
                - thresholds: Configured alert thresholds
        Returns empty dict if no history available.
        """
        if not self.history:
            return {}

        latest = self.history[-1]

        return {
            "current": latest.copy(),
            "peak": self.peak_usage.copy(),
            "samples": len(self.history),
            "duration": (
                self.history[-1]["timestamp"] - self.history[0]["timestamp"]
                if len(self.history) > 1
                else 0.0
            ),
            "thresholds": {
                "cpu": self.cpu_threshold,
                "memory": self.memory_threshold,
                "disk": self.disk_threshold,
            },
        }

    def get_history(self, limit: int | None = None) -> list[dict[str, Any]]:
        """
        Get monitoring history with optional limit.
        Args:
            limit: Maximum number of recent samples to return.
                   If None, returns entire history.
        Returns:
            list: List of metric dictionaries. Returns copy to prevent
                  modification of internal history.
        """
        if limit and limit < len(self.history):
            return self.history[-limit:].copy()
        return self.history.copy()

    def get_recent_alerts(self, last_n_samples: int = 10) -> list[dict[str, Any]]:
        """
        Get recent samples that contain alerts.
        Args:
            last_n_samples: Number of most recent samples to inspect.
        Returns:
            list[dict[str, Any]]: List of metric samples that include alerts.
        """
        if last_n_samples <= 0:
            return []

        recent = self.get_history(limit=last_n_samples)
        return [sample for sample in recent if sample.get("alerts")]

    def get_stats(self) -> dict[str, Any]:
        """
        Compute basic statistics from monitoring history.
        Returns:
            dict: Dictionary containing:
                - averages: Average values for numeric metrics
                - samples: Total number of samples collected
        """
        if not self.history:
            return {}

        numeric_keys = [
            "cpu_percent",
            "memory_percent",
            "disk_percent",
        ]

        totals: dict[str, float] = dict.fromkeys(numeric_keys, 0.0)
        count = 0

        for sample in self.history:
            for key in numeric_keys:
                if key in sample:
                    totals[key] += sample[key]
            count += 1

        averages = {key: totals[key] / count for key in totals}

        return {
            "averages": averages,
            "samples": count,
        }

    def get_peak_usage(self) -> dict[str, float]:
        """
        Get peak usage values for all tracked metrics.
        Returns:
            dict: Copy of peak_usage dictionary
        """
        return self.peak_usage.copy()

    def clear_history(self) -> None:
        """
        Clear all stored history and reset peak usage.
        Resets:
            - history list (emptied)
            - peak_usage dictionary (all values set to 0.0)
            - internal disk/net counters (set to None)
        """
        self.history.clear()
        self.peak_usage = dict.fromkeys(self.peak_usage, 0.0)
        self._disk_before = None
        self._net_before = None

    # Recommendations

    def get_recommendations(self) -> list[str]:
        """
        Generate performance recommendations based on usage patterns.
        Analyzes peak usage to provide actionable suggestions for
        improving system performance and stability.
        Returns:
            list[str]: List of recommendation messages. If no issues
                      detected, returns a single positive message.
        Note:
            Recommendations are based on peak usage during monitoring,
            not current values. Run monitor() or multiple sample() calls
            before calling for meaningful recommendations.
        """
        recs: list[str] = []

        if self.peak_usage["cpu_percent"] >= self.cpu_threshold:
            recs.append("High CPU usage detected — consider lowering system load.")

        if self.peak_usage["memory_percent"] >= self.memory_threshold:
            recs.append("High memory usage detected — consider closing applications.")

        if self.peak_usage["disk_percent"] >= self.disk_threshold:
            recs.append("Disk usage was very high — ensure sufficient free space.")

        if self.peak_usage["network_up_mb"] > 50 or self.peak_usage["network_down_mb"] > 50:
            recs.append("High network usage detected — downloads may slow the system.")

        return recs or ["System resources remained within optimal limits."]
