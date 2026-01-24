"""System command handler for Cortex CLI.

Handles systemd, gpu, printer, wifi commands.
"""

import argparse


class SystemHandler:
    """Handler for system commands."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def systemd(self, service: str, action: str = "status", verbose: bool = False) -> int:
        """Systemd service helper (plain English)."""
        from cortex.systemd import handle_systemd
        return handle_systemd(service, action=action, verbose=verbose)

    def gpu(self, action: str = "status", mode: str = None, verbose: bool = False) -> int:
        """Hybrid GPU (Optimus) manager."""
        from cortex.gpu import handle_gpu
        return handle_gpu(action=action, mode=mode, verbose=verbose)

    def printer(self, action: str = "status", verbose: bool = False) -> int:
        """Printer/Scanner auto-setup."""
        from cortex.printer import handle_printer
        return handle_printer(action=action, verbose=verbose)

    def wifi(self, verbose: bool = False) -> int:
        """WiFi/Bluetooth driver auto-matcher."""
        from cortex.wifi import handle_wifi
        return handle_wifi(verbose=verbose)


def add_systemd_parser(subparsers) -> argparse.ArgumentParser:
    """Add systemd parser to subparsers."""
    systemd_parser = subparsers.add_parser("systemd", help="Systemd service helper (plain English)")
    systemd_parser.add_argument("service", help="Service name")
    systemd_parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "diagnose", "deps"],
        help="Action: status (default), diagnose, deps",
    )
    systemd_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    return systemd_parser


def add_gpu_parser(subparsers) -> argparse.ArgumentParser:
    """Add gpu parser to subparsers."""
    gpu_parser = subparsers.add_parser("gpu", help="Hybrid GPU (Optimus) manager")
    gpu_parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "modes", "switch", "apps"],
        help="Action: status (default), modes, switch, apps",
    )
    gpu_parser.add_argument(
        "mode", nargs="?", help="Mode for switch action (integrated/hybrid/nvidia)"
    )
    gpu_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    return gpu_parser


def add_printer_parser(subparsers) -> argparse.ArgumentParser:
    """Add printer parser to subparsers."""
    printer_parser = subparsers.add_parser("printer", help="Printer/Scanner auto-setup")
    printer_parser.add_argument(
        "action",
        nargs="?",
        default="status",
        choices=["status", "detect"],
        help="Action: status (default), detect",
    )
    printer_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    return printer_parser


def add_wifi_parser(subparsers) -> argparse.ArgumentParser:
    """Add wifi parser to subparsers."""
    wifi_parser = subparsers.add_parser("wifi", help="WiFi/Bluetooth driver auto-matcher")
    return wifi_parser
