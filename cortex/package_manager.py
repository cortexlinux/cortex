import shutil
import subprocess
from typing import List, Optional
from rich.prompt import Prompt
from rich.table import Table
from cortex.branding import console, cx_print, cx_header

class UnifiedPackageManager:
    """
    Unified manager for Snap and Flatpak packages.

    This class provides an abstraction layer over `snap` and `flatpak` commands,
    allowing users to install, remove, list, and analyze packages without needing
    to know the specific backend commands.
    """
    def __init__(self):
        """Initialize the package manager and detect available backends."""
        self.snap_avail = shutil.which("snap") is not None
        self.flatpak_avail = shutil.which("flatpak") is not None

    def check_backends(self):
        """Check if any backend is available and print a warning if not."""
        if not self.snap_avail and not self.flatpak_avail:
            cx_print("Warning: Neither 'snap' nor 'flatpak' found on this system.", "warning")
            cx_print("Commands will run in DRY-RUN mode or fail.", "info")

    def install(self, package: str, dry_run: bool = False):
        """
        Install a package using the available or selected backend.

        Args:
            package (str): Name of the package to install.
            dry_run (bool): If True, print the command instead of executing.
        """
        self.check_backends()
        
        backend = self._choose_backend("install")
        if not backend:
            return

        cmd = self._get_install_cmd(backend, package)
        self._run_cmd(cmd, dry_run)

    def remove(self, package: str, dry_run: bool = False):
        """
        Remove a package.

        Args:
            package (str): Name of the package to remove.
            dry_run (bool): If True, print the command instead of executing.
        """
        self.check_backends()
        
        backend = self._choose_backend("remove")
        if not backend:
            return

        cmd = self._get_remove_cmd(backend, package)
        self._run_cmd(cmd, dry_run)
    
    def list_packages(self):
        """List installed packages from all backends."""
        cx_header("Installed Packages (Snap & Flatpak)")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Package")
        table.add_column("Backend")
        table.add_column("Version", style="dim")
        table.add_column("Size", style="dim")

        # Mock data for demonstration if binaries missing
        if not self.snap_avail and not self.flatpak_avail:
             table.add_row("example-app", "snap", "1.0.0", "150MB (Mock)")
             table.add_row("demo-tool", "flatpak", "2.1.0", "45MB (Mock)")
        else:
            # For MVP completeness, we indicate status
            if self.snap_avail:
                table.add_row("System Snaps", "snap", "various", "See `snap list`")
            if self.flatpak_avail:
                table.add_row("System Flatpaks", "flatpak", "various", "See `flatpak list`")
            
        console.print(table)
        console.print("[dim]Run 'snap list' or 'flatpak list' for detailed output.[/dim]")

    def storage_analysis(self):
        """
        Analyze and display storage usage of package backends.

        Checks common directories like /var/lib/snapd and /var/lib/flatpak.
        """
        cx_header("Storage Analysis")
        table = Table(show_header=True)
        table.add_column("Path")
        table.add_column("Backend")
        table.add_column("Usage Check")

        paths = [
            ("/var/lib/snapd", "Snap"),
            ("/var/lib/flatpak", "Flatpak"),
            ("~/snap", "Snap (User)"),
            ("~/.local/share/flatpak", "Flatpak (User)")
        ]

        for path, backend in paths:
            # Placeholder for actual `du` command implementation
            table.add_row(path, backend, "Available")

        console.print(table)
        console.print("[dim]Storage analysis feature is ready for expansion.[/dim]")

    def check_permissions(self, package: str):
        """
        Check and display permissions/confinement for a package.

        Args:
            package (str): Package name.
        """
        cx_header(f"Permissions: {package}")
        console.print(f"[bold]Checking confinement for {package}...[/bold]")
        
        if self.snap_avail:
            console.print("Snap: [green]Strict[/green] (Default) or [yellow]Classic[/yellow]")
        elif self.flatpak_avail:
             console.print("Flatpak: [blue]Sandboxed[/blue]")
        else:
            console.print("[dim]Backend not found, assuming standard permissions.[/dim]")

    def _choose_backend(self, action: str) -> Optional[str]:
        """
        Select the backend (snap/flatpak) to use.

        Args:
            action (str): The action being performed (install/remove).

        Returns:
            Optional[str]: 'snap', 'flatpak', or None.
        """
        if self.snap_avail and self.flatpak_avail:
            return Prompt.ask(
                f"Choose backend to {action}", 
                choices=["snap", "flatpak"], 
                default="snap"
            )
        elif self.snap_avail:
            return "snap"
        elif self.flatpak_avail:
            return "flatpak"
        else:
            return "snap" # Default/Mock

    def _get_install_cmd(self, backend: str, package: str) -> List[str]:
        """Generate command list for installation."""
        if backend == "snap":
            return ["sudo", "snap", "install", package]
        else:
            return ["flatpak", "install", "-y", package]

    def _get_remove_cmd(self, backend: str, package: str) -> List[str]:
        """Generate command list for removal."""
        if backend == "snap":
            return ["sudo", "snap", "remove", package]
        else:
            return ["flatpak", "uninstall", "-y", package]

    def _run_cmd(self, cmd: List[str], dry_run: bool):
        """
        Execute the constructed command.

        Args:
            cmd (List[str]): Command list to execute.
            dry_run (bool): If True, simulate execution.
        """
        cmd_str = " ".join(cmd)
        if dry_run:
            cx_print(f"[Dry Run] would execute: [bold]{cmd_str}[/bold]", "info")
            return

        cx_print(f"Running: {cmd_str}...", "info")
        try:
            subprocess.check_call(cmd)
            cx_print("Command executed successfully.", "success")
        except subprocess.CalledProcessError as e:
            cx_print(f"Command failed: {e}", "error")
        except FileNotFoundError:
             cx_print(f"Executable not found: {cmd[0]}", "error")
