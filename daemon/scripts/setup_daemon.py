import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import yaml
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

console = Console()

# Audit logging database path
AUDIT_DB_PATH = Path.home() / ".cortex" / "history.db"


def init_audit_db() -> bool:
    """
    Initialize the audit database for installer actions.

    Creates ~/.cortex directory if needed and sets up a SQLite database
    with an events table for logging installer actions.

    Returns:
        bool: True if initialization succeeded, False otherwise.
    """
    try:
        # Create ~/.cortex directory
        audit_dir = AUDIT_DB_PATH.parent
        audit_dir.mkdir(parents=True, exist_ok=True)

        # Create/connect to database
        conn = sqlite3.connect(str(AUDIT_DB_PATH))
        cursor = conn.cursor()

        # Create events table if it doesn't exist
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                details TEXT,
                success INTEGER DEFAULT 1
            )
        """
        )

        conn.commit()
        conn.close()
        return True
    except (sqlite3.Error, OSError) as e:
        console.print(f"[dim]Warning: Could not initialize audit database: {e}[/dim]")
        return False


def log_audit_event(event_type: str, details: str, success: bool = True) -> None:
    """
    Log an audit event to the history database.

    Inserts a timestamped row into the events table. Handles errors gracefully
    without crashing the installer.

    Args:
        event_type: Type of event (e.g., "install_dependencies", "build_daemon").
        details: Human-readable description of the event.
        success: Whether the action succeeded (default True).
    """
    try:
        # Ensure the database exists
        if not AUDIT_DB_PATH.exists():
            if not init_audit_db():
                return

        conn = sqlite3.connect(str(AUDIT_DB_PATH))
        cursor = conn.cursor()

        timestamp = datetime.utcnow().isoformat() + "Z"
        cursor.execute(
            "INSERT INTO events (timestamp, event_type, details, success) VALUES (?, ?, ?, ?)",
            (timestamp, event_type, details, 1 if success else 0),
        )

        conn.commit()
        conn.close()
    except (sqlite3.Error, OSError) as e:
        # Log to console but don't crash the installer
        console.print(f"[dim]Warning: Could not log audit event: {e}[/dim]")


DAEMON_DIR = Path(__file__).parent.parent
BUILD_SCRIPT = DAEMON_DIR / "scripts" / "build.sh"
INSTALL_SCRIPT = DAEMON_DIR / "scripts" / "install.sh"
INSTALL_LLM_SCRIPT = DAEMON_DIR / "scripts" / "install-llm.sh"
MODEL_DIR = Path.home() / ".cortex" / "models"
CONFIG_FILE = "/etc/cortex/daemon.yaml"
CONFIG_EXAMPLE = DAEMON_DIR / "config" / "cortexd.yaml.example"
LLM_ENV_FILE = "/etc/cortex/llm.env"
CORTEX_ENV_FILE = Path.home() / ".cortex" / ".env"

# System dependencies required to build the daemon (apt packages)
DAEMON_SYSTEM_DEPENDENCIES = [
    "cmake",
    "build-essential",
    "libsystemd-dev",
    "libssl-dev",
    "libsqlite3-dev",
    "uuid-dev",
    "pkg-config",
    "libcap-dev",
]

# Recommended models for local llama.cpp
RECOMMENDED_MODELS = {
    "1": {
        "name": "TinyLlama 1.1B (Fast & Lightweight)",
        "url": "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
        "size": "600MB",
        "ram": "2GB",
        "description": "Best for testing and low-resource systems",
    },
    "2": {
        "name": "Phi 2.7B (Fast & Capable)",
        "url": "https://huggingface.co/TheBloke/phi-2-GGUF/resolve/main/phi-2.Q4_K_M.gguf",
        "size": "1.6GB",
        "ram": "3GB",
        "description": "Good balance of speed and capability",
    },
    "3": {
        "name": "Mistral 7B (Balanced)",
        "url": "https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf",
        "size": "4GB",
        "ram": "8GB",
        "description": "Best for production with good balance of speed and quality",
    },
    "4": {
        "name": "Llama 2 13B (High Quality)",
        "url": "https://huggingface.co/TheBloke/Llama-2-13B-Chat-GGUF/resolve/main/llama-2-13b-chat.Q4_K_M.gguf",
        "size": "8GB",
        "ram": "16GB",
        "description": "Best for high-quality responses",
    },
}

# Cloud API providers
CLOUD_PROVIDERS = {
    "1": {
        "name": "Claude (Anthropic)",
        "provider": "claude",
        "env_var": "ANTHROPIC_API_KEY",
        "description": "Recommended - Best reasoning and safety",
    },
    "2": {
        "name": "OpenAI (GPT-4)",
        "provider": "openai",
        "env_var": "OPENAI_API_KEY",
        "description": "Popular choice with broad capabilities",
    },
}


def check_package_installed(package: str) -> bool:
    """
    Check if a system package is installed via dpkg.

    Args:
        package: Name of the apt package to check.

    Returns:
        bool: True if the package is installed, False otherwise.
    """
    result = subprocess.run(
        ["dpkg", "-s", package],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def check_system_dependencies() -> tuple[list[str], list[str]]:
    """
    Check which system dependencies are installed and which are missing.

    Returns:
        tuple: (installed_packages, missing_packages)
    """
    installed = []
    missing = []

    for package in DAEMON_SYSTEM_DEPENDENCIES:
        if check_package_installed(package):
            installed.append(package)
        else:
            missing.append(package)

    return installed, missing


def install_system_dependencies(packages: list[str]) -> bool:
    """
    Install system dependencies using apt-get.

    Args:
        packages: List of package names to install.

    Returns:
        bool: True if installation succeeded, False otherwise.
    """
    if not packages:
        return True

    console.print(f"\n[cyan]Installing {len(packages)} system package(s)...[/cyan]")
    console.print(f"[dim]Packages: {', '.join(packages)}[/dim]\n")

    # Update package list first
    console.print("[cyan]Updating package list...[/cyan]")
    update_result = subprocess.run(
        ["sudo", "apt-get", "update"],
        check=False,
    )
    if update_result.returncode != 0:
        console.print("[yellow]Warning: apt-get update failed, continuing anyway...[/yellow]")

    # Install packages
    install_cmd = ["sudo", "apt-get", "install", "-y"] + packages
    result = subprocess.run(install_cmd, check=False)

    if result.returncode == 0:
        console.print(f"[green]✓ Successfully installed {len(packages)} package(s)[/green]")
        log_audit_event(
            "install_system_dependencies",
            f"Installed {len(packages)} package(s): {', '.join(packages)}",
            success=True,
        )
        return True
    else:
        console.print("[red]✗ Failed to install some packages[/red]")
        log_audit_event(
            "install_system_dependencies",
            f"Failed to install package(s): {', '.join(packages)}",
            success=False,
        )
        return False


def setup_system_dependencies() -> bool:
    """
    Check and install required system dependencies for building the daemon.

    Displays a table of dependencies with their status and prompts the user
    to install missing ones.

    Returns:
        bool: True if all dependencies are satisfied, False otherwise.
    """
    console.print("\n[bold cyan]Checking System Dependencies[/bold cyan]\n")

    installed, missing = check_system_dependencies()

    # Display dependency status table
    table = Table(title="Build Dependencies")
    table.add_column("Package", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Description")

    package_descriptions = {
        "cmake": "Build system generator",
        "build-essential": "GCC, G++, make, and other build tools",
        "libsystemd-dev": "systemd integration headers",
        "libssl-dev": "OpenSSL development libraries",
        "libsqlite3-dev": "SQLite3 development libraries",
        "uuid-dev": "UUID generation libraries",
        "pkg-config": "Package configuration tool",
        "libcap-dev": "Linux capabilities library",
    }

    for package in DAEMON_SYSTEM_DEPENDENCIES:
        status = "[green]✓ Installed[/green]" if package in installed else "[red]✗ Missing[/red]"
        description = package_descriptions.get(package, "")
        table.add_row(package, status, description)

    console.print(table)

    if not missing:
        console.print("\n[green]✓ All system dependencies are installed![/green]")
        return True

    console.print(
        f"\n[yellow]⚠ Missing {len(missing)} required package(s): {', '.join(missing)}[/yellow]"
    )

    if Confirm.ask("\nDo you want to install the missing dependencies now?", default=True):
        if install_system_dependencies(missing):
            # Verify installation
            _, still_missing = check_system_dependencies()
            if still_missing:
                console.print(f"[red]Some packages still missing: {', '.join(still_missing)}[/red]")
                return False
            return True
        else:
            return False
    else:
        console.print("[yellow]Cannot build daemon without required dependencies.[/yellow]")
        console.print("\n[cyan]You can install them manually with:[/cyan]")
        console.print(f"[dim]  sudo apt-get install -y {' '.join(missing)}[/dim]\n")
        return False


def choose_llm_backend() -> str:
    """
    Let user choose between Cloud APIs or Local llama.cpp.

    Displays a table with options and prompts user to select.

    Returns:
        str: "cloud", "local", or "none"
    """
    console.print("\n[bold cyan]LLM Backend Configuration[/bold cyan]\n")
    console.print("Choose how Cortex will handle AI/LLM requests:\n")

    table = Table(title="LLM Backend Options")
    table.add_column("Option", style="cyan", width=8)
    table.add_column("Backend", style="green", width=20)
    table.add_column("Requirements", width=25)
    table.add_column("Best For", width=35)

    table.add_row(
        "1",
        "Cloud APIs",
        "API key (internet required)",
        "Best quality, no local resources needed",
    )
    table.add_row(
        "2",
        "Local llama.cpp",
        "2-16GB RAM, GGUF model",
        "Free, private, works offline",
    )
    table.add_row(
        "3",
        "None (skip)",
        "None",
        "Configure LLM later",
    )

    console.print(table)
    console.print()

    choice = Prompt.ask(
        "Select LLM backend",
        choices=["1", "2", "3"],
        default="1",
    )

    if choice == "1":
        return "cloud"
    elif choice == "2":
        return "local"
    else:
        return "none"


def setup_cloud_api() -> dict | None:
    """
    Configure cloud API provider and get API key.

    Returns:
        dict | None: Configuration dict with provider and api_key, or None if cancelled.
    """
    console.print("\n[bold cyan]Cloud API Setup[/bold cyan]\n")

    table = Table(title="Available Cloud Providers")
    table.add_column("Option", style="cyan")
    table.add_column("Provider", style="green")
    table.add_column("Description")

    for key, provider in CLOUD_PROVIDERS.items():
        table.add_row(key, provider["name"], provider["description"])

    console.print(table)
    console.print()

    choice = Prompt.ask("Select provider", choices=["1", "2"], default="1")
    provider_info = CLOUD_PROVIDERS[choice]

    console.print(f"\n[cyan]Selected: {provider_info['name']}[/cyan]")
    console.print(f"[dim]Environment variable: {provider_info['env_var']}[/dim]\n")

    # Check if API key already exists in environment
    existing_key = os.environ.get(provider_info["env_var"])
    if existing_key:
        console.print(f"[green]✓ Found existing {provider_info['env_var']} in environment[/green]")
        if not Confirm.ask("Do you want to use a different key?", default=False):
            return {
                "provider": provider_info["provider"],
                "api_key": existing_key,
                "env_var": provider_info["env_var"],
            }

    api_key = Prompt.ask(f"Enter your {provider_info['name']} API key", password=True)

    if not api_key:
        console.print("[yellow]No API key provided. Skipping cloud setup.[/yellow]")
        return None

    return {
        "provider": provider_info["provider"],
        "api_key": api_key,
        "env_var": provider_info["env_var"],
    }


def save_cloud_api_config(config: dict) -> None:
    """
    Save cloud API configuration to ~/.cortex/.env file.

    Args:
        config: Dict with provider, api_key, and env_var keys.
    """
    console.print("[cyan]Saving API configuration...[/cyan]")

    # Create ~/.cortex directory
    cortex_dir = Path.home() / ".cortex"
    cortex_dir.mkdir(parents=True, exist_ok=True)

    env_file = cortex_dir / ".env"

    # Read existing env file if it exists
    existing_lines = []
    if env_file.exists():
        with open(env_file) as f:
            existing_lines = f.readlines()

    # Update or add the API key
    env_var = config["env_var"]
    api_key = config["api_key"]
    provider = config["provider"]

    # Filter out existing entries for this env var and CORTEX_PROVIDER
    new_lines = [
        line
        for line in existing_lines
        if not line.startswith(f"{env_var}=") and not line.startswith("CORTEX_PROVIDER=")
    ]

    # Add new entries
    new_lines.append(f"CORTEX_PROVIDER={provider}\n")
    new_lines.append(f"{env_var}={api_key}\n")

    # Write back
    with open(env_file, "w") as f:
        f.writelines(new_lines)

    # Set restrictive permissions
    os.chmod(env_file, 0o600)

    console.print(f"[green]✓ API key saved to {env_file}[/green]")
    console.print(f"[green]✓ Provider set to: {provider}[/green]")

    log_audit_event(
        "save_cloud_api_config",
        f"Saved cloud API configuration for provider: {provider}",
        success=True,
    )


def check_llama_server() -> str | None:
    """
    Check if llama-server is installed.

    Returns:
        str | None: Path to llama-server if found, None otherwise.
    """
    result = subprocess.run(
        ["which", "llama-server"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        path = result.stdout.strip()
        console.print(f"[green]✓ llama-server found: {path}[/green]")
        return path

    # Check common locations
    common_paths = [
        "/usr/local/bin/llama-server",
        "/usr/bin/llama-server",
        str(Path.home() / ".local" / "bin" / "llama-server"),
    ]
    for path in common_paths:
        if Path(path).exists():
            console.print(f"[green]✓ llama-server found: {path}[/green]")
            return path

    console.print("[yellow]⚠ llama-server not found[/yellow]")
    return None


# System dependencies required to build llama.cpp from source
LLAMA_CPP_BUILD_DEPENDENCIES = [
    "cmake",
    "build-essential",
    "git",
]


def check_llama_cpp_build_dependencies() -> tuple[list[str], list[str]]:
    """
    Check which dependencies for building llama.cpp are installed.

    Returns:
        tuple: (installed_packages, missing_packages)
    """
    installed = []
    missing = []

    for package in LLAMA_CPP_BUILD_DEPENDENCIES:
        if check_package_installed(package):
            installed.append(package)
        else:
            missing.append(package)

    return installed, missing


def get_system_architecture() -> str:
    """
    Get the system architecture for downloading pre-built binaries.

    Returns:
        str: Architecture string (e.g., "x86_64", "aarch64")
    """
    import platform

    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    elif machine in ("aarch64", "arm64"):
        return "aarch64"
    else:
        return machine


def install_llama_cpp_from_source() -> bool:
    """
    Build and install llama.cpp from source.

    Returns:
        bool: True if installation succeeded, False otherwise.
    """
    console.print("\n[bold cyan]Building llama.cpp from source[/bold cyan]\n")

    # Check build dependencies
    installed, missing = check_llama_cpp_build_dependencies()

    if missing:
        console.print(f"[yellow]Missing build dependencies: {', '.join(missing)}[/yellow]")
        if Confirm.ask("Install missing dependencies?", default=True):
            if not install_system_dependencies(missing):
                console.print("[red]Failed to install build dependencies.[/red]")
                return False
        else:
            console.print("[red]Cannot build without dependencies.[/red]")
            return False

    # Clone llama.cpp
    llama_cpp_dir = Path.home() / ".local" / "src" / "llama.cpp"
    llama_cpp_dir.parent.mkdir(parents=True, exist_ok=True)

    if llama_cpp_dir.exists():
        console.print(f"[cyan]llama.cpp source found at {llama_cpp_dir}[/cyan]")
        if Confirm.ask("Update existing source?", default=True):
            console.print("[cyan]Pulling latest changes...[/cyan]")
            result = subprocess.run(
                ["git", "pull"],
                cwd=llama_cpp_dir,
                check=False,
            )
            if result.returncode != 0:
                console.print(
                    "[yellow]Warning: git pull failed, continuing with existing source[/yellow]"
                )
    else:
        console.print("[cyan]Cloning llama.cpp repository...[/cyan]")
        result = subprocess.run(
            ["git", "clone", "https://github.com/ggerganov/llama.cpp.git", str(llama_cpp_dir)],
            check=False,
        )
        if result.returncode != 0:
            console.print("[red]Failed to clone llama.cpp repository.[/red]")
            return False

    # Build llama.cpp
    build_dir = llama_cpp_dir / "build"
    build_dir.mkdir(exist_ok=True)

    console.print("[cyan]Configuring build with CMake...[/cyan]")
    result = subprocess.run(
        ["cmake", "..", "-DCMAKE_BUILD_TYPE=Release", "-DLLAMA_SERVER=ON"],
        cwd=build_dir,
        check=False,
    )
    if result.returncode != 0:
        console.print("[red]CMake configuration failed.[/red]")
        return False

    # Get CPU count for parallel build
    import multiprocessing

    cpu_count = multiprocessing.cpu_count()

    console.print(f"[cyan]Building llama.cpp (using {cpu_count} cores)...[/cyan]")
    console.print("[dim]This may take several minutes...[/dim]")
    result = subprocess.run(
        ["cmake", "--build", ".", "--config", "Release", "-j", str(cpu_count)],
        cwd=build_dir,
        check=False,
    )
    if result.returncode != 0:
        console.print("[red]Build failed.[/red]")
        return False

    # Install llama-server to /usr/local/bin
    llama_server_binary = build_dir / "bin" / "llama-server"
    if not llama_server_binary.exists():
        # Try alternative location
        llama_server_binary = build_dir / "llama-server"

    if not llama_server_binary.exists():
        console.print("[red]llama-server binary not found after build.[/red]")
        console.print("[dim]Looking for binary...[/dim]")
        # Search for it
        for f in build_dir.rglob("llama-server"):
            if f.is_file():
                llama_server_binary = f
                console.print(f"[green]Found: {f}[/green]")
                break

    if not llama_server_binary.exists():
        console.print("[red]Could not locate llama-server binary.[/red]")
        return False

    console.print("[cyan]Installing llama-server to /usr/local/bin...[/cyan]")
    result = subprocess.run(
        ["sudo", "cp", str(llama_server_binary), "/usr/local/bin/llama-server"],
        check=False,
    )
    if result.returncode != 0:
        console.print("[red]Failed to install llama-server.[/red]")
        return False

    result = subprocess.run(
        ["sudo", "chmod", "+x", "/usr/local/bin/llama-server"],
        check=False,
    )

    console.print("[green]✓ llama-server installed successfully![/green]")
    return True


def install_llama_cpp_prebuilt() -> bool:
    """
    Download and install pre-built llama.cpp binaries.

    Returns:
        bool: True if installation succeeded, False otherwise.
    """
    console.print("\n[bold cyan]Installing pre-built llama.cpp[/bold cyan]\n")

    arch = get_system_architecture()
    console.print(f"[cyan]Detected architecture: {arch}[/cyan]")

    # Determine the appropriate release URL
    # llama.cpp releases use format like: llama-<version>-bin-ubuntu-x64.zip
    if arch == "x86_64":
        arch_suffix = "x64"
    elif arch == "aarch64":
        arch_suffix = "arm64"
    else:
        console.print(f"[red]Unsupported architecture: {arch}[/red]")
        console.print("[yellow]Please build from source instead.[/yellow]")
        return False

    # Get latest release info from GitHub API
    console.print("[cyan]Fetching latest release information...[/cyan]")

    try:
        import json
        import urllib.request

        with urllib.request.urlopen(
            "https://api.github.com/repos/ggerganov/llama.cpp/releases/latest",
            timeout=30,
        ) as response:
            release_info = json.loads(response.read().decode())

        # Find the appropriate asset
        asset_url = None
        asset_name = None
        for asset in release_info.get("assets", []):
            name = asset["name"].lower()
            # Look for ubuntu/linux binary with matching architecture
            if (
                ("ubuntu" in name or "linux" in name)
                and arch_suffix in name
                and name.endswith(".zip")
            ):
                asset_url = asset["browser_download_url"]
                asset_name = asset["name"]
                break

        if not asset_url:
            console.print("[yellow]No pre-built binary found for your system.[/yellow]")
            console.print("[cyan]Falling back to building from source...[/cyan]")
            return install_llama_cpp_from_source()

        console.print(f"[cyan]Downloading: {asset_name}[/cyan]")

        # Download to temp directory
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / asset_name
            extract_dir = Path(tmpdir) / "extracted"
            extract_dir.mkdir()

            # Download
            result = subprocess.run(
                ["wget", "-q", "--show-progress", asset_url, "-O", str(zip_path)],
                check=False,
            )
            if result.returncode != 0:
                console.print("[red]Download failed.[/red]")
                return False

            # Extract
            console.print("[cyan]Extracting...[/cyan]")
            result = subprocess.run(
                ["unzip", "-q", str(zip_path), "-d", str(extract_dir)],
                check=False,
            )
            if result.returncode != 0:
                console.print("[red]Extraction failed. Is 'unzip' installed?[/red]")
                return False

            # Find llama-server binary
            llama_server_binary = None
            for f in extract_dir.rglob("llama-server"):
                if f.is_file():
                    llama_server_binary = f
                    break

            if not llama_server_binary:
                console.print("[red]llama-server not found in archive.[/red]")
                return False

            # Install
            console.print("[cyan]Installing llama-server to /usr/local/bin...[/cyan]")
            result = subprocess.run(
                ["sudo", "cp", str(llama_server_binary), "/usr/local/bin/llama-server"],
                check=False,
            )
            if result.returncode != 0:
                console.print("[red]Failed to install llama-server.[/red]")
                return False

            result = subprocess.run(
                ["sudo", "chmod", "+x", "/usr/local/bin/llama-server"],
                check=False,
            )

        console.print("[green]✓ llama-server installed successfully![/green]")
        return True

    except Exception as e:
        console.print(f"[red]Failed to fetch release info: {e}[/red]")
        console.print("[cyan]Falling back to building from source...[/cyan]")
        return install_llama_cpp_from_source()


def install_llama_cpp() -> bool:
    """
    Install llama.cpp (llama-server) with user choice of method.

    Returns:
        bool: True if installation succeeded, False otherwise.
    """
    console.print("\n[bold cyan]llama.cpp Installation[/bold cyan]\n")
    console.print("Choose installation method:\n")

    table = Table(title="Installation Options")
    table.add_column("Option", style="cyan", width=8)
    table.add_column("Method", style="green", width=20)
    table.add_column("Time", width=15)
    table.add_column("Description", width=40)

    table.add_row(
        "1",
        "Pre-built binary",
        "~1-2 minutes",
        "Download from GitHub releases (recommended)",
    )
    table.add_row(
        "2",
        "Build from source",
        "~5-15 minutes",
        "Clone and compile (more customizable)",
    )
    table.add_row(
        "3",
        "Skip",
        "-",
        "Install llama-server manually later",
    )

    console.print(table)
    console.print()

    choice = Prompt.ask(
        "Select installation method",
        choices=["1", "2", "3"],
        default="1",
    )

    if choice == "1":
        return install_llama_cpp_prebuilt()
    elif choice == "2":
        return install_llama_cpp_from_source()
    else:
        console.print("[yellow]Skipping llama-server installation.[/yellow]")
        console.print(
            "[dim]You'll need to install it manually before the LLM service can work.[/dim]"
        )
        return False


def install_llm_service(model_path: Path, threads: int = 4, ctx_size: int = 2048) -> bool:
    """
    Install and configure cortex-llm.service.

    Args:
        model_path: Path to the GGUF model file.
        threads: Number of CPU threads for inference.
        ctx_size: Context size in tokens.

    Returns:
        bool: True if installation succeeded, False otherwise.
    """
    console.print("\n[cyan]Installing cortex-llm service...[/cyan]")

    if not INSTALL_LLM_SCRIPT.exists():
        console.print(f"[red]Install script not found: {INSTALL_LLM_SCRIPT}[/red]")
        log_audit_event(
            "install_llm_service",
            f"Install script not found: {INSTALL_LLM_SCRIPT}",
            success=False,
        )
        return False

    result = subprocess.run(
        [
            "sudo",
            str(INSTALL_LLM_SCRIPT),
            "install",
            str(model_path),
            str(threads),
            str(ctx_size),
        ],
        check=False,
    )

    success = result.returncode == 0
    log_audit_event(
        "install_llm_service",
        f"Install LLM service {'succeeded' if success else 'failed'} (model: {model_path}, threads: {threads})",
        success=success,
    )
    return success


def setup_local_llm() -> Path | None:
    """
    Set up local llama.cpp with GGUF model.

    Downloads model and installs cortex-llm.service.

    Returns:
        Path | None: Path to the model file, or None if setup failed.
    """
    console.print("\n[bold cyan]Local llama.cpp Setup[/bold cyan]\n")

    # Check for llama-server
    llama_server_path = check_llama_server()
    if not llama_server_path:
        console.print("\n[yellow]llama-server is required for local LLM inference.[/yellow]")

        if Confirm.ask("Would you like to install llama.cpp now?", default=True):
            if not install_llama_cpp():
                console.print("\n[yellow]llama-server installation was skipped or failed.[/yellow]")
                if not Confirm.ask(
                    "Continue anyway (you can install llama-server later)?", default=False
                ):
                    return None
            else:
                # Verify installation
                llama_server_path = check_llama_server()
                if not llama_server_path:
                    console.print("[yellow]Warning: llama-server still not found in PATH.[/yellow]")
        else:
            console.print("\n[dim]Manual installation options:[/dim]")
            console.print(
                "[dim]  1. Build from source: https://github.com/ggerganov/llama.cpp[/dim]"
            )
            console.print("[dim]  2. Package manager (if available)[/dim]")

            if not Confirm.ask(
                "\nContinue anyway (you can install llama-server later)?", default=False
            ):
                return None

    # Download or select model
    model_path = download_model()
    if not model_path:
        return None

    # Configure threads
    import multiprocessing

    cpu_count = multiprocessing.cpu_count()
    default_threads = min(4, cpu_count)

    console.print(f"\n[cyan]CPU cores available: {cpu_count}[/cyan]")
    threads_str = Prompt.ask(
        "Number of threads for inference",
        default=str(default_threads),
    )
    threads = int(threads_str) if threads_str.isdigit() else default_threads

    # Install cortex-llm service
    if not install_llm_service(model_path, threads):
        console.print("[red]Failed to install cortex-llm service.[/red]")
        console.print("[yellow]You can install it manually later:[/yellow]")
        console.print(f"[dim]  sudo {INSTALL_LLM_SCRIPT} install {model_path} {threads}[/dim]")
        return model_path  # Still return model path for config

    # Save provider config
    cortex_dir = Path.home() / ".cortex"
    cortex_dir.mkdir(parents=True, exist_ok=True)
    env_file = cortex_dir / ".env"

    # Update .env file
    existing_lines = []
    if env_file.exists():
        with open(env_file) as f:
            existing_lines = f.readlines()

    new_lines = [
        line
        for line in existing_lines
        if not line.startswith("CORTEX_PROVIDER=") and not line.startswith("LLAMA_CPP_BASE_URL=")
    ]
    new_lines.append("CORTEX_PROVIDER=llama_cpp\n")
    new_lines.append("LLAMA_CPP_BASE_URL=http://127.0.0.1:8085\n")

    with open(env_file, "w") as f:
        f.writelines(new_lines)

    console.print("[green]✓ Provider set to: llama_cpp[/green]")
    console.print("[green]✓ LLM service URL: http://127.0.0.1:8085[/green]")

    return model_path


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
    success = result.returncode == 0
    log_audit_event(
        "build_daemon",
        f"Build daemon {'succeeded' if success else 'failed'}",
        success=success,
    )
    return success


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
    success = result.returncode == 0
    log_audit_event(
        "install_daemon",
        f"Install daemon {'succeeded' if success else 'failed'}",
        success=success,
    )
    return success


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
    model_dir = MODEL_DIR.expanduser().resolve()
    model_path = (model_dir / safe_filename).resolve()
    if not model_path.is_relative_to(model_dir):
        console.print("[red]Security error: model path escapes designated directory.[/red]")
        return None

    console.print(f"[cyan]Downloading to {model_path}...[/cyan]")
    # Use subprocess with list arguments (no shell) after URL validation
    result = subprocess.run(["wget", model_url, "-O", str(model_path)], check=False)
    success = result.returncode == 0
    if success:
        log_audit_event(
            "download_model",
            f"Downloaded model to {model_path}",
            success=True,
        )
        return model_path
    else:
        log_audit_event(
            "download_model",
            f"Failed to download model from {model_url}",
            success=False,
        )
        return None


def configure_auto_load(model_path: Path | str) -> None:
    """
    Configure the cortex daemon to auto-load the specified model on startup.

    Updates the daemon configuration file (/etc/cortex/daemon.yaml) to set the
    model_path and disable lazy_load, then restarts the daemon service.

    Args:
        model_path: Path (or string path) to the GGUF model file to configure
                    for auto-loading. Accepts either a Path object or a string.

    Returns:
        None. Exits the program with code 1 on failure.
    """
    console.print("[cyan]Configuring auto-load for the model...[/cyan]")

    try:
        # Create /etc/cortex directory if it doesn't exist
        mkdir_result = subprocess.run(
            ["sudo", "mkdir", "-p", "/etc/cortex"],
            capture_output=True,
            text=True,
            check=False,
        )
        if mkdir_result.returncode != 0:
            console.print(
                f"[red]Failed to create /etc/cortex directory: {mkdir_result.stderr}[/red]"
            )
            sys.exit(1)

        # Check if config already exists
        config_exists = Path(CONFIG_FILE).exists()

        if not config_exists:
            # Copy example config and modify it
            console.print("[cyan]Creating daemon configuration file...[/cyan]")
            cp_result = subprocess.run(
                ["sudo", "cp", str(CONFIG_EXAMPLE), CONFIG_FILE],
                capture_output=True,
                text=True,
                check=False,
            )
            if cp_result.returncode != 0:
                console.print(
                    f"[red]Failed to copy {CONFIG_EXAMPLE} to {CONFIG_FILE}: {cp_result.stderr}[/red]"
                )
                sys.exit(1)

        # Use YAML library to safely update the configuration instead of sed
        # This avoids shell injection risks from special characters in model_path
        # Read the current config file
        result = subprocess.run(
            ["sudo", "cat", CONFIG_FILE], capture_output=True, text=True, check=True
        )
        config = yaml.safe_load(result.stdout) or {}

        # Ensure the llm section exists
        if "llm" not in config:
            config["llm"] = {}

        # Update the configuration values under the llm section
        # The daemon reads from llm.model_path and llm.lazy_load
        config["llm"]["model_path"] = str(model_path)
        config["llm"]["lazy_load"] = False

        # Write the updated config atomically using a temp file
        updated_yaml = yaml.dump(config, default_flow_style=False, sort_keys=False)

        # Create a temp file with the updated config
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            tmp.write(updated_yaml)
            tmp_path = tmp.name

        # Move the temp file to the config location atomically with sudo
        mv_result = subprocess.run(
            ["sudo", "mv", tmp_path, CONFIG_FILE],
            capture_output=True,
            text=True,
            check=False,
        )
        if mv_result.returncode != 0:
            # Clean up temp file if move failed
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            console.print(
                f"[red]Failed to write config file {CONFIG_FILE}: {mv_result.stderr}[/red]"
            )
            sys.exit(1)

        console.print(
            f"[green]Model configured to auto-load on daemon startup: {model_path}[/green]"
        )
        console.print("[cyan]Restarting daemon to apply configuration...[/cyan]")

        restart_result = subprocess.run(
            ["sudo", "systemctl", "restart", "cortexd"],
            capture_output=True,
            text=True,
            check=False,
        )
        if restart_result.returncode != 0:
            console.print(f"[red]Failed to restart cortexd service: {restart_result.stderr}[/red]")
            sys.exit(1)

        console.print("[green]Daemon restarted with model loaded![/green]")

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Failed to read config file {CONFIG_FILE}: {e}[/red]")
        sys.exit(1)
    except yaml.YAMLError as e:
        console.print(f"[red]Failed to parse config file {CONFIG_FILE}: {e}[/red]")
        sys.exit(1)


def configure_daemon_llm_backend(backend: str, config: dict | None = None) -> None:
    """
    Update daemon configuration with the chosen LLM backend.

    Args:
        backend: "cloud", "local", or "none"
        config: Optional configuration dict (provider info for cloud, model path for local)
    """
    console.print("[cyan]Updating daemon configuration...[/cyan]")

    # Create /etc/cortex directory if it doesn't exist
    subprocess.run(["sudo", "mkdir", "-p", "/etc/cortex"], check=False)

    # Check if config already exists
    config_exists = Path(CONFIG_FILE).exists()

    if not config_exists:
        console.print("[cyan]Creating daemon configuration file...[/cyan]")
        subprocess.run(["sudo", "cp", str(CONFIG_EXAMPLE), CONFIG_FILE], check=False)

    try:
        # Read the current config file
        result = subprocess.run(
            ["sudo", "cat", CONFIG_FILE], capture_output=True, text=True, check=True
        )
        daemon_config = yaml.safe_load(result.stdout) or {}

        # Ensure the llm section exists
        if "llm" not in daemon_config:
            daemon_config["llm"] = {}

        # Update the backend
        daemon_config["llm"]["backend"] = backend

        if backend == "cloud" and config:
            if "cloud" not in daemon_config["llm"]:
                daemon_config["llm"]["cloud"] = {}
            daemon_config["llm"]["cloud"]["provider"] = config.get("provider", "claude")
            daemon_config["llm"]["cloud"]["api_key_env"] = config.get(
                "env_var", "ANTHROPIC_API_KEY"
            )

        elif backend == "local":
            if "local" not in daemon_config["llm"]:
                daemon_config["llm"]["local"] = {}
            daemon_config["llm"]["local"]["base_url"] = "http://127.0.0.1:8085"
            if config and "model_name" in config:
                daemon_config["llm"]["local"]["model_name"] = config["model_name"]

        # Clear legacy embedded model settings when using new backend
        if backend in ("cloud", "local"):
            daemon_config["llm"]["model_path"] = ""
            daemon_config["llm"]["lazy_load"] = True

        # Write the updated config back via sudo tee
        updated_yaml = yaml.dump(daemon_config, default_flow_style=False, sort_keys=False)
        write_result = subprocess.run(
            ["sudo", "tee", CONFIG_FILE],
            input=updated_yaml,
            text=True,
            capture_output=True,
            check=False,
        )

        if write_result.returncode != 0:
            console.print("[red]Failed to write config file[/red]")
            log_audit_event(
                "configure_daemon_llm_backend",
                f"Failed to write config file for backend: {backend}",
                success=False,
            )
            return

        console.print(f"[green]✓ Daemon configured with LLM backend: {backend}[/green]")
        log_audit_event(
            "configure_daemon_llm_backend",
            f"Configured daemon with LLM backend: {backend}",
            success=True,
        )

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Failed to read config file: {e}[/red]")
        log_audit_event(
            "configure_daemon_llm_backend",
            f"Failed to read config file: {e}",
            success=False,
        )
    except yaml.YAMLError as e:
        console.print(f"[red]Failed to parse config file: {e}[/red]")
        log_audit_event(
            "configure_daemon_llm_backend",
            f"Failed to parse config file: {e}",
            success=False,
        )


def main() -> int:
    """
    Interactive setup wizard for the Cortex daemon.

    Guides the user through building, installing, and configuring the cortexd daemon,
    including LLM backend setup (Cloud APIs or Local llama.cpp).

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

    # Initialize audit database
    init_audit_db()
    log_audit_event("setup_started", "Cortex daemon interactive setup started")

    # Step 0: Check and install system dependencies
    if not setup_system_dependencies():
        console.print("[red]Cannot proceed without required system dependencies.[/red]")
        sys.exit(1)

    # Step 1: Build daemon
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

    # Step 2: Install daemon
    if not install_daemon():
        console.print("[red]Failed to install the daemon.[/red]")
        sys.exit(1)

    # Step 3: Choose LLM backend
    console.print("")
    if not Confirm.ask("Do you want to configure an LLM backend now?", default=True):
        console.print("\n[green]✓ Daemon installed successfully![/green]")
        console.print("[cyan]You can configure LLM later by running this setup again.[/cyan]\n")
        return 0

    backend = choose_llm_backend()
    log_audit_event("choose_llm_backend", f"User selected LLM backend: {backend}")

    if backend == "none":
        console.print("\n[green]✓ Daemon installed successfully![/green]")
        console.print("[cyan]LLM backend not configured. You can set it up later.[/cyan]\n")
        log_audit_event("setup_completed", "Setup completed without LLM backend")
        return 0

    elif backend == "cloud":
        # Setup cloud API
        cloud_config = setup_cloud_api()
        if cloud_config:
            log_audit_event(
                "setup_cloud_api",
                f"Cloud API setup completed for provider: {cloud_config.get('provider', 'unknown')}",
            )
            save_cloud_api_config(cloud_config)
            configure_daemon_llm_backend("cloud", cloud_config)

        console.print(
            "\n[bold green]╔══════════════════════════════════════════════════════════════╗[/bold green]"
        )
        console.print(
            "[bold green]║              Setup Completed Successfully!                   ║[/bold green]"
        )
        console.print(
            "[bold green]╚══════════════════════════════════════════════════════════════╝[/bold green]"
        )
        console.print(f"\n[cyan]LLM Backend: Cloud API ({cloud_config['provider']})[/cyan]")
        console.print("[cyan]Try it out:[/cyan] cortex ask 'What packages do I have installed?'\n")
        return 0
    elif backend == "local":
        # Setup local llama.cpp
        model_path = setup_local_llm()
        if model_path:
            # Get model name from path for config
            model_name = model_path.stem if hasattr(model_path, "stem") else str(model_path)
            configure_daemon_llm_backend("local", {"model_name": model_name})

            console.print(
                "\n[bold green]╔══════════════════════════════════════════════════════════════╗[/bold green]"
            )
            console.print(
                "[bold green]║              Setup Completed Successfully!                   ║[/bold green]"
            )
            console.print(
                "[bold green]╚══════════════════════════════════════════════════════════════╝[/bold green]"
            )
            console.print("\n[cyan]LLM Backend: Local llama.cpp[/cyan]")
            console.print(f"[cyan]Model: {model_path}[/cyan]")
            console.print("[cyan]Service: cortex-llm.service[/cyan]")
            console.print("\n[dim]Useful commands:[/dim]")
            console.print("[dim]  sudo systemctl status cortex-llm   # Check LLM service[/dim]")
            console.print("[dim]  journalctl -u cortex-llm -f        # View LLM logs[/dim]")
            console.print(
                "\n[cyan]Try it out:[/cyan] cortex ask 'What packages do I have installed?'\n"
            )
            return 0
        else:
            console.print("[red]Failed to set up local LLM.[/red]")
            console.print("[yellow]Daemon is installed but LLM is not configured.[/yellow]")
        sys.exit(1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
