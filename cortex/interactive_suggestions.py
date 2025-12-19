"""
Interactive Command Suggestions with Fuzzy Search

Provides instant, hardware-aware command suggestions with fuzzy matching.
This is the "Tab autocomplete" moment - users see value in <1 second.

Features:
- Fuzzy matching on input (like fzf)
- Hardware-aware suggestions (detect GPU, show GPU options first)
- Common stacks pre-defined (ML, web dev, devops)
- Arrow key navigation
- Instant preview of what will be installed
- Works offline (suggestions don't need LLM)
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    from prompt_toolkit import Application
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.formatted_text import FormattedText
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import (
        HSplit,
        Layout,
        VSplit,
        Window,
    )
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
    from prompt_toolkit.styles import Style

    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False
    logger.warning("prompt_toolkit not available. Interactive suggestions will use fallback mode.")


class SuggestionDatabase:
    """Manages the suggestion database and provides search functionality."""

    def __init__(self, db_path: Path | None = None):
        """Initialize the suggestion database.

        Args:
            db_path: Path to suggestions JSON file. Defaults to data/suggestions.json
        """
        if db_path is None:
            # Default to data/suggestions.json relative to cortex package
            cortex_dir = Path(__file__).parent.parent
            db_path = cortex_dir / "data" / "suggestions.json"

        self.db_path = db_path
        self.suggestions: list[dict[str, Any]] = []
        self._load_database()

    def _load_database(self):
        """Load suggestions from JSON database."""
        try:
            if not self.db_path.exists():
                logger.warning(f"Suggestion database not found at {self.db_path}")
                return

            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.suggestions = data.get("suggestions", [])
                logger.debug(f"Loaded {len(self.suggestions)} suggestions from database")
        except Exception as e:
            logger.error(f"Failed to load suggestion database: {e}")
            self.suggestions = []

    def fuzzy_match(self, query: str, text: str) -> float:
        """
        Simple fuzzy matching algorithm.
        Returns a score between 0.0 and 1.0 indicating match quality.

        Args:
            query: The search query
            text: The text to match against

        Returns:
            Match score (0.0 = no match, 1.0 = perfect match)
        """
        if not query:
            return 1.0

        query_lower = query.lower()
        text_lower = text.lower()

        # Exact match gets highest score
        if query_lower == text_lower:
            return 1.0

        # Starts with gets high score
        if text_lower.startswith(query_lower):
            return 0.9

        # Contains gets medium score
        if query_lower in text_lower:
            return 0.7

        # Check if all characters appear in order (subsequence match)
        query_idx = 0
        for char in text_lower:
            if query_idx < len(query_lower) and char == query_lower[query_idx]:
                query_idx += 1

        if query_idx == len(query_lower):
            return 0.5

        # Check keyword matches
        query_words = query_lower.split()
        text_words = text_lower.split()
        matched_words = sum(1 for qw in query_words if any(qw in tw for tw in text_words))
        if matched_words > 0:
            return 0.3 * (matched_words / len(query_words))

        return 0.0

    def search(
        self,
        query: str,
        hardware_info: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Search suggestions with fuzzy matching and hardware-aware prioritization.

        Args:
            query: Search query string
            hardware_info: Hardware information dict (from HardwareDetector.detect_quick())
            limit: Maximum number of results to return

        Returns:
            List of matching suggestions, sorted by relevance
        """
        if not self.suggestions:
            return []

        hardware_info = hardware_info or {}
        has_nvidia = hardware_info.get("has_nvidia", False)

        scored_suggestions = []

        for suggestion in self.suggestions:
            # Calculate base match score
            name_score = self.fuzzy_match(query, suggestion.get("name", ""))
            display_score = self.fuzzy_match(query, suggestion.get("display_name", ""))
            desc_score = self.fuzzy_match(query, suggestion.get("description", "")) * 0.5
            keyword_scores = [
                self.fuzzy_match(query, kw) * 0.7 for kw in suggestion.get("keywords", [])
            ]
            keyword_score = max(keyword_scores) if keyword_scores else 0.0

            # Take the best match score
            base_score = max(name_score, display_score, desc_score, keyword_score)

            if base_score == 0.0:
                continue

            # Apply hardware-aware boost
            priority = suggestion.get("priority", 10)
            hardware_boost = 0.0

            # Boost suggestions that require/prefer hardware we have
            requires_hw = suggestion.get("requires_hardware", [])
            prefers_hw = suggestion.get("preferred_with_hardware", [])

            if has_nvidia:
                if "nvidia_gpu" in requires_hw:
                    hardware_boost = 0.3  # Strong boost for required hardware
                elif "nvidia_gpu" in prefers_hw:
                    hardware_boost = 0.15  # Moderate boost for preferred hardware

            # Calculate final score
            final_score = base_score + hardware_boost + (priority / 100.0)

            scored_suggestions.append((final_score, suggestion))

        # Sort by score (descending) and return top results
        scored_suggestions.sort(key=lambda x: x[0], reverse=True)
        return [suggestion for _, suggestion in scored_suggestions[:limit]]


class InteractiveSuggestionUI:
    """Interactive TUI for command suggestions using prompt_toolkit."""

    def __init__(self, db: SuggestionDatabase, hardware_info: dict[str, Any] | None = None):
        """Initialize the interactive UI.

        Args:
            db: SuggestionDatabase instance
            hardware_info: Hardware information dict
        """
        self.db = db
        self.hardware_info = hardware_info or {}
        self.selected_index = 0
        self.query = ""
        self.results: list[dict[str, Any]] = []
        self.app: Application | None = None

    def _update_results(self):
        """Update search results based on current query."""
        self.results = self.db.search(self.query, self.hardware_info, limit=10)
        if self.results:
            self.selected_index = min(self.selected_index, len(self.results) - 1)
        else:
            self.selected_index = 0


    def _format_results(self) -> FormattedText:
        """Format the results list for display."""
        if not self.results:
            return FormattedText([("class:no-results", "No suggestions found")])

        lines = []
        for idx, suggestion in enumerate(self.results):
            is_selected = idx == self.selected_index
            prefix = "→" if is_selected else " "
            style = "class:selected" if is_selected else "class:normal"

            name = suggestion.get("display_name", suggestion.get("name", "Unknown"))
            desc = suggestion.get("description", "")

            lines.append((style, f"{prefix} {name}\n"))
            if desc:
                lines.append(("class:description", f"   {desc[:60]}...\n"))

        return FormattedText(lines)

    def _format_preview(self) -> FormattedText:
        """Format the preview of selected suggestion."""
        if not self.results or self.selected_index >= len(self.results):
            return FormattedText([("class:preview-title", "Preview\n"), ("", "Select a suggestion")])

        suggestion = self.results[self.selected_index]
        lines = [("class:preview-title", f"{suggestion.get('display_name', 'Unknown')}\n\n")]

        desc = suggestion.get("description", "")
        if desc:
            lines.append(("class:preview-text", f"{desc}\n\n"))

        commands = suggestion.get("commands_preview", [])
        if commands:
            lines.append(("class:preview-title", "Will install:\n"))
            for cmd in commands[:5]:  # Show first 5 commands
                lines.append(("class:preview-command", f"  • {cmd}\n"))

        return FormattedText(lines)

    def _create_key_bindings(self) -> KeyBindings:
        """Create keyboard bindings."""
        kb = KeyBindings()

        @kb.add("up")
        def go_up(event):
            if self.results and self.selected_index > 0:
                self.selected_index -= 1
                event.app.invalidate()

        @kb.add("down")
        def go_down(event):
            if self.results and self.selected_index < len(self.results) - 1:
                self.selected_index += 1
                event.app.invalidate()

        @kb.add("c-c")
        @kb.add("escape")
        def cancel(event):
            event.app.exit(result=None)

        @kb.add("enter")
        def select(event):
            if self.results and 0 <= self.selected_index < len(self.results):
                event.app.exit(result=self.results[self.selected_index])

        return kb

    def show(self, initial_query: str = "") -> dict[str, Any] | None:
        """
        Show the interactive suggestion UI.

        Args:
            initial_query: Initial search query

        Returns:
            Selected suggestion dict, or None if cancelled
        """
        import sys
        
        # Check if we're in a real terminal
        is_tty = sys.stdin.isatty() and sys.stdout.isatty()
        
        if not PROMPT_TOOLKIT_AVAILABLE or not is_tty:
            # Use fallback UI if prompt_toolkit not available or not in a real terminal
            return self._fallback_ui(initial_query)

        self.query = initial_query
        self._update_results()

        style = Style(
            [
                ("selected", "bg:#0088ff fg:#ffffff bold"),
                ("normal", "fg:#ffffff"),
                ("description", "fg:#888888"),
                ("preview-title", "fg:#00ff00 bold"),
                ("preview-text", "fg:#ffffff"),
                ("preview-command", "fg:#ffff00"),
                ("help", "fg:#888888"),
                ("no-results", "fg:#ff0000"),
            ]
        )

        # Search input with buffer that updates on change
        search_buffer = Buffer()
        search_buffer.text = initial_query

        def on_text_changed(buffer):
            new_query = buffer.text
            if new_query != self.query:
                self.query = new_query
                self._update_results()
                if self.app:
                    self.app.invalidate()

        search_buffer.on_text_changed += on_text_changed

        search_field = Window(
            BufferControl(buffer=search_buffer),
            height=1,
            get_line_prefix=lambda line_number, wrap_count: [("class:prompt", "Search: ")],
            wrap_lines=False,
        )

        # Results list
        results_control = FormattedTextControl(
            text=self._format_results,
            focusable=True,
        )
        results_window = Window(
            content=results_control,
            height=10,
            always_hide_cursor=True,
        )

        # Preview window
        preview_control = FormattedTextControl(text=self._format_preview)
        preview_window = Window(
            content=preview_control,
            height=10,
            style="class:preview",
        )

        # Help text
        help_text = FormattedTextControl(
            text=FormattedText(
                [
                    ("class:help", "↑↓ to navigate  "),
                    ("class:help", "Enter to select  "),
                    ("class:help", "Esc to cancel"),
                ]
            )
        )
        help_window = Window(content=help_text, height=1, style="class:help")

        # Main layout
        layout = Layout(
            HSplit(
                [
                    search_field,
                    VSplit([results_window, preview_window]),
                    help_window,
                ]
            )
        )

        kb = self._create_key_bindings()

        # Create application
        self.app = Application(
            layout=layout,
            key_bindings=kb,
            style=style,
            full_screen=False,
            mouse_support=False,
        )

        try:
            # Set focus to search field buffer
            self.app.layout.focus(search_buffer)
            result = self.app.run()
            return result
        except KeyboardInterrupt:
            return None
        except Exception as e:
            logger.error(f"Interactive UI error: {e}", exc_info=True)
            # Fall back to non-interactive mode
            if self.results and 0 <= self.selected_index < len(self.results):
                return self.results[self.selected_index]
            return None

    def _fallback_ui(self, initial_query: str) -> dict[str, Any] | None:
        """Fallback UI when prompt_toolkit is not available."""
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table

        console = Console()
        query = initial_query

        while True:
            # Search and display results
            results = self.db.search(query, self.hardware_info, limit=10)

            if not results:
                console.print("[red]No suggestions found[/red]")
                return None

            # Display results
            table = Table(show_header=False, box=None, padding=(0, 1))
            for idx, suggestion in enumerate(results):
                name = suggestion.get("display_name", suggestion.get("name", "Unknown"))
                desc = suggestion.get("description", "")
                marker = "→" if idx == 0 else " "
                table.add_row(f"{marker} {name}", desc[:60])

            console.print(Panel(table, title="Suggestions", border_style="blue"))
            console.print("\n[dim]Enter number to select, or type to search more, 'q' to quit[/dim]")

            try:
                user_input = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                return None

            if user_input.lower() == "q":
                return None

            # Check if it's a number (selection)
            try:
                selection = int(user_input)
                if 1 <= selection <= len(results):
                    return results[selection - 1]
            except ValueError:
                pass

            # Otherwise, treat as new query
            query = user_input
            self.selected_index = 0


def get_suggestion(
    query: str,
    hardware_info: dict[str, Any] | None = None,
    interactive: bool = True,
) -> dict[str, Any] | None:
    """
    Get a command suggestion, optionally using interactive UI.

    Args:
        query: Search query
        hardware_info: Hardware information dict
        interactive: Whether to show interactive UI

    Returns:
        Selected suggestion dict, or None
    """
    db = SuggestionDatabase()
    hardware_info = hardware_info or {}

    if interactive and PROMPT_TOOLKIT_AVAILABLE:
        ui = InteractiveSuggestionUI(db, hardware_info)
        return ui.show(initial_query=query)
    else:
        # Non-interactive: return best match
        results = db.search(query, hardware_info, limit=1)
        return results[0] if results else None

