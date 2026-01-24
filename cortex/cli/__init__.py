"""Cortex CLI - Main package.

This module provides the main CortexCLI class for package management.
Uses handler pattern for modular command handling.
"""

import argparse
from typing import TYPE_CHECKING

from cortex.cli.handlers import (
    AskHandlerWrapper,
    BenchmarkHandler,
    CacheHandler,
    ConfigHandler,
    DaemonHandler,
    DashboardHandler,
    DemoHandler,
    DoctorHandler,
    DockerHandler,
    EnvHandler,
    HistoryHandler,
    ImportDepHandler,
    InstallHandler,
    MiscHandler,
    NotifyHandler,
    RemoveHandler,
    RoleHandler,
    SandboxHandler,
    StackHandler,
    StatusHandler,
    SystemHandler,
    TroubleshootHandler,
    UpdateHandler,
    VoiceHandler,
    WizardHandler,
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
        # New handlers
        self._demo_handler = DemoHandler(verbose=verbose)
        self._dashboard_handler = DashboardHandler(verbose=verbose)
        self._wizard_handler = WizardHandler(verbose=verbose)
        self._status_handler = StatusHandler(verbose=verbose)
        self._benchmark_handler = BenchmarkHandler(verbose=verbose)
        self._system_handler = SystemHandler(verbose=verbose)
        self._voice_handler = VoiceHandler(verbose=verbose)
        self._docker_handler = DockerHandler(verbose=verbose)
        self._notify_handler = NotifyHandler(verbose=verbose)
        self._role_handler = RoleHandler(verbose=verbose)
        self._cache_handler = CacheHandler(verbose=verbose)
        self._doctor_handler = DoctorHandler(verbose=verbose)
        self._misc_handler = MiscHandler(verbose=verbose)

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

    # New command methods

    def demo(self, args: argparse.Namespace) -> int:
        """Handle demo command."""
        return self._demo_handler.demo()

    def dashboard(self, args: argparse.Namespace) -> int:
        """Handle dashboard command."""
        return self._dashboard_handler.dashboard()

    def wizard(self, args: argparse.Namespace) -> int:
        """Handle wizard command."""
        return self._wizard_handler.wizard()

    def status(self, args: argparse.Namespace) -> int:
        """Handle status command."""
        return self._status_handler.status()

    def benchmark(self, args: argparse.Namespace) -> int:
        """Handle benchmark command."""
        return self._benchmark_handler.benchmark(verbose=getattr(args, "verbose", False))

    def systemd(self, args: argparse.Namespace) -> int:
        """Handle systemd command."""
        return self._system_handler.systemd(
            service=args.service,
            action=getattr(args, "action", "status"),
            verbose=getattr(args, "verbose", False),
        )

    def gpu(self, args: argparse.Namespace) -> int:
        """Handle gpu command."""
        return self._system_handler.gpu(
            action=getattr(args, "action", "status"),
            mode=getattr(args, "mode", None),
            verbose=getattr(args, "verbose", False),
        )

    def printer(self, args: argparse.Namespace) -> int:
        """Handle printer command."""
        return self._system_handler.printer(
            action=getattr(args, "action", "status"),
            verbose=getattr(args, "verbose", False),
        )

    def wifi(self, args: argparse.Namespace) -> int:
        """Handle wifi command."""
        return self._system_handler.wifi(verbose=getattr(args, "verbose", False))

    def voice(self, args: argparse.Namespace) -> int:
        """Handle voice command."""
        return self._voice_handler.voice(
            continuous=not getattr(args, "single", False),
            model=getattr(args, "model", None),
        )

    def docker(self, args: argparse.Namespace) -> int:
        """Handle docker command."""
        if hasattr(args, "docker_action") and args.docker_action == "permissions":
            return self._docker_handler.docker_permissions(args)
        return 1

    def notify(self, args: argparse.Namespace) -> int:
        """Handle notify command."""
        return self._notify_handler.notify(args)

    def role(self, args: argparse.Namespace) -> int:
        """Handle role command."""
        return self._role_handler.role(args)

    def cache(self, args: argparse.Namespace) -> int:
        """Handle cache command."""
        return self._cache_handler.cache(args)

    def doctor(self, args: argparse.Namespace) -> int:
        """Handle doctor command."""
        return self._doctor_handler.doctor(args)

    def activate(self, args: argparse.Namespace) -> int:
        """Handle activate command."""
        return self._misc_handler.activate(args)

    def upgrade(self, args: argparse.Namespace) -> int:
        """Handle upgrade command."""
        return self._misc_handler.upgrade(args)

    def stdin(self, args: argparse.Namespace) -> int:
        """Handle stdin command."""
        return self._misc_handler.stdin(args)

    def deps(self, args: argparse.Namespace) -> int:
        """Handle deps command."""
        return self._misc_handler.deps(args)

    def health(self, args: argparse.Namespace) -> int:
        """Handle health command."""
        return self._misc_handler.health(args)

    def license(self, args: argparse.Namespace) -> int:
        """Handle license command."""
        return self._misc_handler.license(args)

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
            add_activate_parser,
            add_ask_parser,
            add_benchmark_parser,
            add_cache_parser,
            add_config_parser,
            add_daemon_parser,
            add_dashboard_parser,
            add_demo_parser,
            add_deps_parser,
            add_docker_parser,
            add_doctor_parser,
            add_env_parser,
            add_gpu_parser,
            add_health_parser,
            add_history_parser,
            add_import_deps_parser,
            add_install_parser,
            add_license_parser,
            add_notify_parser,
            add_printer_parser,
            add_remove_parser,
            add_role_parser,
            add_sandbox_parser,
            add_stack_parser,
            add_stdin_parser,
            add_status_parser,
            add_systemd_parser,
            add_troubleshoot_parser,
            add_update_parser,
            add_upgrade_parser,
            add_voice_parser,
            add_wizard_parser,
            add_wifi_parser,
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
        # New parsers
        add_demo_parser(subparsers)
        add_dashboard_parser(subparsers)
        add_wizard_parser(subparsers)
        add_status_parser(subparsers)
        add_benchmark_parser(subparsers)
        add_systemd_parser(subparsers)
        add_gpu_parser(subparsers)
        add_printer_parser(subparsers)
        add_voice_parser(subparsers)
        add_docker_parser(subparsers)
        add_notify_parser(subparsers)
        add_role_parser(subparsers)
        add_cache_parser(subparsers)
        add_doctor_parser(subparsers)
        add_activate_parser(subparsers)
        add_upgrade_parser(subparsers)
        add_stdin_parser(subparsers)
        add_deps_parser(subparsers)
        add_health_parser(subparsers)
        add_license_parser(subparsers)
        add_wifi_parser(subparsers)

        return parser

    def dispatch(self, args: argparse.Namespace) -> int:
        """Dispatch command to appropriate handler.

        Returns exit code (0 for success, 1 for failure).
        """
        command = getattr(args, "command", None)

        # Dispatch to handler methods
        handler_map = {
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
            "demo": self.demo,
            "dashboard": self.dashboard,
            "wizard": self.wizard,
            "status": self.status,
            "benchmark": self.benchmark,
            "systemd": self.systemd,
            "gpu": self.gpu,
            "printer": self.printer,
            "wifi": self.wifi,
            "voice": self.voice,
            "docker": self.docker,
            "notify": self.notify,
            "role": self.role,
            "cache": self.cache,
            "doctor": self.doctor,
            "activate": self.activate,
            "upgrade": self.upgrade,
            "stdin": self.stdin,
            "deps": self.deps,
            "health": self.health,
            "license": self.license,
        }

        if command in handler_map:
            return handler_map[command](args)

        return 1


# Re-export main from cli_main for backward compatibility
from cortex.cli_main import main as main

__all__ = ["CortexCLI", "main"]
