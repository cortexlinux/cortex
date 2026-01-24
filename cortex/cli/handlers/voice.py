"""Voice command handler for Cortex CLI."""

import argparse


class VoiceHandler:
    """Handler for voice command."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    def voice(self, continuous: bool = True, model: str = None) -> int:
        """Voice input mode (F9 to speak, Ctrl+C to exit)."""
        from cortex.voice import run_voice_mode
        return run_voice_mode(continuous=continuous, model=model)


def add_voice_parser(subparsers) -> argparse.ArgumentParser:
    """Add voice parser to subparsers."""
    voice_parser = subparsers.add_parser(
        "voice", help="Voice input mode (F9 to speak, Ctrl+C to exit)"
    )
    voice_parser.add_argument(
        "--single",
        "-s",
        action="store_true",
        help="Record single input and exit (default: continuous mode)",
    )
    voice_parser.add_argument(
        "--model",
        "-m",
        type=str,
        default=None,
        metavar="MODEL",
        choices=[
            "tiny.en",
            "base.en",
            "small.en",
            "medium.en",
            "tiny",
            "base",
            "small",
            "medium",
            "large",
        ],
        help="Whisper model to use",
    )
    return voice_parser
