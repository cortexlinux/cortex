"""Cortex CLI Handlers.

Modular command handlers for Cortex CLI.
"""

from cortex.cli.handlers.ask import AskHandlerWrapper, add_ask_parser
from cortex.cli.handlers.benchmark import BenchmarkHandler, add_benchmark_parser
from cortex.cli.handlers.cache import CacheHandler, add_cache_parser
from cortex.cli.handlers.config import ConfigHandler, add_config_parser
from cortex.cli.handlers.daemon import DaemonHandler, add_daemon_parser
from cortex.cli.handlers.dashboard import DashboardHandler, add_dashboard_parser
from cortex.cli.handlers.demo import DemoHandler, add_demo_parser
from cortex.cli.handlers.doctor import DoctorHandler, add_doctor_parser
from cortex.cli.handlers.docker import DockerHandler, add_docker_parser
from cortex.cli.handlers.env import EnvHandler, add_env_parser
from cortex.cli.handlers.history import HistoryHandler, add_history_parser, add_rollback_parser
from cortex.cli.handlers.import_deps import ImportDepHandler, add_import_deps_parser
from cortex.cli.handlers.install import InstallHandler, add_install_parser
from cortex.cli.handlers.license import add_activate_parser, add_license_parser, add_upgrade_parser
from cortex.cli.handlers.misc import (
    MiscHandler,
    add_deps_parser,
    add_health_parser,
    add_stdin_parser,
)
from cortex.cli.handlers.notify import NotifyHandler, add_notify_parser
from cortex.cli.handlers.remove import RemoveHandler, add_remove_parser
from cortex.cli.handlers.role import RoleHandler, add_role_parser
from cortex.cli.handlers.sandbox import SandboxHandler, add_sandbox_parser
from cortex.cli.handlers.stack import StackHandler, add_stack_parser
from cortex.cli.handlers.status import StatusHandler, add_status_parser
from cortex.cli.handlers.system import (
    SystemHandler,
    add_gpu_parser,
    add_printer_parser,
    add_systemd_parser,
    add_wifi_parser,
)
from cortex.cli.handlers.troubleshoot import TroubleshootHandler, add_troubleshoot_parser
from cortex.cli.handlers.update import UpdateHandler, add_update_parser
from cortex.cli.handlers.voice import VoiceHandler, add_voice_parser
from cortex.cli.handlers.wizard import WizardHandler, add_wizard_parser

__all__ = [
    # Ask
    "AskHandlerWrapper",
    "add_ask_parser",
    # Benchmark
    "BenchmarkHandler",
    "add_benchmark_parser",
    # Cache
    "CacheHandler",
    "add_cache_parser",
    # Config
    "ConfigHandler",
    "add_config_parser",
    # Daemon
    "DaemonHandler",
    "add_daemon_parser",
    # Dashboard
    "DashboardHandler",
    "add_dashboard_parser",
    # Demo
    "DemoHandler",
    "add_demo_parser",
    # Doctor
    "DoctorHandler",
    "add_doctor_parser",
    # Docker
    "DockerHandler",
    "add_docker_parser",
    # Env
    "EnvHandler",
    "add_env_parser",
    # History
    "HistoryHandler",
    "add_history_parser",
    "add_rollback_parser",
    # Import
    "ImportDepHandler",
    "add_import_deps_parser",
    # Install
    "InstallHandler",
    "add_install_parser",
    # License/Misc
    "MiscHandler",
    "add_activate_parser",
    "add_license_parser",
    "add_upgrade_parser",
    "add_deps_parser",
    "add_health_parser",
    "add_stdin_parser",
    # Notify
    "NotifyHandler",
    "add_notify_parser",
    # Remove
    "RemoveHandler",
    "add_remove_parser",
    # Role
    "RoleHandler",
    "add_role_parser",
    # Sandbox
    "SandboxHandler",
    "add_sandbox_parser",
    # Stack
    "StackHandler",
    "add_stack_parser",
    # Status
    "StatusHandler",
    "add_status_parser",
    # System
    "SystemHandler",
    "add_systemd_parser",
    "add_gpu_parser",
    "add_printer_parser",
    "add_wifi_parser",
    # Troubleshoot
    "TroubleshootHandler",
    "add_troubleshoot_parser",
    # Update
    "UpdateHandler",
    "add_update_parser",
    # Voice
    "VoiceHandler",
    "add_voice_parser",
    # Wizard
    "WizardHandler",
    "add_wizard_parser",
]
