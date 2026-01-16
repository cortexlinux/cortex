"""
UI components for system monitoring display.
Separates UI logic from monitoring logic.
This module provides user interface components for displaying system
monitoring data. It handles all formatting and display logic, keeping
UI concerns separate from data collection in ResourceMonitor.
"""

import threading
import time
from typing import Any

from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from cortex.monitor.resource_monitor import ResourceMonitor


def bar(percent: float, width: int = 10) -> str:
    """
    Create a text-based progress bar.
    Args:
        percent: Percentage value (0-100)
        width: Width of the bar in characters
    Returns:
        Progress bar string with filled and empty portions
    Example:
        >>> bar(75, 10)
        '███████░░░'
    """
    percent = max(0, min(100, percent))
    filled = int((percent / 100) * width)
    empty = width - filled
    return "█" * filled + "░" * empty


class MonitorUI:
    """
    Static UI formatting methods for monitoring displays.
    This class provides methods to format monitoring data for different
    contexts (command output, installation displays, summaries).
    All methods are static/class methods to emphasize their pure formatting
    nature without state.
    """

    @staticmethod
    def create_progress_bar(percent: float, width: int = 10) -> str:
        """
        Create a text-based progress bar.
        Args:
            percent: Percentage value (0-100)
            width: Width of the bar in characters
        Returns:
            Progress bar string
        Example:
            >>> MonitorUI.create_progress_bar(80, 10)
            '████████░░'
        """
        return bar(percent, width)

    @staticmethod
    def format_installing_header(name: str) -> str:
        """
        Format the installation header.
        Args:
            name: Name of the package being installed (e.g., CUDA)
        Returns:
            Formatted installing header string
        Example:
            >>> MonitorUI.format_installing_header("CUDA")
            'Installing CUDA...'
        """
        return f"Installing {name}..."

    @classmethod
    def format_system_health(cls, metrics: dict[str, Any]) -> str:
        """
        Format system health output for `cortex monitor` command.
        Args:
            metrics: Dictionary containing system metrics with keys:
                    - cpu_percent: CPU usage percentage
                    - memory_used_gb: Used memory in GB
                    - memory_total_gb: Total memory in GB
                    - memory_percent: Memory usage percentage
                    - disk_used_gb: Used disk space in GB
                    - disk_total_gb: Total disk space in GB
                    - disk_percent: Disk usage percentage
                    - network_down_mb: Download rate in MB/s
                    - network_up_mb: Upload rate in MB/s
                    - cpu_cores: Number of CPU cores (optional)
        Returns:
            Formatted multi-line string
        """
        cpu_cores = metrics.get("cpu_cores", "?")

        lines = [
            f"  CPU:     {metrics['cpu_percent']:.0f}% ({cpu_cores} cores)",
            f"  RAM:     {metrics['memory_used_gb']:.1f}/{metrics['memory_total_gb']:.1f} GB "
            f"({metrics['memory_percent']:.0f}%)",
            f"  Disk:    {metrics['disk_used_gb']:.0f}/{metrics['disk_total_gb']:.0f} GB "
            f"({metrics['disk_percent']:.0f}%)",
            f"  Network: {metrics['network_down_mb']:.1f} MB/s ↓  "
            f"{metrics['network_up_mb']:.1f} MB/s ↑",
        ]

        return "\n".join(lines)

    @classmethod
    def format_installation_metrics(cls, metrics: dict[str, Any]) -> str:
        """
        Format real-time metrics during installation.
        Returns the exact format:
          CPU: ████████░░ 80% (compilation)
          RAM: ██████████ 12.5/16 GB
          Disk: Writing... 2.1 GB/3.5 GB
        Args:
            metrics: Dictionary containing system metrics
        Returns:
            Formatted installation metrics string
        """
        cpu_bar = cls.create_progress_bar(metrics["cpu_percent"], 10)
        ram_bar = cls.create_progress_bar(metrics["memory_percent"], 10)

        lines = [
            f"  CPU: {cpu_bar} {metrics['cpu_percent']:.0f}% (compilation)",
            f"  RAM: {ram_bar} {metrics['memory_used_gb']:.1f}/{metrics['memory_total_gb']:.1f} GB",
            f"  Disk: Writing... {metrics['disk_used_gb']:.1f}/{metrics['disk_total_gb']:.1f} GB",
        ]

        return "\n".join(lines)

    @classmethod
    def format_peak_usage(cls, peak_metrics: dict[str, float]) -> str:
        """
        Format peak usage summary after installation.
        Returns the exact format:
        📊 Peak usage: CPU 95%, RAM 13.2 GB
        Args:
            peak_metrics: Dictionary containing peak usage values
        Returns:
            Formatted peak usage string
        """
        cpu = peak_metrics.get("cpu_percent", 0)
        ram = peak_metrics.get("memory_used_gb", 0)
        return f"📊 Peak usage: CPU {cpu:.0f}%, RAM {ram:.1f} GB"

    @classmethod
    def format_installation_complete(cls) -> str:
        """
        Format installation complete message.
        Returns the exact format:
        ✓  Installation complete
        Returns:
            Installation complete message
        """
        return "✓  Installation complete"


class LiveMonitorUI:
    """
    Live-rendered UI for installation monitoring.
    Provides a real-time updating display of system metrics during
    installations. This is a pure UI component that renders data
    provided by ResourceMonitor.
    Attributes:
        monitor (ResourceMonitor): Monitoring instance providing data
        title (str): Display title for the UI
        _stop_event (threading.Event): Event to signal UI thread to stop
        _thread (threading.Thread | None): Background UI thread
    Example:
        >>> monitor = ResourceMonitor()
        >>> ui = LiveMonitorUI(monitor, "Installing CUDA...")
        >>> ui.start()
        >>> # Installation happens here
        >>> ui.stop()
    """

    def __init__(self, monitor: ResourceMonitor, title: str = "Installing..."):
        """
        Initialize a LiveMonitorUI instance.
        Args:
            monitor: ResourceMonitor instance providing metrics data
            title: Display title for the UI panel
        """
        self.monitor = monitor
        self.title = title
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _render(self) -> Panel:
        """
        Render the current monitoring state as a Rich Panel.
        Returns:
            Panel: Rich Panel object ready for display
        Note:
            This method is thread-safe and handles missing data gracefully.
            It accesses monitor.history with bounds checking.
        """
        # Safely access the latest metrics with bounds checking
        latest_metrics = self._get_latest_metrics()
        if not latest_metrics:
            return Panel("Collecting metrics...", border_style="cyan")

        cpu = latest_metrics["cpu_percent"]
        ram_used = latest_metrics["memory_used_gb"]
        ram_total = latest_metrics["memory_total_gb"]
        ram_percent = latest_metrics["memory_percent"]
        disk_used = latest_metrics["disk_used_gb"]
        disk_total = latest_metrics["disk_total_gb"]
        disk_percent = latest_metrics["disk_percent"]

        # Network metrics (if available)
        net_down = latest_metrics.get("network_down_mb", 0)
        net_up = latest_metrics.get("network_up_mb", 0)

        text = Text()
        text.append(f"{self.title}\n\n", style="bold")

        # CPU
        text.append(f"CPU:  {bar(cpu)} {cpu:.0f}%\n")

        # RAM - add check for zero division
        if ram_total > 0:
            text.append(
                f"RAM:  {bar(ram_percent)} {ram_used:.1f}/{ram_total:.1f} GB ({ram_percent:.0f}%)\n"
            )
        else:
            text.append(f"RAM:  {ram_used:.1f} GB (total unavailable)\n")

        # Disk
        if disk_total > 0:
            text.append(
                f"Disk: {bar(disk_percent)} {disk_used:.1f}/{disk_total:.1f} GB ({disk_percent:.0f}%)\n"
            )
        else:
            text.append(f"Disk: {disk_used:.1f} GB (total unavailable)\n")

        # Network
        if net_down > 0 or net_up > 0:
            text.append(f"Net:  ↓{net_down:.1f} MB/s  ↑{net_up:.1f} MB/s\n")

        return Panel(text, border_style="cyan")

    def _get_latest_metrics(self) -> dict[str, Any] | None:
        """
        Safely get the latest metrics from monitor history.
        Returns:
            Latest metrics dictionary or None if no data available
        Note:
            This method handles thread safety by using a copy of the
            history and bounds checking.
        """
        try:
            # Use get_history to get a copy for thread safety
            history = self.monitor.get_history(limit=1)
            if history:
                return history[0].copy()
        except (IndexError, AttributeError, TypeError):
            pass
        return None

    def start(self) -> None:
        """
        Start the monitoring UI.
        Spawns a background thread that continuously renders the
        monitoring display until stop() is called.
        Raises:
            RuntimeError: If UI is already running
        """
        if self._thread and self._thread.is_alive():
            raise RuntimeError("LiveMonitorUI is already running")

        self._stop_event.clear()

        def loop() -> None:
            """Main UI rendering loop."""
            with Live(self._render(), refresh_per_second=4, screen=False) as live:
                while not self._stop_event.is_set():
                    try:
                        live.update(self._render())
                        time.sleep(0.25)  # 4 FPS
                    except (KeyboardInterrupt, SystemExit):
                        break
                    except Exception as exc:
                        # Log but continue rendering
                        print(f"UI rendering error: {exc}")
                        time.sleep(0.5)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """
        Stop the monitoring UI.
        Signals the UI thread to stop and waits for it to finish
        with a timeout to prevent hanging.
        """
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
