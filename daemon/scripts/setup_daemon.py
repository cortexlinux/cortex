import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import yaml
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

console = Console()

DAEMON_DIR = Path(__file__).parent.parent
BUILD_SCRIPT = DAEMON_DIR / "scripts" / "build.sh"
INSTALL_SCRIPT = DAEMON_DIR / "scripts" / "install.sh"
MODEL_DIR = Path.home() / ".cortex" / "models"
CONFIG_FILE = "/etc/cortex/daemon.yaml"
CONFIG_EXAMPLE = DAEMON_DIR / "config" / "cortexd.yaml.example"

# Recommended models
RECOMMENDED_MODELS = {
    "1": {
        "name": "TinyLlama 1.1B (Fast & Lightweight)",
        "url": "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
        "size": "600MB",
        "description": "Best for testing and low-resource systems",
    },
    "2": {
        "name": "Mistral 7B (Balanced)",
        "url": "https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf",
        "size": "4GB",
        "description": "Best for production with good balance of speed and quality",
    },
    "3": {
        "name": "Llama 2 13B (High Quality)",
        "url": "https://huggingface.co/TheBloke/Llama-2-13B-Chat-GGUF/resolve/main/llama-2-13b-chat.Q4_K_M.gguf",
        "size": "8GB",
        "description": "Best for high-quality responses",
    },
}


def check_daemon_built() -> bool:
    """
    Check if the cortexd daemon binary has been built.

    Checks for the existence of the cortexd binary at DAEMON_DIR / "build" / "cortexd".

    Returns:
        bool: True if the daemon binary exists, False otherwise.
    """
    return (DAEMON_DIR / "build" / "cortexd").exists()


def clean_build() -> None:
    """
    Remove the previous build directory to ensure a clean build.

    Removes DAEMON_DIR / "build" using sudo rm -rf. Prints status messages
    to console. On failure, logs an error and calls sys.exit(1) to terminate.

    Returns:
        None
    """
    build_dir = DAEMON_DIR / "build"
    if build_dir.exists():
        console.print(f"[cyan]Removing previous build directory: {build_dir}[/cyan]")
        result = subprocess.run(["sudo", "rm", "-rf", str(build_dir)], check=False)
        if result.returncode != 0:
            console.print("[red]Failed to remove previous build directory.[/red]")
            sys.exit(1)


def build_daemon() -> bool:
    """
    Build the cortexd daemon from source.

    Runs the BUILD_SCRIPT (daemon/scripts/build.sh) with "Release" argument
    using subprocess.run.

    Returns:
        bool: True if the build completed successfully (exit code 0), False otherwise.
    """
    console.print("[cyan]Building the daemon...[/cyan]")
    result = subprocess.run(["bash", str(BUILD_SCRIPT), "Release"], check=False)
    return result.returncode == 0


def install_daemon() -> bool:
    """
    Install the cortexd daemon system-wide.

    Runs the INSTALL_SCRIPT (daemon/scripts/install.sh) with sudo using
    subprocess.run.

    Returns:
        bool: True if the installation completed successfully (exit code 0),
              False otherwise.
    """
    console.print("[cyan]Installing the daemon...[/cyan]")
    result = subprocess.run(["sudo", str(INSTALL_SCRIPT)], check=False)
    return result.returncode == 0


def download_model() -> Path | None:
    """
    Download or select an LLM model for the cortex daemon.

    Presents options to use an existing model or download a new one from
    recommended sources or a custom URL. Validates and sanitizes URLs to
    prevent security issues.

    Returns:
        Path | None: Path to the downloaded/selected model file, or None if
                     download failed or was cancelled.
    """
    console.print("[cyan]Setting up LLM model...[/cyan]\n")

    # Check for existing models
    existing_models = []
    if MODEL_DIR.exists():
        existing_models = list(MODEL_DIR.glob("*.gguf"))

    if existing_models:
        console.print("[green]Found existing models in ~/.cortex/models:[/green]")
        for idx, model in enumerate(existing_models, 1):
            console.print(f"  {idx}. {model.name}")

        use_existing = Confirm.ask("\nDo you want to use an existing model?")
        if use_existing:
            if len(existing_models) == 1:
                return existing_models[0]
            else:
                choice = Prompt.ask(
                    "Select a model", choices=[str(i) for i in range(1, len(existing_models) + 1)]
                )
                return existing_models[int(choice) - 1]

        console.print("\n[cyan]Proceeding to download a new model...[/cyan]\n")

    # Display recommended models
    table = Table(title="Recommended Models")
    table.add_column("Option", style="cyan")
    table.add_column("Model", style="green")
    table.add_column("Size")
    table.add_column("Description")

    for key, model in RECOMMENDED_MODELS.items():
        table.add_row(key, model["name"], model["size"], model["description"])

    console.print(table)
    console.print("\n[cyan]Option 4:[/cyan] Custom model URL")

    choice = Prompt.ask("Select an option (1-4)", choices=["1", "2", "3", "4"])

    if choice in RECOMMENDED_MODELS:
        model_url = RECOMMENDED_MODELS[choice]["url"]
        console.print(f"[green]Selected: {RECOMMENDED_MODELS[choice]['name']}[/green]")
    else:
        model_url = Prompt.ask("Enter the model URL")

    # Validate and sanitize the URL
    parsed_url = urlparse(model_url)
    if parsed_url.scheme not in ("http", "https"):
        console.print("[red]Invalid URL scheme. Only http and https are allowed.[/red]")
        return None
    if not parsed_url.netloc:
        console.print("[red]Invalid URL: missing host/domain.[/red]")
        return None

    # Derive a safe filename from the URL path
    url_path = Path(parsed_url.path)
    raw_filename = url_path.name if url_path.name else ""

    # Reject filenames with path traversal or empty names
    if not raw_filename or ".." in raw_filename or raw_filename.startswith("/"):
        console.print("[red]Invalid or unsafe filename in URL. Using generated name.[/red]")
        # Generate a safe fallback name based on URL hash
        import hashlib

        url_hash = hashlib.sha256(model_url.encode()).hexdigest()[:12]
        raw_filename = f"model_{url_hash}.gguf"

    # Clean the filename: only allow alphanumerics, dots, hyphens, underscores
    safe_filename = re.sub(r"[^\w.\-]", "_", raw_filename)
    if not safe_filename:
        safe_filename = "downloaded_model.gguf"

    os.makedirs(MODEL_DIR, exist_ok=True)

    # Construct model_path safely and verify it stays within MODEL_DIR
    model_path = (MODEL_DIR / safe_filename).resolve()
    if not str(model_path).startswith(str(MODEL_DIR.resolve())):
        console.print("[red]Security error: model path escapes designated directory.[/red]")
        return None

    console.print(f"[cyan]Downloading to {model_path}...[/cyan]")
    # Use subprocess with list arguments (no shell) after URL validation
    result = subprocess.run(["wget", model_url, "-O", str(model_path)], check=False)
    return model_path if result.returncode == 0 else None


def setup_model(model_path: str) -> bool:
    """
    Attempt to load an LLM model into the cortex daemon.

    Tries multiple methods to load the model (sg for group membership, direct command).
    Falls back to configuring auto-load if immediate loading fails due to permissions.

    Args:
        model_path: Path to the GGUF model file to load.

    Returns:
        bool: True if model was loaded or auto-load should be configured,
              False if loading failed with a non-recoverable error.
    """
    console.print(f"[cyan]Loading model: {model_path}[/cyan]")
    console.print("[cyan]This may take a minute depending on model size...[/cyan]")

    # Try loading the model - use sg (switch group) to run with cortex group
    # This is needed because group membership from install won't take effect
    # until logout/login, but sg can run a command with the new group immediately
    try:
        # First, try with sg (switch group) to use new group membership
        result = subprocess.run(
            ["sg", "cortex", "-c", f"cortex daemon llm load {model_path}"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True

        # If sg failed (group might not exist yet), try direct command
        result = subprocess.run(
            ["cortex", "daemon", "llm", "load", str(model_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True

        # If still failing, show the error
        if "Permission denied" in result.stderr or "Permission denied" in result.stdout:
            console.print("[yellow]Permission denied - will configure auto-load instead.[/yellow]")
            console.print(
                "[yellow]The model will load automatically when the daemon restarts.[/yellow]"
            )
            return True  # Return True so we continue to configure auto-load

        console.print(f"[red]Error: {result.stderr or result.stdout}[/red]")
        return False

    except Exception as e:
        console.print(f"[yellow]Could not load model immediately: {e}[/yellow]")
        console.print("[yellow]Will configure auto-load instead.[/yellow]")
        return True  # Continue to configure auto-load


def configure_auto_load(model_path: str) -> None:
    """
    Configure the cortex daemon to auto-load the specified model on startup.

    Updates the daemon configuration file (/etc/cortex/daemon.yaml) to set the
    model_path and disable lazy_load, then restarts the daemon service.

    Args:
        model_path: Path to the GGUF model file to configure for auto-loading.

    Returns:
        None. Exits the program with code 1 on failure.
    """
    console.print("[cyan]Configuring auto-load for the model...[/cyan]")
    # Create /etc/cortex directory if it doesn't exist
    subprocess.run(["sudo", "mkdir", "-p", "/etc/cortex"], check=False)

    # Check if config already exists
    config_exists = Path(CONFIG_FILE).exists()

    if not config_exists:
        # Copy example config and modify it
        console.print("[cyan]Creating daemon configuration file...[/cyan]")
        subprocess.run(["sudo", "cp", str(CONFIG_EXAMPLE), CONFIG_FILE], check=False)

    # Use YAML library to safely update the configuration instead of sed
    # This avoids shell injection risks from special characters in model_path
    try:
        # Read the current config file
        result = subprocess.run(
            ["sudo", "cat", CONFIG_FILE], capture_output=True, text=True, check=True
        )
        config = yaml.safe_load(result.stdout) or {}

        # Update the configuration values
        config["model_path"] = str(model_path)
        config["lazy_load"] = False

        # Write the updated config back via sudo tee
        updated_yaml = yaml.dump(config, default_flow_style=False, sort_keys=False)
        write_result = subprocess.run(
            ["sudo", "tee", CONFIG_FILE],
            input=updated_yaml,
            text=True,
            capture_output=True,
            check=False,
        )

        if write_result.returncode != 0:
            console.print(
                f"[red]Failed to write config file (exit code {write_result.returncode})[/red]"
            )
            sys.exit(1)

        console.print(
            f"[green]Model configured to auto-load on daemon startup: {model_path}[/green]"
        )
        console.print("[cyan]Restarting daemon to apply configuration...[/cyan]")
        subprocess.run(["sudo", "systemctl", "restart", "cortexd"], check=False)
        console.print("[green]Daemon restarted with model loaded![/green]")

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Failed to read config file: {e}[/red]")
        sys.exit(1)
    except yaml.YAMLError as e:
        console.print(f"[red]Failed to parse config file: {e}[/red]")
        sys.exit(1)


def main() -> int:
    """
    Interactive setup wizard for the Cortex daemon.

    Guides the user through building, installing, and configuring the cortexd daemon,
    including optional LLM model setup.

    Returns:
        int: Exit code (0 for success, 1 for failure). The function calls sys.exit()
             directly on failures, so the return value is primarily for documentation
             and potential future refactoring.
    """
    console.print(
        "\n[bold cyan]╔══════════════════════════════════════════════════════════════╗[/bold cyan]"
    )
    console.print(
        "[bold cyan]║           Cortex Daemon Interactive Setup                    ║[/bold cyan]"
    )
    console.print(
        "[bold cyan]╚══════════════════════════════════════════════════════════════╝[/bold cyan]\n"
    )

    if not check_daemon_built():
        if Confirm.ask("Daemon not built. Do you want to build it now?"):
            if not build_daemon():
                console.print("[red]Failed to build the daemon.[/red]")
                sys.exit(1)
        else:
            console.print("[yellow]Cannot proceed without building the daemon.[/yellow]")
            sys.exit(1)
    else:
        if Confirm.ask("Daemon already built. Do you want to rebuild it?"):
            clean_build()
            if not build_daemon():
                console.print("[red]Failed to build the daemon.[/red]")
                sys.exit(1)

    if not install_daemon():
        console.print("[red]Failed to install the daemon.[/red]")
        sys.exit(1)

    # Ask if user wants to set up a model
    console.print("")
    if not Confirm.ask("Do you want to set up an LLM model now?", default=True):
        console.print("\n[green]✓ Daemon installed successfully![/green]")
        console.print(
            "[cyan]You can set up a model later with:[/cyan] cortex daemon llm load <model_path>\n"
        )
        sys.exit(0)

    model_path = download_model()
    if model_path:
        # Configure auto-load (this will also restart the daemon)
        configure_auto_load(model_path)

        console.print(
            "\n[bold green]╔══════════════════════════════════════════════════════════════╗[/bold green]"
        )
        console.print(
            "[bold green]║              Setup Completed Successfully!                   ║[/bold green]"
        )
        console.print(
            "[bold green]╚══════════════════════════════════════════════════════════════╝[/bold green]"
        )
        console.print("\n[cyan]The daemon is now running with your model loaded.[/cyan]")
        console.print("[cyan]Try it out:[/cyan] cortex ask 'What packages do I have installed?'\n")
        return 0
    else:
        console.print("[red]Failed to download/select the model.[/red]")
        console.print("[yellow]Daemon is installed but no model is configured.[/yellow]")
        sys.exit(1)

    return 0  # Unreachable, but satisfies type checker


if __name__ == "__main__":
    sys.exit(main())
