"""Cortex CLI - Main package.

This module provides the main CortexCLI class for package management.
Uses handler pattern for modular command handling.
"""

import argparse
from typing import TYPE_CHECKING

from cortex.cli.handlers import (
    AskHandlerWrapper,
    ConfigHandler,
    DaemonHandler,
    EnvHandler,
    HistoryHandler,
    ImportDepHandler,
    InstallHandler,
    RemoveHandler,
    SandboxHandler,
    StackHandler,
    TroubleshootHandler,
    UpdateHandler,
)
from cortex.predictive_prevention import RiskLevel

if TYPE_CHECKING:
    from cortex.shell_env_analyzer import ShellEnvironmentAnalyzer


class CortexCLI:
    """Facade class for Cortex CLI - delegates to modular handlers."""

    RISK_COLORS = {
        RiskLevel.NONE: "green",
        RiskLevel.LOW: "green",
        RiskLevel.MEDIUM: "yellow",
        RiskLevel.HIGH: "orange1",
        RiskLevel.CRITICAL: "red",
    }

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        # Initialize all handlers
        self._install_handler = InstallHandler(verbose=verbose)
        self._remove_handler = RemoveHandler(verbose=verbose)
        self._ask_handler = AskHandlerWrapper(verbose=verbose)
        self._update_handler = UpdateHandler(verbose=verbose)
        self._config_handler = ConfigHandler(verbose=verbose)
        self._daemon_handler = DaemonHandler(verbose=verbose)
        self._sandbox_handler = SandboxHandler(verbose=verbose)
        self._env_handler = EnvHandler(verbose=verbose)
        self._stack_handler = StackHandler(verbose=verbose)
        self._history_handler = HistoryHandler(verbose=verbose)
        self._troubleshoot_handler = TroubleshootHandler(verbose=verbose)
        self._import_handler = ImportDepHandler(verbose=verbose)

    @property
    def risk_labels(self) -> dict[RiskLevel, str]:
        """Localized mapping from RiskLevel enum values to human-readable strings."""
        from cortex.i18n import t
        return {
            RiskLevel.NONE: t("predictive.no_risk"),
            RiskLevel.LOW: t("predictive.low_risk"),
            RiskLevel.MEDIUM: t("predictive.medium_risk"),
            RiskLevel.HIGH: t("predictive.high_risk"),
            RiskLevel.CRITICAL: t("predictive.critical_risk"),
        }

    # Delegate methods to handlers

    def install(self, args: argparse.Namespace) -> int:
        """Handle install command."""
        return self._install_handler.install(args)

    def remove(self, args: argparse.Namespace) -> int:
        """Handle remove command."""
        return self._remove_handler.remove(args)

    def ask(self, args: argparse.Namespace) -> int:
        """Handle ask command."""
        return self._ask_handler.ask(args)

    def update(self, args: argparse.Namespace) -> int:
        """Handle update command."""
        return self._update_handler.update(args)

    def config(self, args: argparse.Namespace) -> int:
        """Handle config command."""
        return self._config_handler.config(args)

    def daemon(self, args: argparse.Namespace) -> int:
        """Handle daemon command."""
        return self._daemon_handler.daemon(args)

    def sandbox(self, args: argparse.Namespace) -> int:
        """Handle sandbox command."""
        return self._sandbox_handler.sandbox(args)

    def env(self, args: argparse.Namespace) -> int:
        """Handle env command."""
        return self._env_handler.env(args)

    def stack(self, args: argparse.Namespace) -> int:
        """Handle stack command."""
        return self._stack_handler.stack(args)

    def history(self, args: argparse.Namespace) -> int:
        """Handle history command."""
        return self._history_handler.history(args)

    def rollback(self, args: argparse.Namespace) -> int:
        """Handle rollback command."""
        return self._history_handler.rollback(args)

    def troubleshoot(self, args: argparse.Namespace) -> int:
        """Handle troubleshoot command."""
        return self._troubleshoot_handler.troubleshoot(args)

    def import_deps(self, args: argparse.Namespace) -> int:
        """Handle import command."""
        return self._import_handler.import_deps(args)

    def docker_permissions(self, args: argparse.Namespace) -> int:
        """Handle Docker permissions command."""
        from cortex.permission_manager import PermissionManager
        import os
        from cortex.branding import cx_print

        try:
            manager = PermissionManager(os.getcwd())
            cx_print("Scanning for Docker-related permission issues...", "info")
            manager.check_compose_config()

            execute_flag = getattr(args, "execute", False)
            yes_flag = getattr(args, "yes", False)

            if execute_flag and not yes_flag:
                mismatches = manager.diagnose()
                if mismatches:
                    cx_print(
                        f"Found {len(mismatches)} paths requiring ownership reclamation.",
                        "warning",
                    )
                    from cortex.stdin_handler import StdinHandler
                    from rich.console import Console
                    console = Console()
                    try:
                        console.print(
                            "[bold cyan]Reclaim ownership using sudo? (y/n): [/bold cyan]", end=""
                        )
                        response = StdinHandler.get_input()
                        if response.lower() not in ("y", "yes"):
                            cx_print("Operation cancelled", "info")
                            return 0
                    except (EOFError, KeyboardInterrupt):
                        console.print()
                        cx_print("Operation cancelled", "info")
                        return 0

            if manager.fix_permissions(execute=execute_flag):
                if execute_flag:
                    cx_print("Permissions fixed successfully!", "success")
                return 0
            return 1

        except (PermissionError, FileNotFoundError, OSError) as e:
            cx_print(f"Permission check failed: {e}", "error")
            return 1
        except NotImplementedError as e:
            cx_print(f"{e}", "error")
            return 1
        except Exception as e:
            cx_print(f"Unexpected error: {e}", "error")
            return 1

    def _get_api_key(self) -> str | None:
        """Get API key from environment or prompt user."""
        from cortex.cli.utils.api import get_api_key
        return get_api_key()

    def _get_provider(self) -> str:
        """Get the LLM provider to use."""
        from cortex.cli.utils.api import get_provider
        return get_provider()

    def _debug(self, message: str) -> None:
        """Print debug info only in verbose mode."""
        if self.verbose:
            from rich.console import Console
            console = Console()
            console.print(f"[dim][DEBUG] {message}[/dim]")

    def create_parser(self) -> argparse.ArgumentParser:
        """Create the argument parser with all subcommands."""
        from cortex.cli.handlers import (
            add_ask_parser,
            add_config_parser,
            add_daemon_parser,
            add_env_parser,
            add_history_parser,
            add_import_deps_parser,
            add_install_parser,
            add_remove_parser,
            add_sandbox_parser,
            add_stack_parser,
            add_troubleshoot_parser,
            add_update_parser,
        )

        parser = argparse.ArgumentParser(
            prog="cortex",
            description="AI-Powered Linux Package Manager",
        )
        parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

        subparsers = parser.add_subparsers(dest="command", required=True)

        # Add all command parsers
        add_install_parser(subparsers)
        add_remove_parser(subparsers)
        add_ask_parser(subparsers)
        add_update_parser(subparsers)
        add_config_parser(subparsers)
        add_daemon_parser(subparsers)
        add_sandbox_parser(subparsers)
        add_env_parser(subparsers)
        add_stack_parser(subparsers)
        add_history_parser(subparsers)
        add_troubleshoot_parser(subparsers)
        add_import_deps_parser(subparsers)

        return parser

    def dispatch(self, args: argparse.Namespace) -> int:
        """Dispatch command to appropriate handler.

        Returns exit code (0 for success, 1 for failure).
        """
        command = getattr(args, "command", None)

        # Commands with handlers
        command_handlers = {
            "install": self.install,
            "remove": self.remove,
            "ask": self.ask,
            "update": self.update,
            "config": self.config,
            "daemon": self.daemon,
            "sandbox": self.sandbox,
            "env": self.env,
            "stack": self.stack,
            "history": self.history,
            "rollback": self.rollback,
            "troubleshoot": self.troubleshoot,
            "import": self.import_deps,
        }

        if command in command_handlers:
            return command_handlers[command](args)

        # Commands without handlers - delegate to cli_main inline handlers
        # These need to be migrated later
        from cortex.branding import cx_print
        cx_print(f"Command '{command}' uses inline handler", "warning")
        return 1


# Re-export main from cli_main for backward compatibility
from cortex.cli_main import main as main

__all__ = ["CortexCLI", "main"]
