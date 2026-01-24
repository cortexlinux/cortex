"""Demo command handler for Cortex CLI."""

import argparse


class DemoHandler:
    """Handler for demo command."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def demo(self) -> int:
        """Run a demonstration of Cortex capabilities."""
        from cortex.demo import run_demo
        return run_demo()


def add_demo_parser(subparsers) -> argparse.ArgumentParser:
    """Add demo parser to subparsers."""
    demo_parser = subparsers.add_parser("demo", help="See Cortex in action")
    return demo_parser
