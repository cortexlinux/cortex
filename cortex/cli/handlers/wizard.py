"""Wizard command handler for Cortex CLI."""

import argparse


class WizardHandler:
    """Handler for wizard command."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def wizard(self) -> int:
        """Configure API key interactively."""
        from cortex.api_key_detector import setup_api_key
        return setup_api_key()


def add_wizard_parser(subparsers) -> argparse.ArgumentParser:
    """Add wizard parser to subparsers."""
    wizard_parser = subparsers.add_parser("wizard", help="Configure API key interactively")
    return wizard_parser
