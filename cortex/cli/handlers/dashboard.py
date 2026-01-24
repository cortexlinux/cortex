"""Dashboard command handler for Cortex CLI."""

import argparse


class DashboardHandler:
    """Handler for dashboard command."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def dashboard(self) -> int:
        """Launch the real-time system monitoring dashboard."""
        from cortex.dashboard import run_dashboard
        return run_dashboard()


def add_dashboard_parser(subparsers) -> argparse.ArgumentParser:
    """Add dashboard parser to subparsers."""
    dashboard_parser = subparsers.add_parser(
        "dashboard", help="Real-time system monitoring dashboard"
    )
    return dashboard_parser
