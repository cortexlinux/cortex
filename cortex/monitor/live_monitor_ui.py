"""
UI components for system monitoring display.
Separates UI logic from monitoring logic.
"""

import threading
import time
from typing import Any

import psutil
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from cortex.monitor.resource_monitor import ResourceMonitor


def bar(percent: float, width: int = 10) -> str:
    """Create a text-based progress bar."""
    percent = max(0, min(100, percent))
    filled = int((percent / 100) * width)
    empty = width - filled
    return "█" * filled + "░" * empty


class MonitorUI:
    """UI formatting for monitoring displays."""

    @staticmethod
    def create_progress_bar(percent: float, width: int = 10) -> str:
        """Create a text-based progress bar.

        Args:
            percent: Percentage value (0-100)
            width: Width of the bar in characters

        Returns:
            Progress bar string
        """
        return bar(percent, width)

    @staticmethod
    def format_installing_header(name: str) -> str:
        """
        Format the installation header.

        Args:
            name: Name of the package being installed (e.g. CUDA)

        Returns:
            Formatted installing header string
        """
        return f"Installing {name}..."

    @classmethod
    def format_system_health(cls, metrics: dict[str, Any]) -> str:
        """Format system health output for `cortex monitor` command.

        Returns the exact format from the example:
          CPU:     45% (4 cores)
          RAM:     8.2/16 GB (51%)
          Disk:    120/500 GB (24%)
          Network: 2.5 MB/s ↓  0.8 MB/s ↑
        """
        cpu_cores = psutil.cpu_count(logical=True)

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
        """Format real-time metrics during installation.

        Returns the exact format from the example:
          CPU: ████████░░ 80% (compilation)
          RAM: ██████████ 12.5/16 GB
          Disk: Writing... 2.1 GB/3.5 GB
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
        """Format peak usage summary after installation.

        Returns the exact format from the example:
        📊 Peak usage: CPU 95%, RAM 13.2 GB
        """
        cpu = peak_metrics.get("cpu_percent", 0)
        ram = peak_metrics.get("memory_used_gb", 0)
        return f"📊 Peak usage: CPU {cpu:.0f}%, RAM {ram:.1f} GB"

    @classmethod
    def format_installation_complete(cls) -> str:
        """Format installation complete message.

        Returns the exact format from the example:
        ✓  Installation complete
        """
        return "✓  Installation complete"


class LiveMonitorUI:
    """
    Live-rendered UI for installation monitoring.
    Pure UI layer — no system logic here.
    """

    def __init__(self, monitor: ResourceMonitor, title: str = "Installing..."):
        self.monitor = monitor
        self.title = title
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _render(self) -> Panel:
        if not self.monitor.history:
            return Panel("Collecting metrics...", border_style="cyan")

        m = self.monitor.history[-1]

        cpu = m["cpu_percent"]
        ram_used = m["memory_used_gb"]
        ram_total = m["memory_total_gb"]
        ram_percent = m["memory_percent"]
        disk_used = m["disk_used_gb"]
        disk_total = m["disk_total_gb"]
        disk_percent = m["disk_percent"]

        # Network metrics (if available)
        net_down = m.get("network_down_mb", 0)
        net_up = m.get("network_up_mb", 0)

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

    def start(self) -> None:
        """Start the monitoring UI."""
        self._stop_event.clear()

        def loop():
            with Live(self._render(), refresh_per_second=4, screen=False) as live:
                while not self._stop_event.is_set():
                    live.update(self._render())
                    time.sleep(0.5)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the monitoring UI."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
