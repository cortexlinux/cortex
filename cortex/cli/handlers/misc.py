"""Activate, upgrade, and other misc command handlers for Cortex CLI."""

import argparse


class MiscHandler:
    """Handler for miscellaneous commands."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def activate(self, args: argparse.Namespace) -> int:
        """Activate a license key."""
        from cortex.license import handle_activate
        return handle_activate(args)

    def upgrade(self, args: argparse.Namespace) -> int:
        """Upgrade Cortex (alias for update)."""
        from cortex.cli.handlers.update import UpdateHandler
        handler = UpdateHandler(verbose=self.verbose)
        return handler.upgrade(args)

    def stdin(self, args: argparse.Namespace) -> int:
        """Process piped stdin data."""
        from cortex.stdin import handle_stdin
        return handle_stdin(args)

    def deps(self, args: argparse.Namespace) -> int:
        """Dependency version resolver."""
        from cortex.deps import handle_deps
        return handle_deps(args)

    def health(self, args: argparse.Namespace) -> int:
        """System health score and recommendations."""
        from cortex.health import handle_health
        return handle_health(args)

    def license(self, args: argparse.Namespace) -> int:
        """License management."""
        from cortex.license import handle_license
        return handle_license(args)


def add_activate_parser(subparsers) -> argparse.ArgumentParser:
    """Add activate parser to subparsers."""
    activate_parser = subparsers.add_parser("activate", help="Activate a license key")
    activate_parser.add_argument("key", nargs="?", help="License key")
    activate_parser.add_argument("--offline", action="store_true", help="Offline activation")
    return activate_parser


def add_upgrade_parser(subparsers) -> argparse.ArgumentParser:
    """Add upgrade parser to subparsers."""
    upgrade_parser = subparsers.add_parser("upgrade", help="Check for and install Cortex updates")
    upgrade_parser.add_argument("--check", action="store_true", help="Only check for updates")
    upgrade_parser.add_argument("--channel", choices=["stable", "beta", "dev"], help="Update channel")
    return upgrade_parser


def add_stdin_parser(subparsers) -> argparse.ArgumentParser:
    """Add stdin parser to subparsers."""
    stdin_parser = subparsers.add_parser("stdin", help="Process piped stdin data")
    stdin_parser.add_argument("--parse", action="store_true", help="Parse commands from stdin")
    return stdin_parser


def add_deps_parser(subparsers) -> argparse.ArgumentParser:
    """Add deps parser to subparsers."""
    deps_parser = subparsers.add_parser("deps", help="Dependency version resolver")
    deps_parser.add_argument("packages", nargs="+", help="Package names")
    deps_parser.add_argument("--json", action="store_true", help="Output as JSON")
    return deps_parser


def add_health_parser(subparsers) -> argparse.ArgumentParser:
    """Add health parser to subparsers."""
    health_parser = subparsers.add_parser("health", help="System health score and recommendations")
    health_parser.add_argument("--json", action="store_true", help="Output as JSON")
    return health_parser


def add_license_parser(subparsers) -> argparse.ArgumentParser:
    """Add license parser to subparsers."""
    license_parser = subparsers.add_parser("license", help="License management")
    license_subs = license_parser.add_subparsers(dest="license_action", help="License actions")

    license_subs.add_parser("status", help="Show license status")
    license_subs.add_parser("activate", help="Activate license")
    license_subs.add_parser("info", help="Show license information")

    return license_parser
