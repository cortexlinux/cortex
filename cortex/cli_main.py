"""Cortex CLI - Main entry point.

This is the main entry point for the Cortex CLI. It uses the CortexCLI facade
from cortex.cli which delegates to modular handlers.
"""

import argparse
import logging
import os
import sys

from rich.console import Console

from cortex.branding import VERSION, console, cx_print, show_banner
from cortex.i18n import SUPPORTED_LANGUAGES, set_language

# Suppress noisy log messages
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("cortex.installation_history").setLevel(logging.ERROR)


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _handle_set_language(lang_code: str) -> int:
    """Handle the --set-language global flag."""
    if lang_code not in SUPPORTED_LANGUAGES:
        cx_print(f"Error: Language '{lang_code}' not supported.", "error")
        cx_print(f"Available languages: {', '.join(SUPPORTED_LANGUAGES.keys())}", "info")
        return 1
    
    set_language(lang_code)
    cx_print(f"Language set to {SUPPORTED_LANGUAGES[lang_code]['name']}", "success")
    return 0


def show_rich_help():
    """Show rich help when no command is provided."""
    from rich.markdown import Markdown
    from rich.panel import Panel
    
    help_text = """
# Cortex Linux AI

**AI-Powered Linux Package Manager**

## Quick Start
```bash
cortex install nginx              # Install a package
cortex ask "how do I setup SSL?" # Ask questions in plain English
cortex status                    # Check system status
```

## Commands
**Package Management:**
- `install`   - Install software
- `remove`    - Remove packages safely
- `history`   - View installation history
- `rollback`  - Rollback an installation

**AI Features:**
- `ask`       - Ask questions about your system
- `do`        - Execute commands with AI approval

**System:**
- `status`    - System health check
- `doctor`    - Diagnose and fix issues
- `daemon`    - Manage the background daemon

**Configuration:**
- `config`    - Configure settings
- `wizard`    - Interactive setup wizard

## Help
- `cortex --help`     - Show all commands
- `cortex <cmd> --help` - Show command-specific help

For more information: https://cortexlinux.com
"""
    console.print(Panel(Markdown(help_text), title="Cortex Linux AI", border_style="blue"))


def main():
    """Main entry point for Cortex CLI."""
    # Load environment variables first
    from cortex.env_loader import load_env
    load_env()
    
    # Import facade AFTER loading env
    from cortex.cli import CortexCLI
    
    # Create parser using facade
    cli = CortexCLI()
    parser = cli.create_parser()
    
    # Add global flags
    parser.add_argument("--version", "-V", action="version", version=f"cortex {VERSION}")
    parser.add_argument("--set-language", "--language", dest="set_language",
                        metavar="LANG", help="Set display language (e.g., en, es, fr, de, zh)")
    
    # Parse args
    args = parser.parse_args()
    
    # Handle --set-language first
    if getattr(args, "set_language", None):
        result = _handle_set_language(args.set_language)
        if not args.command:
            return result
        if result != 0:
            return result
    
    # Show help if no command
    if not args.command:
        show_rich_help()
        return 0
    
    # Dispatch to facade
    try:
        result = cli.dispatch(args)
        return result if result is not None else 0
    except KeyboardInterrupt:
        console.print("\nInterrupted")
        return 130
    except Exception as e:
        console.print(f"Error: {e}", style="red")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
