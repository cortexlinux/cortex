"""Docker command handler for Cortex CLI."""

import argparse


class DockerHandler:
    """Handler for docker command."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

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


def add_docker_parser(subparsers) -> argparse.ArgumentParser:
    """Add docker parser to subparsers."""
    docker_parser = subparsers.add_parser("docker", help="Docker and container utilities")
    docker_subs = docker_parser.add_subparsers(dest="docker_action", help="Docker actions")

    # Add the permissions action to allow fixing file ownership issues
    perm_parser = docker_subs.add_parser(
        "permissions", help="Fix file permissions from bind mounts"
    )

    # Provide an option to skip the manual confirmation prompt
    perm_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    perm_parser.add_argument(
        "--execute", "-e", action="store_true", help="Apply ownership changes (default: dry-run)"
    )

    return docker_parser
