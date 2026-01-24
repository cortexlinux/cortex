"""History command handler for Cortex CLI.

Provides installation history and rollback functionality.
"""

import argparse
from typing import Optional

from rich.console import Console
from rich.table import Table

from cortex.installation_history import InstallationHistory, InstallationStatus

console = Console()


class HistoryHandler:
    """Handler for history command."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def history(
        self,
        limit: int = 20,
        status: Optional[str] = None,
        show_id: Optional[str] = None,
    ) -> int:
        """Show installation history."""
        history = InstallationHistory()

        if show_id:
            entry = history.get_installation(show_id)
            if entry:
                self._display_entry(entry)
                return 0
            else:
                console.print(f"Installation not found: {show_id}", style="yellow")
                return 1

        status_filter = InstallationStatus(status) if status else None
        entries = history.get_history(limit, status_filter)

        if not entries:
            console.print("No installation history found")
            return 0

        table = Table(title="Installation History")
        table.add_column("ID", style="dim")
        table.add_column("Type")
        table.add_column("Packages", style="cyan")
        table.add_column("Status")
        table.add_column("Date", style="dim")

        for entry in entries:
            status_style = {
                InstallationStatus.SUCCESS: "green",
                InstallationStatus.FAILED: "red",
                InstallationStatus.IN_PROGRESS: "blue",
                InstallationStatus.PENDING: "yellow",
            }.get(entry.status, "white")

            packages = ", ".join(entry.packages[:3])
            if len(entry.packages) > 3:
                packages += f" (+{len(entry.packages) - 3} more)"

            # Format timestamp (it's a string like "2025-01-24T12:34:56.123456")
            ts = entry.timestamp[:19].replace("T", " ")

            table.add_row(
                entry.id[:8],
                entry.operation_type.value,
                packages,
                f"[{status_style}]{entry.status.value}[/]",
                ts,
            )

        console.print(table)
        return 0

    def rollback(self, install_id: str, dry_run: bool = False) -> int:
        """Rollback an installation."""
        from cortex.transaction_history import UndoManager

        history = InstallationHistory()

        entry = history.get_installation(install_id)
        if not entry:
            console.print(f"Installation not found: {install_id}", style="yellow")
            return 1

        undo_manager = UndoManager()

        preview = undo_manager.preview_undo(install_id)
        if not preview:
            console.print("No rollback available for this installation", style="yellow")
            return 1

        console.print("Rollback preview:")
        console.print(f"  Installation ID: {install_id}")
        console.print(f"  Packages to remove: {', '.join(preview.packages_to_remove)}")
        console.print(f"  Rollback commands: {len(preview.rollback_commands)}")

        if preview.rollback_commands:
            console.print("\nRollback commands:")
            for i, cmd in enumerate(preview.rollback_commands, 1):
                console.print(f"  {i}. {cmd}")

        if dry_run:
            console.print("\nDry run - no changes made", style="blue")
            return 0

        from rich.prompt import Confirm

        if not Confirm.ask("\nProceed with rollback?"):
            console.print("Cancelled")
            return 0

        result = undo_manager.execute_undo(install_id)

        if result.success:
            console.print("Rollback completed successfully", style="green")
            history.update_installation(install_id, InstallationStatus.ROLLED_BACK)
            return 0
        else:
            console.print(f"Rollback failed: {result.error}", style="red")
            return 1

    def _display_entry(self, entry) -> None:
        """Display a single history entry."""
        from rich.panel import Panel
        from rich.text import Text

        text = Text()
        text.append(f"ID: {entry.id}\n")
        text.append(f"Type: {entry.operation_type.value}\n")
        text.append(f"Packages: {', '.join(entry.packages)}\n")
        text.append(f"Status: {entry.status.value}\n")
        # Format timestamp
        ts = entry.timestamp[:19].replace("T", " ")
        text.append(f"Date: {ts}\n")

        if entry.error_message:
            text.append(f"Error: {entry.error_message}")

        console.print(Panel(text, title=f"Installation {entry.id[:8]}", expand=False))


def add_history_parser(subparsers) -> argparse.ArgumentParser:
    """Add history parser to subparsers."""
    history_parser = subparsers.add_parser("history", help="Show installation history")
    history_parser.add_argument("--limit", type=int, default=20, help="Max entries to show")
    history_parser.add_argument("--status", help="Filter by status")
    history_parser.add_argument("id", nargs="?", help="Show specific installation")

    return history_parser


def add_rollback_parser(subparsers) -> argparse.ArgumentParser:
    """Add rollback parser to subparsers."""
    rollback_parser = subparsers.add_parser("rollback", help="Rollback an installation")
    rollback_parser.add_argument("install_id", help="Installation ID to rollback")
    rollback_parser.add_argument("--dry-run", action="store_true", help="Show what would happen")

    return rollback_parser
