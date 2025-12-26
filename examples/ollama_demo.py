#!/usr/bin/env python3
"""
Example: Using Cortex with Ollama for local LLM inference.

This demonstrates:
1. Checking Ollama installation
2. Using Cortex with local models
3. Comparing local vs cloud performance
4. Privacy-first package management

Author: Cortex Linux Team
License: Apache 2.0
"""

import sys
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Add parent directory to path
sys.path.insert(0, "..")

from cortex.llm_router import LLMRouter, TaskType
from cortex.providers.ollama_provider import OllamaProvider

console = Console()


def check_ollama_status():
    """Check Ollama installation and available models."""
    console.print("\n[bold cyan]🔍 Checking Ollama Status[/bold cyan]")

    provider = OllamaProvider()

    # Check installation
    if provider.is_installed():
        console.print("✅ Ollama installed", style="green")
    else:
        console.print("❌ Ollama not installed", style="red")
        console.print("\nInstall with: curl -fsSL https://ollama.com/install.sh | sh")
        return False

    # Check service
    if provider.is_running():
        console.print("✅ Ollama service running", style="green")
    else:
        console.print("⚠️  Ollama service not running", style="yellow")
        console.print("Starting service...")
        if provider.start_service():
            console.print("✅ Service started", style="green")
        else:
            console.print("❌ Failed to start service", style="red")
            return False

    # List models
    models = provider.get_available_models()
    if models:
        console.print("\n[bold]Available Models:[/bold]")
        for model in models:
            console.print(f"  • {model}", style="cyan")
    else:
        console.print("\n⚠️  No models installed", style="yellow")
        console.print("Install default model: ollama pull phi3:mini")
        return False

    return True


def demo_local_completion():
    """Demonstrate local LLM completion."""
    console.print("\n[bold cyan]💬 Testing Local Completion[/bold cyan]")

    provider = OllamaProvider()

    # Ensure model available
    model = provider.ensure_model_available()
    if not model:
        console.print("❌ No model available", style="red")
        return

    console.print(f"Using model: [cyan]{model}[/cyan]")

    # Test completion
    messages = [{"role": "user", "content": "How do I install nginx on Ubuntu? Be brief."}]

    console.print("\n[yellow]Generating response...[/yellow]")
    start_time = time.time()

    response = provider.complete(messages=messages, temperature=0.7, max_tokens=200)

    elapsed = time.time() - start_time

    console.print(f"\n[bold]Response ({elapsed:.2f}s):[/bold]")
    console.print(Panel(response.get("response", "No response"), style="green"))


def demo_router_with_fallback():
    """Demonstrate LLM router with fallback."""
    console.print("\n[bold cyan]🧭 Testing LLM Router[/bold cyan]")

    router = LLMRouter(prefer_local=True)

    # Test routing decision
    routing = router.route_task(TaskType.SYSTEM_OPERATION)
    console.print(f"\nRouting decision: [cyan]{routing.provider.value}[/cyan]")
    console.print(f"Reasoning: {routing.reasoning}")

    # Test completion
    messages = [{"role": "user", "content": "List 3 lightweight text editors for Ubuntu"}]

    console.print("\n[yellow]Generating response...[/yellow]")
    start_time = time.time()

    try:
        response = router.complete(
            messages=messages, task_type=TaskType.SYSTEM_OPERATION, temperature=0.7, max_tokens=200
        )

        elapsed = time.time() - start_time

        console.print(f"\n[bold]Response from {response.provider.value} ({elapsed:.2f}s):[/bold]")
        console.print(Panel(response.content, style="green"))
        console.print(f"\nCost: ${response.cost_usd:.4f} | Tokens: {response.tokens_used}")

    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")


def show_provider_comparison():
    """Show comparison between providers."""
    console.print("\n[bold cyan]📊 Provider Comparison[/bold cyan]\n")

    table = Table(title="LLM Provider Comparison")

    table.add_column("Feature", style="cyan")
    table.add_column("Ollama (Local)", style="green")
    table.add_column("Claude", style="yellow")
    table.add_column("OpenAI", style="blue")

    table.add_row("Privacy", "100% Local ✅", "Cloud", "Cloud")
    table.add_row("Cost", "$0", "$3-15/1M tokens", "$2-30/1M tokens")
    table.add_row("Offline", "Yes ✅", "No", "No")
    table.add_row("API Key", "Not needed ✅", "Required", "Required")
    table.add_row("Speed", "Varies by HW", "Fast", "Fast")
    table.add_row("Quality", "Good-Excellent", "Excellent", "Excellent")
    table.add_row("Setup", "Auto ✅", "Manual", "Manual")

    console.print(table)


def main():
    """Main demo function."""
    console.print(
        Panel.fit(
            "[bold cyan]Cortex Linux - Ollama Integration Demo[/bold cyan]\n"
            "[dim]Privacy-First, Offline-Capable Package Management[/dim]",
            border_style="cyan",
        )
    )

    # Check Ollama status
    if not check_ollama_status():
        console.print("\n[yellow]⚠️  Ollama not ready. Please install and try again.[/yellow]")
        return

    # Demo local completion
    try:
        demo_local_completion()
    except Exception as e:
        console.print(f"\n[red]Error in local completion: {e}[/red]")

    # Demo router
    try:
        demo_router_with_fallback()
    except Exception as e:
        console.print(f"\n[red]Error in router demo: {e}[/red]")

    # Show comparison
    show_provider_comparison()

    # Final tips
    console.print("\n[bold cyan]💡 Quick Tips[/bold cyan]")
    console.print("• Use [cyan]cortex install <query>[/cyan] for package management")
    console.print("• No API keys needed - fully local by default")
    console.print("• Set ANTHROPIC_API_KEY for cloud fallback")
    console.print("• Manage models: [cyan]ollama list[/cyan], [cyan]ollama pull <model>[/cyan]")
    console.print("\n[dim]Full docs: docs/OLLAMA_INTEGRATION.md[/dim]\n")


if __name__ == "__main__":
    main()
