"""Doctor command handler for Cortex CLI."""

import argparse


class DoctorHandler:
    """Handler for doctor command."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def doctor(self, args: argparse.Namespace) -> int:
        """Handle doctor command."""
        from cortex.doctor import handle_doctor
        return handle_doctor(args)


def add_doctor_parser(subparsers) -> argparse.ArgumentParser:
    """Add doctor parser to subparsers."""
    doctor_parser = subparsers.add_parser("doctor", help="System health check")
    doctor_parser.add_argument("--fix", action="store_true", help="Attempt to fix issues automatically")
    doctor_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    return doctor_parser
