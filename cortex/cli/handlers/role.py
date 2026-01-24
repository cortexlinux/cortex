"""Role command handler for Cortex CLI."""

import argparse


class RoleHandler:
    """Handler for role command."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def role(self, args: argparse.Namespace) -> int:
        """Handle role command."""
        from cortex.role_manager import handle_role
        return handle_role(args)


def add_role_parser(subparsers) -> argparse.ArgumentParser:
    """Add role parser to subparsers."""
    role_parser = subparsers.add_parser(
        "role", help="AI-driven system personality and context management"
    )
    role_subs = role_parser.add_subparsers(dest="role_action", help="Role actions")

    # Subcommand: role detect
    role_subs.add_parser(
        "detect", help="Dynamically sense system context and shell patterns to suggest an AI role"
    )

    # Subcommand: role set <slug>
    role_set_parser = role_subs.add_parser(
        "set", help="Manually override the system role and receive tailored recommendations"
    )
    role_set_parser.add_argument(
        "role_slug",
        help="Role identifier (e.g., developer, data-scientist, sysadmin)"
    )

    # Subcommand: role list
    role_subs.add_parser("list", help="List all available AI roles")

    # Subcommand: role suggest
    suggest_parser = role_subs.add_parser(
        "suggest", help="Get role recommendations based on current context"
    )
    suggest_parser.add_argument(
        "--context", "-c", help="Additional context for suggestion"
    )

    return role_parser
