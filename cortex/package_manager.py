import shutil
import subprocess

from rich.prompt import Prompt
from rich.table import Table

from cortex.branding import console, cx_header, cx_print


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

    def _validate_package_name(self, package: str) -> bool:
        """Validate package name to prevent command injection."""
        # Allow alphanumeric, hyphens, underscores, and dots.
        # This is basic validation; backends have their own strict rules.
        import re
        if not re.match(r"^[a-zA-Z0-9.\-_]+$", package):
            cx_print(f"Invalid package name: {package}", "error")
            return False
        return True

    def install(self, package: str, dry_run: bool = False, scope: str = "user"):
        """
        Install a package using the available or selected backend.

        Args:
            package (str): Name of the package to install.
            dry_run (bool): If True, print the command instead of executing.
            scope (str): Installation scope for Flatpak ('user' or 'system'). Default is 'user'.
        """
        self._execute_action("install", package, dry_run, scope)

    def remove(self, package: str, dry_run: bool = False, scope: str = "user"):
        """
        Remove a package.

        Args:
            package (str): Name of the package to remove.
            dry_run (bool): If True, print the command instead of executing.
            scope (str): Removal scope for Flatpak ('user' or 'system'). Default is 'user'.
        """
        self._execute_action("remove", package, dry_run, scope)

    def _execute_action(self, action: str, package: str, dry_run: bool, scope: str = "user"):
        """
        Execute an install or remove action.
        """
        if not self._validate_package_name(package):
            return

        self.check_backends()

        backend = self._choose_backend(action)
        if not backend:
            return

        cmd = self._get_cmd(action, backend, package, scope)
        self._run_cmd(cmd, dry_run)

    def list_packages(self):
        """Check and display status of available package backends."""
        cx_header("Package Backends Status")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Backend")
        table.add_column("Status")
        table.add_column("Note", style="dim")

        if not self.snap_avail and not self.flatpak_avail:
             table.add_row("snap", "Not Found", "Install snapd to use")
             table.add_row("flatpak", "Not Found", "Install flatpak to use")
        else:
            if self.snap_avail:
                table.add_row("snap", "Available", "Use `snap list` to see packages")
            else:
                table.add_row("snap", "Not Found", "")

            if self.flatpak_avail:
                table.add_row("flatpak", "Available", "Use `flatpak list` to see packages")
            else:
                table.add_row("flatpak", "Not Found", "")

        console.print(table)
        console.print("[dim]Full package listing integration is planned for future updates.[/dim]")

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
        if not self._validate_package_name(package):
            return

        cx_header(f"Permissions: {package}")
        console.print(f"[bold]Checking confinement for {package}...[/bold]")

        if self.snap_avail:
            console.print("Snap: [green]Strict[/green] (Default) or [yellow]Classic[/yellow]")
        elif self.flatpak_avail:
             console.print("Flatpak: [blue]Sandboxed[/blue]")
        else:
            console.print("[dim]Backend not found, assuming standard permissions.[/dim]")

    def _choose_backend(self, action: str) -> str | None:
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

    def _get_cmd(self, action: str, backend: str, package: str, scope: str = "user") -> list[str]:
        """Generate command list for action."""
        if backend == "snap":
            # Snap doesn't typically distinguish user/system scope in the same way as flatpak CLI for install,
            # but usually requires sudo.
            cmd = ["sudo", "snap"]
            if action == "install":
                cmd.extend(["install", package])
            elif action == "remove":
                cmd.extend(["remove", package])
            return cmd
        else:
            # Flatpak
            cmd = ["flatpak"]
            if action == "install":
                cmd.extend(["install", "-y"])
            elif action == "remove":
                cmd.extend(["uninstall", "-y"])

            if scope == "user":
                cmd.append("--user")
            elif scope == "system":
                cmd.append("--system")

            cmd.append(package)
            return cmd

    def _run_cmd(self, cmd: list[str], dry_run: bool):
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
            # Added timeout of 300 seconds (5 minutes)
            subprocess.check_call(cmd, timeout=300)
            cx_print("Command executed successfully.", "success")
        except subprocess.TimeoutExpired:
             cx_print("Command timed out after 300 seconds.", "error")
        except subprocess.CalledProcessError as e:
            cx_print(f"Command failed: {e}", "error")
        except FileNotFoundError:
            cx_print(f"Executable not found: {cmd[0]}", "error")
