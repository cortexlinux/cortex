"""
Cortex Interactive TUI for Package Suggestions
Save as: cortex/tui.py
"""

import sys
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .database import PackageDatabase
from .hardware_detection import detect_hardware, detect_quick
from .matcher import FuzzyMatcher

console = Console()


class SuggestionTUI:
    """Interactive TUI for package suggestions."""

    def __init__(self, db: PackageDatabase):
        self.db = db
        self.matcher = FuzzyMatcher(db)
        self.results: list[dict] = []
        self.selected_index = 0
        self.selected_item: dict | None = None

    def search(self, query: str) -> list[dict]:
        """Perform search and return results."""
        self.results = self.matcher.match(query, limit=10)
        self.selected_index = 0 if self.results else -1
        return self.results

    def render_results(self, query: str) -> Table:
        """Render search results as a rich Table."""
        table = Table(
            title=f"🔍 Suggestions for '{query}'", show_header=True, header_style="bold cyan"
        )
        table.add_column("", width=2)
        table.add_column("Type", width=6)
        table.add_column("Name", width=28, style="green")
        table.add_column("Description", width=45)
        table.add_column("GPU", width=3)

        if not self.results:
            table.add_row("", "", "[dim]No matches found[/dim]", "", "")
            return table

        for i, item in enumerate(self.results):
            is_selected = i == self.selected_index
            prefix = "→" if is_selected else ""
            type_badge = "[S]" if item["type"] == "stack" else "[P]"
            gpu_badge = "🎮" if item.get("requires_gpu") else ""

            name = item["name"]
            desc = (
                item["description"][:42] + "..."
                if len(item["description"]) > 45
                else item["description"]
            )

            if is_selected:
                table.add_row(
                    f"[bold cyan]{prefix}[/]",
                    f"[bold]{type_badge}[/]",
                    f"[bold reverse] {name} [/]",
                    f"[bold]{desc}[/]",
                    gpu_badge,
                )
            else:
                table.add_row(prefix, type_badge, name, f"[dim]{desc}[/]", gpu_badge)

        return table

    def render_preview(self) -> Panel:
        """Render preview panel for selected item."""
        if not self.results or self.selected_index < 0:
            return Panel("[dim]Select an item to see preview[/dim]", title="📦 Preview")

        item = self.results[self.selected_index]
        preview = self.matcher.get_install_preview(item["type"], item["id"])

        content = f"[bold green]{preview.get('name', 'Unknown')}[/bold green]\n"
        content += f"[dim]{preview.get('description', '')}[/dim]\n\n"

        if preview.get("apt_packages"):
            pkgs = preview["apt_packages"]
            content += "[bold]APT Packages:[/bold]\n"
            for pkg in pkgs[:8]:
                content += f"  • {pkg}\n"
            if len(pkgs) > 8:
                content += f"  [dim]...and {len(pkgs)-8} more[/dim]\n"

        if preview.get("pip_packages"):
            content += "\n[bold]Pip Packages:[/bold]\n"
            for pkg in preview["pip_packages"][:4]:
                content += f"  • {pkg}\n"

        if preview.get("default_port"):
            content += f"\n[bold]Default Port:[/bold] {preview['default_port']}"

        return Panel(content, title="📦 Preview", border_style="green")

    def show_hardware_info(self):
        """Display detected hardware information."""
        hw = detect_quick()

        console.print("\n[bold]🖥️  Detected Hardware:[/bold]")
        console.print(f"  CPU Cores: {hw['cpu_cores']}")
        console.print(f"  RAM: {hw['ram_gb']} GB")
        console.print(f"  NVIDIA GPU: {'✅ Yes' if hw['has_nvidia'] else '❌ No'}")
        console.print(f"  Disk Free: {hw['disk_free_gb']} GB")
        console.print()

    def run_interactive(self, initial_query: str = "") -> dict | None:
        """Run the interactive suggestion selector with real arrow key navigation."""
        try:
            from prompt_toolkit import Application
            from prompt_toolkit.formatted_text import HTML
            from prompt_toolkit.key_binding import KeyBindings
            from prompt_toolkit.layout import HSplit, Layout, Window
            from prompt_toolkit.layout.controls import FormattedTextControl

            # Search immediately (silently)
            self.search(initial_query)

            if not self.results:
                console.print(f"[dim]No matches found for '{initial_query}'[/dim]")
                return None

            # Auto-select only if: exactly 1 result AND high-confidence match (score >= 100)
            # Low fuzzy scores (< 100) should still show the menu to avoid bad auto-selections
            if len(self.results) == 1 and self.results[0].get("score", 0) >= 100:
                return self.results[0]

            # Scrolling viewport: show 5 items at a time, scroll as you navigate
            viewport_size = 5
            total_results = len(self.results)
            self.scroll_offset = 0  # Track viewport start position

            # Setup key bindings for arrow navigation
            kb = KeyBindings()

            @kb.add("up")
            def _(event):
                if self.selected_index > 0:
                    self.selected_index -= 1
                    # Scroll viewport up if selection goes above visible area
                    if self.selected_index < self.scroll_offset:
                        self.scroll_offset = self.selected_index
                    event.app.invalidate()

            @kb.add("down")
            def _(event):
                if self.selected_index < total_results - 1:
                    self.selected_index += 1
                    # Scroll viewport down if selection goes below visible area
                    if self.selected_index >= self.scroll_offset + viewport_size:
                        self.scroll_offset = self.selected_index - viewport_size + 1
                    event.app.invalidate()

            @kb.add("enter")
            def _(event):
                self.selected_item = self.results[self.selected_index]
                event.app.exit()

            @kb.add("escape")
            @kb.add("q")
            def _(event):
                self.selected_item = None
                event.app.exit()

            @kb.add("tab")
            def _(event):
                event.app.exit()
                self.show_full_details()
                # Restart the app
                event.app.run()

            # Calculate max name width for alignment (from visible results)
            max_name_width = (
                max(len(item["id"]) for item in self.results[: viewport_size + 5])
                if self.results
                else 16
            )
            max_name_width = max(max_name_width, 16)  # Minimum 16 chars

            def get_text():
                # Build the display text with scrolling viewport
                lines = []

                # Calculate viewport bounds
                start = self.scroll_offset
                end = min(start + viewport_size, total_results)
                visible_results = self.results[start:end]

                # Show scroll indicator if there are items above
                if start > 0:
                    lines.append(f"<ansigray>  ↑ {start} more above</ansigray>")

                for i, item in enumerate(visible_results):
                    actual_index = start + i
                    prefix = "→" if actual_index == self.selected_index else " "

                    name = item["id"]
                    desc = item["description"]
                    name_padded = name.ljust(max_name_width)

                    if actual_index == self.selected_index:
                        lines.append(
                            f"<style bg='ansiblue'><b>{prefix} {name_padded}</b> {desc}</style>"
                        )
                    else:
                        lines.append(f"{prefix} <ansigray>{name_padded}</ansigray> {desc}")

                # Show scroll indicator if there are items below
                remaining = total_results - end
                if remaining > 0:
                    lines.append(f"<ansigray>  ↓ {remaining} more below</ansigray>")

                # Add help text at bottom
                lines.append("")
                lines.append(
                    "<ansigray>[↑↓ to select, Enter to install, Tab for details, q to quit]</ansigray>"
                )

                return HTML("\n".join(lines))

            # Create application
            app = Application(
                layout=Layout(HSplit([Window(content=FormattedTextControl(get_text))])),
                key_bindings=kb,
                full_screen=False,
                mouse_support=False,
            )

            # Run the application
            app.run()

            return self.selected_item

        except ImportError:
            # Fallback to simple mode if prompt_toolkit not available (silently)
            return self.run_simple(initial_query)

    def show_full_details(self):
        """Show full details for selected item."""
        if not self.results or self.selected_index < 0:
            return

        item = self.results[self.selected_index]
        preview = self.matcher.get_install_preview(item["type"], item["id"])

        console.clear()
        console.print()
        console.print(
            Panel(
                f"[bold]{preview.get('name')}[/bold]\n\n{preview.get('description')}",
                title="📦 Package Details",
                border_style="blue",
            )
        )

        if preview.get("apt_packages"):
            console.print("\n[bold]APT Packages to install:[/bold]")
            for pkg in preview["apt_packages"]:
                console.print(f"  • {pkg}")

        if preview.get("pip_packages"):
            console.print("\n[bold]Pip Packages to install:[/bold]")
            for pkg in preview["pip_packages"]:
                console.print(f"  • {pkg}")

        console.print("\n[bold]Installation Command(s):[/bold]")
        commands = preview.get("commands", [preview.get("command")])
        for cmd in commands:
            if cmd:
                console.print(Panel(cmd, border_style="cyan"))

        console.input("\n[dim]Press Enter to continue...[/dim]")

    def run_simple(self, query: str) -> dict | None:
        """Run in simple non-interactive mode - clean format."""
        self.search(query)

        if not self.results:
            console.print(f"[dim]No matches found for '{query}'[/dim]")
            return None

        # Display clean suggestions instantly - no extra text
        for i, item in enumerate(self.results[:5]):
            prefix = "→" if i == 0 else " "
            name = item["id"].ljust(16)  # Pad for alignment
            desc = item["description"]
            console.print(f"{prefix} {name} {desc}")
        console.print("[dim]  [↑↓ to select, Enter to install, Tab for details][/dim]")
        console.print()
        console.print("  0. Cancel")

        try:
            choice = console.input("\n[bold]Enter choice (1-5, 0 to cancel):[/bold] ")
            idx = int(choice) - 1
            if 0 <= idx < len(self.results):
                self.selected_item = self.results[idx]
                return self.selected_item
        except (ValueError, KeyboardInterrupt):
            pass

        return None


def run_suggestions(
    query: str = "", db_path: str | None = None, interactive: bool = True
) -> dict | None:
    """
    Main entry point for package suggestions.

    Args:
        query: Initial search query
        db_path: Optional path to packages.json
        interactive: Run in interactive mode

    Returns:
        Selected package/stack dict or None if cancelled
    """
    try:
        db = PackageDatabase(db_path)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("[dim]Make sure packages.json exists in data/ directory[/dim]")
        return None

    tui = SuggestionTUI(db)

    if interactive:
        return tui.run_interactive(query)
    else:
        return tui.run_simple(query)


def print_suggestions(query: str, db_path: str | None = None, limit: int = 5):
    """Print suggestions without interaction (for scripting)."""
    try:
        db = PackageDatabase(db_path)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        return

    matcher = FuzzyMatcher(db)
    results = matcher.match(query, limit=limit)

    if not results:
        console.print(f"[yellow]No matches for '{query}'[/yellow]")
        return

    for r in results:
        gpu = "🎮 " if r.get("requires_gpu") else ""
        t = "[Stack]" if r["type"] == "stack" else "[Pkg]"
        console.print(f"{gpu}{t} [green]{r['name']}[/green] - {r['description'][:50]}")


# CLI entry point
if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else ""
    interactive = "--simple" not in sys.argv

    result = run_suggestions(query, interactive=interactive)

    if result:
        console.print(f"\n[bold green]✅ Selected:[/bold green] {result['name']}")
        preview = FuzzyMatcher(PackageDatabase()).get_install_preview(result["type"], result["id"])
        console.print("\n[bold]To install, run:[/bold]")
        commands = preview.get("commands", [preview.get("command")])
        for cmd in commands:
            if cmd:
                console.print(f"  [cyan]{cmd}[/cyan]")
