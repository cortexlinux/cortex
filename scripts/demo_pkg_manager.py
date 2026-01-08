#!/usr/bin/env python3
import time
import sys
from rich.console import Console

console = Console()

def type_cmd(cmd):
    console.print(f"[bold green]murat@cortex:~$[/bold green] ", end="")
    for char in cmd:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(0.05)
    print()
    time.sleep(0.5)

def demo():
    console.clear()
    console.print("[bold cyan]Cortex Unified Package Manager Demo[/bold cyan]\n")
    time.sleep(1)

    # 1. List Status
    type_cmd("cortex pkg list")
    console.print("""
Package Backends Status
┏━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Backend ┃ Status    ┃ Note                             ┃
┡━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ snap    │ Available │ Use `snap list` to see packages  │
│ flatpak │ Available │ Use `flatpak list` to see packa… │
└─────────┴───────────┴──────────────────────────────────┘
[dim]Full package listing integration is planned for future updates.[/dim]
    """)
    time.sleep(2)

    # 2. Dry Run Install
    type_cmd("cortex pkg install vlc --dry-run")
    console.print("[bold yellow]Multiple backends available (snap, flatpak).[/bold yellow]")
    console.print("[info]Running: flatpak install -y --user vlc...[/info]")
    console.print("[Dry Run] would execute: [bold]flatpak install -y --user vlc[/bold]", style="info")
    time.sleep(2)

    # 3. Scope usage
    type_cmd("cortex pkg install vlc --scope system --dry-run")
    console.print("[info]Running: flatpak install -y --system vlc...[/info]")
    console.print("[Dry Run] would execute: [bold]flatpak install -y --system vlc[/bold]", style="info")
    time.sleep(2)

    console.print("\n[bold green]✨ Demo Completed[/bold green]")

if __name__ == "__main__":
    demo()
