"""
Tests for branding/UI utilities.

Tests Rich console output functions.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from io import StringIO

from cortex.tutor.branding import (
    console,
    tutor_print,
    print_banner,
    print_lesson_header,
    print_code_example,
    print_menu,
    print_table,
    print_progress_summary,
    print_markdown,
    print_best_practice,
    print_tutorial_step,
    print_error_panel,
    print_success_panel,
    get_user_input,
)


class TestConsole:
    """Tests for console instance."""

    def test_console_exists(self):
        """Test console is initialized."""
        assert console is not None

    def test_console_is_rich(self):
        """Test console is Rich Console."""
        from rich.console import Console

        assert isinstance(console, Console)


class TestTutorPrint:
    """Tests for tutor_print function."""

    def test_tutor_print_success(self, capsys):
        """Test success status print."""
        tutor_print("Test message", "success")
        # Rich output, just ensure no errors

    def test_tutor_print_error(self, capsys):
        """Test error status print."""
        tutor_print("Error message", "error")

    def test_tutor_print_warning(self, capsys):
        """Test warning status print."""
        tutor_print("Warning message", "warning")

    def test_tutor_print_info(self, capsys):
        """Test info status print."""
        tutor_print("Info message", "info")

    def test_tutor_print_tutor(self, capsys):
        """Test tutor status print."""
        tutor_print("Tutor message", "tutor")

    def test_tutor_print_default(self, capsys):
        """Test default status print."""
        tutor_print("Default message")


class TestPrintBanner:
    """Tests for print_banner function."""

    def test_print_banner(self, capsys):
        """Test banner prints without error."""
        print_banner()
        # Just ensure no errors


class TestPrintLessonHeader:
    """Tests for print_lesson_header function."""

    def test_print_lesson_header(self, capsys):
        """Test lesson header prints."""
        print_lesson_header("docker")

    def test_print_lesson_header_long_name(self, capsys):
        """Test lesson header with long package name."""
        print_lesson_header("very-long-package-name-for-testing")


class TestPrintCodeExample:
    """Tests for print_code_example function."""

    def test_print_code_example_bash(self, capsys):
        """Test code example with bash."""
        print_code_example("docker run nginx", "bash", "Run container")

    def test_print_code_example_python(self, capsys):
        """Test code example with python."""
        print_code_example("print('hello')", "python", "Hello world")

    def test_print_code_example_no_title(self, capsys):
        """Test code example without title."""
        print_code_example("echo hello", "bash")


class TestPrintMenu:
    """Tests for print_menu function."""

    def test_print_menu(self, capsys):
        """Test menu prints."""
        options = ["Option 1", "Option 2", "Exit"]
        print_menu(options)

    def test_print_menu_empty(self, capsys):
        """Test empty menu."""
        print_menu([])

    def test_print_menu_single(self, capsys):
        """Test single option menu."""
        print_menu(["Only option"])


class TestPrintTable:
    """Tests for print_table function."""

    def test_print_table(self, capsys):
        """Test table prints."""
        headers = ["Name", "Value"]
        rows = [["docker", "100"], ["nginx", "50"]]
        print_table(headers, rows, "Test Table")

    def test_print_table_no_title(self, capsys):
        """Test table without title."""
        headers = ["Col1", "Col2"]
        rows = [["a", "b"]]
        print_table(headers, rows)

    def test_print_table_empty_rows(self, capsys):
        """Test table with empty rows."""
        headers = ["Header"]
        print_table(headers, [])


class TestPrintProgressSummary:
    """Tests for print_progress_summary function."""

    def test_print_progress_summary(self, capsys):
        """Test progress summary prints."""
        print_progress_summary(3, 5, "docker")

    def test_print_progress_summary_complete(self, capsys):
        """Test progress summary when complete."""
        print_progress_summary(5, 5, "docker")

    def test_print_progress_summary_zero(self, capsys):
        """Test progress summary with zero progress."""
        print_progress_summary(0, 5, "docker")


class TestPrintMarkdown:
    """Tests for print_markdown function."""

    def test_print_markdown(self, capsys):
        """Test markdown prints."""
        print_markdown("# Header\n\nSome **bold** text.")

    def test_print_markdown_code(self, capsys):
        """Test markdown with code block."""
        print_markdown("```bash\necho hello\n```")

    def test_print_markdown_list(self, capsys):
        """Test markdown with list."""
        print_markdown("- Item 1\n- Item 2\n- Item 3")


class TestPrintBestPractice:
    """Tests for print_best_practice function."""

    def test_print_best_practice(self, capsys):
        """Test best practice prints."""
        print_best_practice("Use official images", 1)

    def test_print_best_practice_long(self, capsys):
        """Test best practice with long text."""
        long_text = "This is a very long best practice text " * 5
        print_best_practice(long_text, 10)


class TestPrintTutorialStep:
    """Tests for print_tutorial_step function."""

    def test_print_tutorial_step(self, capsys):
        """Test tutorial step prints."""
        print_tutorial_step("Install Docker", 1, 5)

    def test_print_tutorial_step_last(self, capsys):
        """Test last tutorial step."""
        print_tutorial_step("Finish setup", 5, 5)


class TestPrintErrorPanel:
    """Tests for print_error_panel function."""

    def test_print_error_panel(self, capsys):
        """Test error panel prints."""
        print_error_panel("Something went wrong")

    def test_print_error_panel_long(self, capsys):
        """Test error panel with long message."""
        print_error_panel("Error: " + "x" * 100)


class TestPrintSuccessPanel:
    """Tests for print_success_panel function."""

    def test_print_success_panel(self, capsys):
        """Test success panel prints."""
        print_success_panel("Operation completed")

    def test_print_success_panel_long(self, capsys):
        """Test success panel with long message."""
        print_success_panel("Success: " + "y" * 100)


class TestGetUserInput:
    """Tests for get_user_input function."""

    @patch("builtins.input", return_value="test input")
    def test_get_user_input(self, mock_input):
        """Test getting user input."""
        result = get_user_input("Enter value")
        assert result == "test input"

    @patch("builtins.input", return_value="")
    def test_get_user_input_empty(self, mock_input):
        """Test empty user input."""
        result = get_user_input("Enter value")
        assert result == ""

    @patch("builtins.input", return_value="  spaced  ")
    def test_get_user_input_strips(self, mock_input):
        """Test input stripping is not done (raw input)."""
        result = get_user_input("Enter value")
        # Note: get_user_input should return raw input
        assert "spaced" in result
