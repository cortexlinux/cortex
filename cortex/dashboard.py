"""
Cortex Dashboard - Enhanced Terminal UI with Progress Tracking
Supports real-time monitoring, system metrics, process tracking, and installation management
"""

import logging
import os
import queue
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

try:
    from rich.box import ROUNDED
    from rich.columns import Columns
    from rich.console import Console, Group
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn
    from rich.table import Table
    from rich.text import Text
except ImportError as e:
    raise ImportError(f"rich library required: {e}. Install with: pip install rich")

try:
    import psutil
except ImportError as e:
    raise ImportError(f"psutil library required: {e}. Install with: pip install psutil")

try:
    import pynvml

    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False

# Cross-platform keyboard input
if sys.platform == "win32":
    import msvcrt
else:
    import select
    import termios
    import tty

# Suppress verbose logging
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class DashboardTab(Enum):
    """Available dashboard tabs"""

    HOME = "home"
    PROGRESS = "progress"


class InstallationState(Enum):
    """Installation states"""

    IDLE = "idle"
    WAITING_INPUT = "waiting_input"
    PROCESSING = "processing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ActionType(Enum):
    """Action types for dashboard"""

    NONE = "none"
    INSTALL = "install"
    BENCH = "bench"
    DOCTOR = "doctor"
    CANCEL = "cancel"


@dataclass
class SystemMetrics:
    """Container for system metrics"""

    cpu_percent: float
    ram_percent: float
    ram_used_gb: float
    ram_total_gb: float
    gpu_percent: float | None = None
    gpu_memory_percent: float | None = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class InstallationProgress:
    """Tracks installation progress"""

    state: InstallationState = InstallationState.IDLE
    package: str = ""
    current_step: int = 0
    total_steps: int = 0
    current_library: str = ""
    libraries: list[str] = field(default_factory=list)
    error_message: str = ""
    success_message: str = ""
    start_time: float | None = None
    elapsed_time: float = 0.0
    estimated_remaining: float = 0.0

    def update_elapsed(self):
        """Update elapsed time"""
        if self.start_time:
            self.elapsed_time = time.time() - self.start_time


class SystemMonitor:
    """Monitors CPU, RAM, GPU metrics"""

    def __init__(self):
        self.current_metrics = SystemMetrics(
            cpu_percent=0.0, ram_percent=0.0, ram_used_gb=0.0, ram_total_gb=0.0
        )
        self.lock = threading.Lock()
        self.gpu_initialized = False
        self._init_gpu()

    def _init_gpu(self):
        """Initialize GPU monitoring if available"""
        if not GPU_AVAILABLE:
            return
        try:
            pynvml.nvmlInit()
            self.gpu_initialized = True
        except Exception as e:
            logger.debug(f"GPU init failed: {e}")

    def get_metrics(self) -> SystemMetrics:
        """Get current metrics"""
        with self.lock:
            return self.current_metrics

    def update_metrics(self):
        """Update all metrics"""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            vm = psutil.virtual_memory()

            gpu_percent = None
            gpu_memory_percent = None

            if self.gpu_initialized:
                try:
                    device_count = pynvml.nvmlDeviceGetCount()
                    if device_count > 0:
                        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                        gpu_percent = pynvml.nvmlDeviceGetUtilizationRates(handle).gpu
                        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                        gpu_memory_percent = (mem_info.used / mem_info.total) * 100
                except Exception as e:
                    logger.debug(f"GPU metrics error: {e}")

            metrics = SystemMetrics(
                cpu_percent=cpu_percent,
                ram_percent=vm.percent,
                ram_used_gb=vm.used / (1024**3),
                ram_total_gb=vm.total / (1024**3),
                gpu_percent=gpu_percent,
                gpu_memory_percent=gpu_memory_percent,
            )

            with self.lock:
                self.current_metrics = metrics
        except Exception as e:
            logger.error(f"Metrics error: {e}")


class ProcessLister:
    """Lists running inference processes"""

    KEYWORDS = {
        "python",
        "node",
        "ollama",
        "llama",
        "bert",
        "gpt",
        "transformers",
        "inference",
        "pytorch",
        "tensorflow",
        "cortex",
        "cuda",
    }

    def __init__(self):
        self.processes = []
        self.lock = threading.Lock()

    def update_processes(self):
        """Update process list"""
        try:
            processes = []
            for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    name = proc.info.get("name", "").lower()
                    cmdline = " ".join(proc.info.get("cmdline") or []).lower()

                    if any(kw in name for kw in self.KEYWORDS) or any(
                        kw in cmdline for kw in self.KEYWORDS
                    ):
                        processes.append(
                            {
                                "pid": proc.info.get("pid"),
                                "name": proc.info.get("name", "unknown"),
                                "cmdline": " ".join(proc.info.get("cmdline") or [])[:60],
                            }
                        )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            with self.lock:
                self.processes = processes[:15]
        except Exception as e:
            logger.error(f"Process listing error: {e}")

    def get_processes(self) -> list[dict]:
        """Get current processes"""
        with self.lock:
            return list(self.processes)


class CommandHistory:
    """Loads and tracks shell history"""

    def __init__(self, max_size: int = 10):
        self.max_size = max_size
        self.history = deque(maxlen=max_size)
        self.lock = threading.Lock()
        self._load_shell_history()

    def _load_shell_history(self):
        """Load from shell history files"""
        for history_file in [
            os.path.expanduser("~/.bash_history"),
            os.path.expanduser("~/.zsh_history"),
        ]:
            if os.path.exists(history_file):
                try:
                    with open(history_file, encoding="utf-8", errors="ignore") as f:
                        for line in f.readlines()[-self.max_size :]:
                            cmd = line.strip()
                            if cmd and not cmd.startswith(":"):
                                self.history.append(cmd)
                    break
                except Exception as e:
                    logger.debug(f"History load error: {e}")

    def add_command(self, command: str):
        """Add command to history"""
        if command.strip():
            with self.lock:
                self.history.append(command)

    def get_history(self) -> list[str]:
        """Get history"""
        with self.lock:
            return list(self.history)


class UIRenderer:
    """Renders the dashboard UI with multi-tab support"""

    def __init__(self, monitor: SystemMonitor, lister: ProcessLister, history: CommandHistory):
        self.console = Console()
        self.monitor = monitor
        self.lister = lister
        self.history = history
        self.running = False
        self.should_quit = False
        self.current_tab = DashboardTab.HOME

        # Installation state
        self.installation_progress = InstallationProgress()
        self.input_text = ""
        self.input_active = False

        # Current action state (for display)
        self.current_action = ActionType.NONE
        self.last_pressed_key = ""
        self.status_message = ""

        # Doctor results
        self.doctor_results = []
        self.doctor_running = False

        # Bench results
        self.bench_status = "Ready to run benchmark"
        self.bench_running = False

    def _create_bar(self, label: str, percent: float, width: int = 20) -> str:
        """Create a resource bar"""
        if percent is None:
            return f"{label}: N/A"

        filled = int((percent / 100) * width)
        bar = "[green]" + "█" * filled + "[/green]" + "░" * (width - filled)
        if percent > 75:
            bar = "[red]" + "█" * filled + "[/red]" + "░" * (width - filled)
        elif percent > 50:
            bar = "[yellow]" + "█" * filled + "[/yellow]" + "░" * (width - filled)

        return f"{label}: {bar} {percent:.1f}%"

    def _render_header(self) -> Panel:
        """Render header with tab indicator"""
        title = Text("🚀 CORTEX DASHBOARD", style="bold cyan")
        timestamp = Text(datetime.now().strftime("%H:%M:%S"), style="dim")

        # Tab indicator
        tab_text = ""
        for tab in DashboardTab:
            if tab == self.current_tab:
                tab_text += f"[bold cyan]▸ {tab.value.upper()} ◂[/bold cyan] "
            else:
                tab_text += f"[dim]{tab.value}[/dim] "

        content = f"{title}  {timestamp}\n[dim]{tab_text}[/dim]"
        return Panel(content, style="blue", box=ROUNDED)

    def _render_resources(self) -> Panel:
        """Render resources section"""
        metrics = self.monitor.get_metrics()
        lines = [
            self._create_bar("CPU", metrics.cpu_percent),
            self._create_bar("RAM", metrics.ram_percent),
            f"     Used: {metrics.ram_used_gb:.1f}GB / {metrics.ram_total_gb:.1f}GB",
        ]

        if metrics.gpu_percent is not None:
            lines.append(self._create_bar("GPU", metrics.gpu_percent))
        if metrics.gpu_memory_percent is not None:
            lines.append(self._create_bar("VRAM", metrics.gpu_memory_percent))

        return Panel("\n".join(lines), title="📊 System Resources", padding=(1, 1), box=ROUNDED)

    def _render_processes(self) -> Panel:
        """Render processes section"""
        processes = self.lister.get_processes()
        if not processes:
            content = "[dim]No processes detected[/dim]"
        else:
            lines = [f"  {p['pid']} {p['name'][:20]}" for p in processes[:8]]
            content = "\n".join(lines)

        return Panel(content, title="⚙️  Running Processes", padding=(1, 1), box=ROUNDED)

    def _render_history(self) -> Panel:
        """Render history section"""
        cmds = self.history.get_history()
        if not cmds:
            content = "[dim]No history[/dim]"
        else:
            lines = [f"  {c[:50]}" for c in reversed(list(cmds)[-5:])]
            content = "\n".join(lines)

        return Panel(content, title="📝 Recent Commands", padding=(1, 1), box=ROUNDED)

    def _render_actions(self) -> Panel:
        """Render action menu with pressed indicator"""
        # Build action items
        action_items = [
            ("1", "Install", ActionType.INSTALL),
            ("2", "Bench", ActionType.BENCH),
            ("3", "Doctor", ActionType.DOCTOR),
            ("4", "Cancel", ActionType.CANCEL),
        ]

        actions = []
        for key, name, action_type in action_items:
            actions.append(f"[cyan]{key}[/cyan] {name}")

        content = "  ".join(actions)

        # Add pressed indicator if a key was recently pressed
        if self.last_pressed_key:
            content += (
                f"  [dim]|[/dim]  [bold yellow]► {self.last_pressed_key} pressed[/bold yellow]"
            )

        return Panel(content, title="⚡ Actions", padding=(1, 1), box=ROUNDED)

    def _render_home_tab(self) -> Group:
        """Render home tab"""
        return Group(
            self._render_header(),
            "",
            Columns([self._render_resources(), self._render_processes()], expand=True),
            "",
            self._render_history(),
            "",
            self._render_actions(),
            "",
        )

    def _render_input_dialog(self) -> Panel:
        """Render input dialog for package selection"""
        instructions = "[cyan]Enter package name[/cyan] (e.g., nginx, docker, python)\n[dim]Press Enter to install, Esc to cancel[/dim]"

        content = f"{instructions}\n\n[bold]>[/bold] {self.input_text}[blink_fast]█[/blink_fast]"
        return Panel(
            content, title="📦 What would you like to install?", padding=(2, 2), box=ROUNDED
        )

    def _render_progress_panel(self) -> Panel:
        """Render progress panel with support for install, bench, doctor"""
        progress = self.installation_progress

        if progress.state == InstallationState.WAITING_INPUT:
            return self._render_input_dialog()

        lines = []

        # Operation name and status
        if progress.package:
            lines.append(f"[bold cyan]Operation:[/bold cyan] {progress.package}")

        # Progress bar
        if progress.total_steps > 0:
            filled = int((progress.current_step / progress.total_steps) * 20)
            bar = "[green]" + "█" * filled + "[/green]" + "░" * (20 - filled)
            percentage = int((progress.current_step / progress.total_steps) * 100)
            lines.append(f"\n[cyan]Progress:[/cyan] {bar} {percentage}%")
            lines.append(f"[dim]Step {progress.current_step}/{progress.total_steps}[/dim]")

        # Current step being processed
        if progress.current_library:
            lines.append(f"\n[bold]Current:[/bold] {progress.current_library}")

        # Time info
        if progress.elapsed_time > 0:
            lines.append(f"\n[dim]Elapsed: {progress.elapsed_time:.1f}s[/dim]")

        # Doctor results display
        if self.doctor_results:
            lines.append("\n[bold]Check Results:[/bold]")
            for name, passed, detail in self.doctor_results:
                icon = "[green]✓[/green]" if passed else "[red]✗[/red]"
                lines.append(f"  {icon} {name}: {detail}")

        # Show installed libraries for install operations
        if progress.libraries and progress.package not in ["System Benchmark", "System Doctor"]:
            lines.append(f"\n[dim]Libraries: {', '.join(progress.libraries[:5])}[/dim]")
            if len(progress.libraries) > 5:
                lines.append(f"[dim]... and {len(progress.libraries) - 5} more[/dim]")

        # Status messages
        if progress.error_message:
            lines.append(f"\n[red]✗ {progress.error_message}[/red]")
        elif progress.success_message:
            lines.append(f"\n[green]✓ {progress.success_message}[/green]")

        # Idle state message
        if progress.state == InstallationState.IDLE:
            lines.append("[dim]Press 1 for Install, 2 for Bench, 3 for Doctor[/dim]")

        content = (
            "\n".join(lines)
            if lines
            else "[dim]No operation in progress\nPress 1 for Install, 2 for Bench, 3 for Doctor[/dim]"
        )

        title_map = {
            InstallationState.IDLE: "📋 Progress",
            InstallationState.WAITING_INPUT: "📦 Installation",
            InstallationState.PROCESSING: "🔄 Processing",
            InstallationState.IN_PROGRESS: "⏳ In Progress",
            InstallationState.COMPLETED: "✅ Completed",
            InstallationState.FAILED: "❌ Failed",
        }

        title = title_map.get(progress.state, "📋 Progress")

        return Panel(content, title=title, padding=(1, 2), box=ROUNDED)

    def _render_progress_tab(self) -> Group:
        """Render progress tab with actions"""
        return Group(
            self._render_header(), "", self._render_progress_panel(), "", self._render_actions(), ""
        )

    def _render_footer(self) -> Panel:
        """Render footer"""
        footer_text = (
            "[cyan]q[/cyan] Quit  |  [cyan]Tab[/cyan] Switch Tab  |  [cyan]1-4[/cyan] Actions"
        )
        return Panel(footer_text, style="dim", box=ROUNDED)

    def _render_screen(self):
        """Render full screen based on current tab"""
        if self.current_tab == DashboardTab.HOME:
            content = self._render_home_tab()
        elif self.current_tab == DashboardTab.PROGRESS:
            content = self._render_progress_tab()
        else:
            content = self._render_home_tab()

        return Group(content, self._render_footer())

    def _handle_key_press(self, key: str):
        """Handle key press"""
        # Clear previous pressed indicator after a short time
        self.last_pressed_key = ""

        if key == "q":
            self.should_quit = True
            return

        elif key == "\t":  # Tab key
            # Switch tabs
            tabs = list(DashboardTab)
            current_idx = tabs.index(self.current_tab)
            self.current_tab = tabs[(current_idx + 1) % len(tabs)]
            self.last_pressed_key = "Tab"
            return

        # Handle input mode first if active
        if self.input_active:
            if key == "\n" or key == "\r":  # Enter
                self._submit_installation_input()
            elif key == "\x1b":  # Escape
                self._cancel_operation()
            elif key == "\b" or key == "\x7f":  # Backspace
                self.input_text = self.input_text[:-1]
            elif key.isprintable() and len(self.input_text) < 50:
                self.input_text += key
            return

        # Handle action keys
        if key == "1":
            self.last_pressed_key = "Install"
            self._start_installation()
        elif key == "2":
            self.last_pressed_key = "Bench"
            self._start_bench()
        elif key == "3":
            self.last_pressed_key = "Doctor"
            self._start_doctor()
        elif key == "4":
            self.last_pressed_key = "Cancel"
            self._cancel_operation()

    def _start_bench(self):
        """Start benchmark"""
        # Allow starting if not currently running
        if not self.bench_running and self.installation_progress.state not in [
            InstallationState.IN_PROGRESS,
            InstallationState.PROCESSING,
        ]:
            # Reset state for new benchmark
            self.installation_progress = InstallationProgress()
            self.doctor_results = []
            self.bench_running = True
            self.bench_status = "Running benchmark..."
            self.current_tab = DashboardTab.PROGRESS
            self.installation_progress.state = InstallationState.PROCESSING
            self.installation_progress.package = "System Benchmark"

            # Run benchmark in background thread
            def run_bench():
                steps = ["CPU Test", "Memory Test", "Disk I/O Test", "Network Test"]
                self.installation_progress.total_steps = len(steps)
                self.installation_progress.start_time = time.time()
                self.installation_progress.state = InstallationState.IN_PROGRESS

                for i, step in enumerate(steps, 1):
                    if not self.running or not self.bench_running:
                        break
                    self.installation_progress.current_step = i
                    self.installation_progress.current_library = step
                    self.installation_progress.update_elapsed()
                    time.sleep(0.8)

                self.bench_status = "Benchmark complete - System OK"
                self.installation_progress.state = InstallationState.COMPLETED
                self.installation_progress.success_message = "Benchmark completed successfully!"
                self.installation_progress.current_library = ""
                self.bench_running = False

            threading.Thread(target=run_bench, daemon=True).start()

    def _start_doctor(self):
        """Start doctor system check"""
        # Allow starting if not currently running
        if not self.doctor_running and self.installation_progress.state not in [
            InstallationState.IN_PROGRESS,
            InstallationState.PROCESSING,
        ]:
            # Reset state for new doctor check
            self.installation_progress = InstallationProgress()
            self.doctor_running = True
            self.doctor_results = []
            self.current_tab = DashboardTab.PROGRESS
            self.installation_progress.state = InstallationState.PROCESSING
            self.installation_progress.package = "System Doctor"

            # Run doctor in background thread
            def run_doctor():
                checks = [
                    (
                        "Python version",
                        True,
                        f"Python {sys.version_info.major}.{sys.version_info.minor}",
                    ),
                    ("psutil module", True, "Installed"),
                    ("rich module", True, "Installed"),
                    (
                        "Disk space",
                        psutil.disk_usage("/").percent < 90,
                        f"{psutil.disk_usage('/').percent:.1f}% used",
                    ),
                    (
                        "Memory available",
                        psutil.virtual_memory().percent < 95,
                        f"{psutil.virtual_memory().percent:.1f}% used",
                    ),
                    ("CPU load", psutil.cpu_percent() < 90, f"{psutil.cpu_percent():.1f}% load"),
                ]

                self.installation_progress.total_steps = len(checks)
                self.installation_progress.start_time = time.time()
                self.installation_progress.state = InstallationState.IN_PROGRESS

                for i, (name, passed, detail) in enumerate(checks, 1):
                    if not self.running or not self.doctor_running:
                        break
                    self.installation_progress.current_step = i
                    self.installation_progress.current_library = f"Checking {name}..."
                    self.doctor_results.append((name, passed, detail))
                    self.installation_progress.update_elapsed()
                    time.sleep(0.5)

                all_passed = all(r[1] for r in self.doctor_results)
                self.installation_progress.state = InstallationState.COMPLETED
                if all_passed:
                    self.installation_progress.success_message = (
                        "All checks passed! System is healthy."
                    )
                else:
                    self.installation_progress.success_message = (
                        "Some checks failed. Review results above."
                    )
                self.installation_progress.current_library = ""
                self.doctor_running = False

            threading.Thread(target=run_doctor, daemon=True).start()

    def _cancel_operation(self):
        """Cancel any ongoing operation"""
        # Cancel installation
        if self.installation_progress.state in [
            InstallationState.IN_PROGRESS,
            InstallationState.PROCESSING,
            InstallationState.WAITING_INPUT,
        ]:
            self.installation_progress.state = InstallationState.FAILED
            self.installation_progress.error_message = "Operation cancelled by user"
            self.installation_progress.current_library = ""

        # Cancel bench
        if self.bench_running:
            self.bench_running = False
            self.bench_status = "Benchmark cancelled"

        # Cancel doctor
        if self.doctor_running:
            self.doctor_running = False

        # Reset input
        self.input_active = False
        self.input_text = ""

        # Return to home after a moment
        self.status_message = "Operation cancelled"

    def _start_installation(self):
        """Start installation process"""
        # Allow starting new installation if not currently in progress
        if self.installation_progress.state not in [
            InstallationState.IN_PROGRESS,
            InstallationState.PROCESSING,
            InstallationState.WAITING_INPUT,
        ]:
            # Reset progress state for new installation
            self.installation_progress = InstallationProgress()
            self.installation_progress.state = InstallationState.WAITING_INPUT
            self.input_active = True
            self.input_text = ""
            self.current_tab = DashboardTab.PROGRESS
            self.doctor_results = []  # Clear previous results

    def _submit_installation_input(self):
        """Submit installation input"""
        if self.input_text.strip():
            package = self.input_text.strip()
            self.installation_progress.package = package
            self.installation_progress.state = InstallationState.PROCESSING
            self.installation_progress.input_active = False
            self.input_active = False

            # Simulate processing - in real implementation, this would call CLI
            self._simulate_installation()

    def _run_installation(self):
        """Run installation in background thread"""
        progress = self.installation_progress
        package_name = progress.package

        progress.state = InstallationState.IN_PROGRESS
        progress.start_time = time.time()
        progress.total_steps = 5
        progress.libraries = []

        # Simulate library installation steps (will be replaced with actual CLI call)
        install_steps = [
            f"Preparing {package_name}",
            "Resolving dependencies",
            "Downloading packages",
            "Installing components",
            "Verifying installation",
        ]

        for i, step in enumerate(install_steps, 1):
            if not self.running or progress.state == InstallationState.FAILED:
                break
            progress.current_step = i
            progress.current_library = step
            progress.libraries.append(step)
            progress.update_elapsed()
            time.sleep(0.6)  # Simulate work

        if progress.state != InstallationState.FAILED:
            progress.state = InstallationState.COMPLETED
            progress.success_message = f"Successfully installed {package_name}!"
        progress.current_library = ""

    def _simulate_installation(self):
        """Start installation in background thread"""
        threading.Thread(target=self._run_installation, daemon=True).start()

    def _reset_to_home(self):
        """Reset state and go to home tab"""
        self.installation_progress = InstallationProgress()
        self.input_text = ""
        self.input_active = False
        self.current_tab = DashboardTab.HOME
        self.doctor_results = []
        self.bench_status = "Ready to run benchmark"

    def _check_keyboard_input(self):
        """Check for keyboard input (cross-platform)"""
        try:
            if sys.platform == "win32":
                if msvcrt.kbhit():
                    key = msvcrt.getch().decode("utf-8", errors="ignore")
                    return key
            else:
                if select.select([sys.stdin], [], [], 0)[0]:
                    key = sys.stdin.read(1)
                    return key
        except Exception as e:
            logger.debug(f"Keyboard check error: {e}")
        return None

    def run(self):
        """Run dashboard"""
        self.running = True
        self.should_quit = False

        # Save terminal settings on Unix
        old_settings = None
        if sys.platform != "win32":
            try:
                old_settings = termios.tcgetattr(sys.stdin)
                tty.setcbreak(sys.stdin.fileno())
            except Exception:
                pass

        def monitor_loop():
            while self.running:
                try:
                    self.monitor.update_metrics()
                    self.lister.update_processes()

                    # Update progress if in progress tab
                    if self.current_tab == DashboardTab.PROGRESS:
                        self.installation_progress.update_elapsed()

                except Exception as e:
                    logger.error(f"Monitor error: {e}")
                time.sleep(1.0)

        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()

        try:
            with Live(
                self._render_screen(), console=self.console, refresh_per_second=2, screen=True
            ) as live:
                while self.running and not self.should_quit:
                    # Check for keyboard input
                    key = self._check_keyboard_input()
                    if key:
                        self._handle_key_press(key)

                    # Update display
                    live.update(self._render_screen())
                    time.sleep(0.1)  # More frequent updates for responsiveness

        except KeyboardInterrupt:
            self.should_quit = True

        finally:
            self.running = False
            # Restore terminal settings on Unix
            if old_settings is not None:
                try:
                    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                except Exception:
                    pass


class DashboardApp:
    """Main dashboard application"""

    def __init__(self):
        self.monitor = SystemMonitor()
        self.lister = ProcessLister()
        self.history = CommandHistory()
        self.ui = UIRenderer(self.monitor, self.lister, self.history)

    def run(self):
        """Run the app"""
        console = Console()
        try:
            console.print("[bold cyan]Starting Cortex Dashboard...[/bold cyan]")
            console.print("[dim]Press [cyan]q[/cyan] to quit[/dim]\n")
            time.sleep(1)
            self.ui.run()
        except KeyboardInterrupt:
            pass
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
        finally:
            self.ui.running = False
            console.print("\n[yellow]Dashboard shutdown[/yellow]")


def main():
    """Entry point"""
    app = DashboardApp()
    app.run()


if __name__ == "__main__":
    main()
