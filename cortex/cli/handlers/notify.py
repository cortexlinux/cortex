"""Notify command handler for Cortex CLI."""

import argparse


class NotifyHandler:
    """Handler for notify command."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def notify(self, args: argparse.Namespace) -> int:
        """Handle notify command."""
        from cortex.notification_manager import handle_notify
        return handle_notify(args)


def add_notify_parser(subparsers) -> argparse.ArgumentParser:
    """Add notify parser to subparsers."""
    notify_parser = subparsers.add_parser("notify", help="Manage desktop notifications")
    notify_subs = notify_parser.add_subparsers(dest="notify_action", help="Notify actions")

    notify_subs.add_parser("config", help="Show configuration")
    notify_subs.add_parser("enable", help="Enable notifications")
    notify_subs.add_parser("disable", help="Disable notifications")

    dnd_parser = notify_subs.add_parser("dnd", help="Configure DND window")
    dnd_parser.add_argument("start", help="Start time (HH:MM)")
    dnd_parser.add_argument("end", help="End time (HH:MM)")

    send_parser = notify_subs.add_parser("send", help="Send test notification")
    send_parser.add_argument("message", help="Notification message")
    send_parser.add_argument("--title", default="Cortex Notification")
    send_parser.add_argument("--level", choices=["low", "normal", "critical"], default="normal")
    send_parser.add_argument("--actions", nargs="*", help="Action buttons")

    return notify_parser
