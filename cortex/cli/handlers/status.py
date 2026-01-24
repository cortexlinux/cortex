"""Status command handler for Cortex CLI."""

import argparse


class StatusHandler:
    """Handler for status command."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def status(self) -> int:
        """Show comprehensive system status and health checks."""
        from cortex.status import show_status
        return show_status()


def add_status_parser(subparsers) -> argparse.ArgumentParser:
    """Add status parser to subparsers."""
    status_parser = subparsers.add_parser(
        "status", help="Show comprehensive system status and health checks"
    )
    return status_parser
