import sys
import os
import argparse
import time
import json
from typing import Any, Dict, List, Optional
import logging
from typing import List, Optional
import subprocess
from datetime import datetime
from pathlib import Path

# Suppress noisy log messages in normal operation
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("cortex.installation_history").setLevel(logging.ERROR)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from LLM.interpreter import CommandInterpreter
from cortex.coordinator import InstallationCoordinator, StepStatus
from cortex.installation_history import (
    InstallationHistory,
    InstallationType,
    InstallationStatus
)
from cortex.user_preferences import (
    PreferencesManager,
    print_all_preferences,
    format_preference_value
)
from cortex.branding import (
    console,
    cx_print,
    cx_step,
    cx_header,
    show_banner,
    VERSION
)
from cortex.validators import (
    validate_api_key,
    validate_install_request,
    validate_installation_id,
    ValidationError
)


class CortexCLI:
    def __init__(self, verbose: bool = False):
        self.spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.spinner_idx = 0
        self.prefs_manager = None  # Lazy initialization
        self.verbose = verbose

    def _debug(self, message: str):
        """Print debug info only in verbose mode"""
        if self.verbose:
            console.print(f"[dim][DEBUG] {message}[/dim]")

    def _get_api_key(self) -> Optional[str]:
        # Check if using Ollama (no API key needed)
        provider = self._get_provider()
        if provider == 'ollama':
            self._debug("Using Ollama (no API key required)")
            return "ollama-local"  # Placeholder for Ollama

        is_valid, detected_provider, error = validate_api_key()
        if not is_valid:
            self._print_error(error)
            cx_print("Run [bold]cortex wizard[/bold] to configure your API key.", "info")
            cx_print("Or use [bold]CORTEX_PROVIDER=ollama[/bold] for offline mode.", "info")
            return None
        api_key = os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('OPENAI_API_KEY')
        return api_key

    def _get_provider(self) -> str:
        # Check environment variable for explicit provider choice
        explicit_provider = os.environ.get('CORTEX_PROVIDER', '').lower()
        if explicit_provider in ['ollama', 'openai', 'claude']:
            return explicit_provider

        # Auto-detect based on available API keys
        if os.environ.get('ANTHROPIC_API_KEY'):
            return 'claude'
        elif os.environ.get('OPENAI_API_KEY'):
            return 'openai'

        # Fallback to Ollama for offline mode
        return 'ollama'

    def _print_status(self, emoji: str, message: str):
        """Legacy status print - maps to cx_print for Rich output"""
        status_map = {
            "🧠": "thinking",
            "📦": "info",
            "⚙️": "info",
            "🔍": "info",
        }
        status = status_map.get(emoji, "info")
        cx_print(message, status)

    def _print_error(self, message: str):
        cx_print(f"Error: {message}", "error")

    def _print_success(self, message: str):
        cx_print(message, "success")

    def _animate_spinner(self, message: str):
        sys.stdout.write(f"\r{self.spinner_chars[self.spinner_idx]} {message}")
        sys.stdout.flush()
        self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner_chars)
        time.sleep(0.1)

    def _clear_line(self):
        sys.stdout.write('\r\033[K')
        sys.stdout.flush()
    
    def _resolve_conflicts_interactive(self, conflicts: List[tuple]) -> Dict[str, List[str]]:
        """
        Interactively resolve package conflicts with user input.
        
        Args:
            conflicts: List of tuples (package1, package2) representing conflicts
            
        Returns:
            Dictionary with resolution actions (e.g., {'remove': ['pkgA']})
        """
        resolutions = {'remove': []}
        saved_resolutions = self.prefs_manager.get("conflicts.saved_resolutions") or {}
        
        print("\n" + "=" * 60)
        print("Package Conflicts Detected")
        print("=" * 60)
        
        for i, (pkg1, pkg2) in enumerate(conflicts, 1):
            conflict_key = f"{min(pkg1, pkg2)}:{max(pkg1, pkg2)}"
            if conflict_key in saved_resolutions:
                preferred = saved_resolutions[conflict_key]
                to_remove = pkg2 if preferred == pkg1 else pkg1
                resolutions['remove'].append(to_remove)
                print(f"\nConflict {i}: {pkg1} vs {pkg2}")
                print(f"  Using saved preference: Keep {preferred}, remove {to_remove}")
                continue

            print(f"\nConflict {i}: {pkg1} vs {pkg2}")
            print(f"  1. Keep/Install {pkg1} (removes {pkg2})")
            print(f"  2. Keep/Install {pkg2} (removes {pkg1})")
            print("  3. Cancel installation")
            
            while True:
                choice = input(f"\nSelect action for Conflict {i} [1-3]: ").strip()
                if choice == '1':
                    resolutions['remove'].append(pkg2)
                    print(f"Selected: Keep {pkg1}, remove {pkg2}")
                    self._ask_save_preference(pkg1, pkg2, pkg1)
                    break
                elif choice == '2':
                    resolutions['remove'].append(pkg1)
                    print(f"Selected: Keep {pkg2}, remove {pkg1}")
                    self._ask_save_preference(pkg1, pkg2, pkg2)
                    break
                elif choice == '3':
                    print("Installation cancelled.")
                    sys.exit(1)
                else:
                    print("Invalid choice. Please enter 1, 2, or 3.")
        
        return resolutions

    def _ask_save_preference(self, pkg1: str, pkg2: str, preferred: str):
        """
        Ask user if they want to save the conflict resolution preference.
        
        Args:
            pkg1: First package in conflict
            pkg2: Second package in conflict
            preferred: The package user chose to keep
        """
        save = input("Save this preference for future conflicts? (y/N): ").strip().lower()
        if save == 'y':
            conflict_key = f"{min(pkg1, pkg2)}:{max(pkg1, pkg2)}"
            saved_resolutions = self.prefs_manager.get("conflicts.saved_resolutions") or {}
            saved_resolutions[conflict_key] = preferred
            self.prefs_manager.set("conflicts.saved_resolutions", saved_resolutions)
            self.prefs_manager.save()
            print("Preference saved.")
    
    def install(self, software: str, execute: bool = False, dry_run: bool = False):
        # Validate input first
        is_valid, error = validate_install_request(software)
        if not is_valid:
            self._print_error(error)
            return 1

        api_key = self._get_api_key()
        if not api_key:
            return 1

        provider = self._get_provider()
        self._debug(f"Using provider: {provider}")
        self._debug(f"API key: {api_key[:10]}...{api_key[-4:]}")
        
        # Initialize installation history
        history = InstallationHistory()
        install_id = None
        start_time = datetime.now()
        
        try:
            self._print_status("[INFO]", "Understanding request...")
            
            interpreter = CommandInterpreter(api_key=api_key, provider=provider)
            
            self._print_status("[INFO]", "Planning installation...")
            
            for _ in range(10):
                self._animate_spinner("Analyzing system requirements...")
            self._clear_line()
            
            commands = interpreter.parse(f"install {software}")
            
            if not commands:
                self._print_error("No commands generated. Please try again with a different request.")
                return 1

            # Check for package conflicts using DependencyResolver
            from dependency_resolver import DependencyResolver
            resolver = DependencyResolver()
            
            target_package = software.split()[0]
            
            try:
                graph = resolver.resolve_dependencies(target_package)
                if graph.conflicts:
                    resolutions = self._resolve_conflicts_interactive(graph.conflicts)
                    
                    if resolutions['remove']:
                        for pkg_to_remove in resolutions['remove']:
                            if not any(f"remove {pkg_to_remove}" in cmd for cmd in commands):
                                commands.insert(0, f"sudo apt-get remove -y {pkg_to_remove}")
                                self._print_status("[INFO]", f"Added command to remove conflicting package: {pkg_to_remove}")
            except Exception:
                pass
            
            # Extract packages from commands for tracking
            packages = history._extract_packages_from_commands(commands)
            
            # Record installation start
            if execute or dry_run:
                install_id = history.record_installation(
                    InstallationType.INSTALL,
                    packages,
                    commands,
                    start_time
                )
            
            self._print_status("[INFO]", f"Installing {software}...")
            print("\nGenerated commands:")
            for i, cmd in enumerate(commands, 1):
                print(f"  {i}. {cmd}")
            
            if dry_run:
                print("\n(Dry run mode - commands not executed)")
                if install_id:
                    history.update_installation(install_id, InstallationStatus.SUCCESS)
                return 0
            
            if execute:
                def progress_callback(current, total, step):
                    status_label = "[PENDING]"
                    if step.status == StepStatus.SUCCESS:
                        status_label = "[SUCCESS]"
                    elif step.status == StepStatus.FAILED:
                        status_label = "[FAILED]"
                    print(f"\n[{current}/{total}] {status_label} {step.description}")
                    print(f"  Command: {step.command}")
                
                print("\nExecuting commands...")
                
                coordinator = InstallationCoordinator(
                    commands=commands,
                    descriptions=[f"Step {i+1}" for i in range(len(commands))],
                    timeout=300,
                    stop_on_error=True,
                    progress_callback=progress_callback
                )
                
                result = coordinator.execute()
                
                if result.success:
                    self._print_success(f"{software} installed successfully!")
                    print(f"\nCompleted in {result.total_duration:.2f} seconds")
                    
                    # Record successful installation
                    if install_id:
                        history.update_installation(install_id, InstallationStatus.SUCCESS)
                        print(f"\n[INFO] Installation recorded (ID: {install_id})")
                        print(f"   To rollback: cortex rollback {install_id}")
                    
                    return 0
                else:
                    # Record failed installation
                    if install_id:
                        error_msg = result.error_message or "Installation failed"
                        history.update_installation(
                            install_id,
                            InstallationStatus.FAILED,
                            error_msg
                        )
                    
                    if result.failed_step is not None:
                        self._print_error(f"Installation failed at step {result.failed_step + 1}")
                    else:
                        self._print_error("Installation failed")
                    if result.error_message:
                        print(f"  Error: {result.error_message}", file=sys.stderr)
                    if install_id:
                        print(f"\n[INFO] Installation recorded (ID: {install_id})")
                        print(f"   View details: cortex history show {install_id}")
                    return 1
            else:
                print("\nTo execute these commands, run with --execute flag")
                print("Example: cortex install docker --execute")
            
            return 0
            
        except ValueError as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            self._print_error(str(e))
            return 1
        except RuntimeError as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            self._print_error(f"API call failed: {str(e)}")
            return 1
        except Exception as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            self._print_error(f"Unexpected error: {str(e)}")
            return 1

    def history(self, limit: int = 20, status: Optional[str] = None, show_id: Optional[str] = None):
        """Show installation history"""
        history = InstallationHistory()
        
        try:
            if show_id:
                # Show specific installation
                record = history.get_installation(show_id)
                
                if not record:
                    self._print_error(f"Installation {show_id} not found")
                    return 1
                
                print(f"\nInstallation Details: {record.id}")
                print("=" * 60)
                print(f"Timestamp: {record.timestamp}")
                print(f"Operation: {record.operation_type.value}")
                print(f"Status: {record.status.value}")
                if record.duration_seconds:
                    print(f"Duration: {record.duration_seconds:.2f}s")
                else:
                    print("Duration: N/A")
                print(f"\nPackages: {', '.join(record.packages)}")
                
                if record.error_message:
                    print(f"\nError: {record.error_message}")
                
                if record.commands_executed:
                    print(f"\nCommands executed:")
                    for cmd in record.commands_executed:
                        print(f"  {cmd}")
                
                print(f"\nRollback available: {record.rollback_available}")
                return 0
            else:
                # List history
                status_filter = InstallationStatus(status) if status else None
                records = history.get_history(limit, status_filter)
                
                if not records:
                    print("No installation records found.")
                    return 0
                
                print(f"\n{'ID':<18} {'Date':<20} {'Operation':<12} {'Packages':<30} {'Status':<15}")
                print("=" * 100)
                
                for r in records:
                    date = r.timestamp[:19].replace('T', ' ')
                    packages = ', '.join(r.packages[:2])
                    if len(r.packages) > 2:
                        packages += f" +{len(r.packages)-2}"
                    
                    print(f"{r.id:<18} {date:<20} {r.operation_type.value:<12} {packages:<30} {r.status.value:<15}")
                
                return 0
        except Exception as e:
            self._print_error(f"Failed to retrieve history: {str(e)}")
            return 1

    def rollback(self, install_id: str, dry_run: bool = False):
        """Rollback an installation"""
        history = InstallationHistory()
        
        try:
            success, message = history.rollback(install_id, dry_run)
            
            if dry_run:
                print("\nRollback actions (dry run):")
                print(message)
                return 0
            elif success:
                self._print_success(message)
                return 0
            else:
                self._print_error(message)
                return 1
        except Exception as e:
            self._print_error(f"Rollback failed: {str(e)}")
            return 1

    def config(self, action: str, key: Optional[str] = None, value: Optional[str] = None):
        """
        Manage user preferences and configuration.
        
        Args:
            action: Configuration action (list, get, set, reset, validate, info, export, import)
            key: Preference key or file path
            value: Preference value (for set action)
            
        Returns:
            Exit code (0 for success, 1 for error)
        """
        try:
            if action == "list":
                prefs = self.prefs_manager.list_all()
                
                print("\n[INFO] Current Configuration:")
                print("=" * 60)
                import yaml
                print(yaml.dump(prefs, default_flow_style=False, sort_keys=False))
                
                info = self.prefs_manager.get_config_info()
                print(f"\nConfig file: {info['config_path']}")
                return 0
            
            elif action == "get":
                if not key:
                    self._print_error("Key required for 'get' action")
                    return 1
                
                value = self.prefs_manager.get(key)
                if value is None:
                    self._print_error(f"Preference '{key}' not found")
                    return 1
                
                print(f"{key}: {value}")
                return 0
            
            elif action == "set":
                if not key or value is None:
                    self._print_error("Key and value required for 'set' action")
                    return 1
                
                parsed_value = self._parse_config_value(value)
                
                self.prefs_manager.set(key, parsed_value)
                self.prefs_manager.save()
                
                self._print_success(f"Set {key} = {parsed_value}")
                return 0
            
            elif action == "reset":
                if key:
                    self.prefs_manager.reset(key)
                    self._print_success(f"Reset {key} to default")
                else:
                    print("This will reset all preferences to defaults.")
                    confirm = input("Continue? (y/n): ")
                    if confirm.lower() == 'y':
                        self.prefs_manager.reset()
                        self._print_success("All preferences reset to defaults")
                    else:
                        print("Reset cancelled")
                return 0
            
            elif action == "validate":
                errors = self.prefs_manager.validate()
                if errors:
                    print("Configuration validation errors:")
                    for error in errors:
                        print(f"  - {error}")
                    return 1
                else:
                    self._print_success("Configuration is valid")
                    return 0
            
            elif action == "info":
                info = self.prefs_manager.get_config_info()
                print("\n[INFO] Configuration Info:")
                print("=" * 60)
                for k, v in info.items():
                    print(f"{k}: {v}")
                return 0
            
            elif action == "export":
                if not key:
                    self._print_error("Output path required for 'export' action")
                    return 1
                
                output_path = Path(key)
                self.prefs_manager.export_json(output_path)
                self._print_success(f"Configuration exported to {output_path}")
                return 0
            
            elif action == "import":
                if not key:
                    self._print_error("Input path required for 'import' action")
                    return 1
                
                input_path = Path(key)
                self.prefs_manager.import_json(input_path)
                self._print_success(f"Configuration imported from {input_path}")
                return 0
            
            else:
                self._print_error(f"Unknown config action: {action}")
                return 1
        
        except ValueError as e:
            self._print_error(str(e))
            return 1
        except Exception as e:
            self._print_error(f"Configuration error: {str(e)}")
            return 1
    
    def _parse_config_value(self, value: str) -> Any:
        """
        Parse configuration value from string.
        
        Args:
            value: String value to parse
            
        Returns:
            Parsed value (bool, int, list, or string)
        """
        if value.lower() in ('true', 'yes', 'on', '1'):
            return True
        if value.lower() in ('false', 'no', 'off', '0'):
            return False
        
        try:
            return int(value)
        except ValueError:
            pass
        
        if ',' in value:
            return [item.strip() for item in value.split(',')]
        
        return value

    def status(self):
        """Show system status including security features"""
        import shutil

        show_banner(show_version=True)
        console.print()

        cx_header("System Status")

        # Check API key
        is_valid, provider, _ = validate_api_key()
        if is_valid:
            cx_print(f"API Provider: [bold]{provider}[/bold]", "success")
        else:
            # Check for Ollama
            ollama_provider = os.environ.get('CORTEX_PROVIDER', '').lower()
            if ollama_provider == 'ollama':
                cx_print("API Provider: [bold]Ollama (local)[/bold]", "success")
            else:
                cx_print("API Provider: [bold]Not configured[/bold]", "warning")
                cx_print("  Run: cortex wizard", "info")

        # Check Firejail
        firejail_path = shutil.which('firejail')
        if firejail_path:
            cx_print(f"Firejail: [bold]Available[/bold] ({firejail_path})", "success")
        else:
            cx_print("Firejail: [bold]Not installed[/bold]", "warning")
            cx_print("  Install: sudo apt-get install firejail", "info")

        # Check Ollama
        ollama_host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
        try:
            import urllib.request
            req = urllib.request.Request(f"{ollama_host}/api/tags", method='GET')
            with urllib.request.urlopen(req, timeout=2) as resp:
                cx_print(f"Ollama: [bold]Running[/bold] ({ollama_host})", "success")
        except Exception:
            cx_print(f"Ollama: [bold]Not running[/bold]", "info")
            cx_print("  Start: ollama serve", "info")

        console.print()
        cx_header("Configuration")

        # Show config file location
        config_path = os.path.expanduser('~/.cortex/config.json')
        if os.path.exists(config_path):
            cx_print(f"Config: {config_path}", "info")
        else:
            cx_print(f"Config: Not created yet", "info")

        history_path = os.path.expanduser('~/.cortex/history.db')
        if os.path.exists(history_path):
            cx_print(f"History: {history_path}", "info")
        else:
            cx_print(f"History: Not created yet", "info")

        console.print()
        return 0

    def wizard(self):
        """Interactive setup wizard for API key configuration"""
        from pathlib import Path

        show_banner()
        console.print()
        cx_print("Welcome to Cortex Setup Wizard!", "success")
        console.print()

        # Check current API key status
        is_valid, provider, _ = validate_api_key()
        if is_valid:
            cx_print(f"API key already configured ({provider})", "success")
            console.print()
            response = input("Do you want to reconfigure? (y/N): ").strip().lower()
            if response != 'y':
                cx_print("Configuration unchanged.", "info")
                return 0

        console.print("[bold]Choose your AI provider:[/bold]")
        console.print("  1. Anthropic Claude [green](recommended)[/green]")
        console.print("  2. OpenAI GPT-4")
        console.print()

        choice = input("Enter choice (1 or 2): ").strip()

        if choice == '1':
            provider_name = 'ANTHROPIC_API_KEY'
            console.print()
            console.print("[dim]Get your key at: https://console.anthropic.com[/dim]")
        elif choice == '2':
            provider_name = 'OPENAI_API_KEY'
            console.print()
            console.print("[dim]Get your key at: https://platform.openai.com/api-keys[/dim]")
        else:
            self._print_error("Invalid choice. Please enter 1 or 2.")
            return 1

        console.print()
        api_key = input(f"Enter your {provider_name}: ").strip()

        if not api_key:
            self._print_error("API key cannot be empty.")
            return 1

        # Validate key format
        if provider_name == 'ANTHROPIC_API_KEY' and not api_key.startswith('sk-ant-'):
            cx_print("Warning: Key doesn't look like an Anthropic key (should start with 'sk-ant-')", "warning")
        elif provider_name == 'OPENAI_API_KEY' and not api_key.startswith('sk-'):
            cx_print("Warning: Key doesn't look like an OpenAI key (should start with 'sk-')", "warning")

        # Save to shell profile
        console.print()
        console.print("[bold]Where should I save this?[/bold]")
        console.print("  1. ~/.bashrc")
        console.print("  2. ~/.zshrc")
        console.print("  3. ~/.profile")
        console.print("  4. Just show me the export command")
        console.print()

        save_choice = input("Enter choice (1-4): ").strip()

        export_line = f'export {provider_name}="{api_key}"'

        if save_choice in ['1', '2', '3']:
            files = {
                '1': Path.home() / '.bashrc',
                '2': Path.home() / '.zshrc',
                '3': Path.home() / '.profile',
            }
            target_file = files[save_choice]

            try:
                with open(target_file, 'a') as f:
                    f.write(f'\n# Cortex Linux API key\n{export_line}\n')
                cx_print(f"Added to {target_file}", "success")
                console.print()
                console.print(f"[yellow]Run this to activate now:[/yellow]")
                console.print(f"  source {target_file}")
            except Exception as e:
                self._print_error(f"Could not write to {target_file}: {e}")
                console.print()
                console.print("[yellow]Add this line manually:[/yellow]")
                console.print(f"  {export_line}")
        else:
            console.print()
            console.print("[yellow]Add this to your shell profile:[/yellow]")
            console.print(f"  {export_line}")

        console.print()
        cx_print("Setup complete! Try: cortex install docker", "success")
        return 0

    def demo(self):
        """Run a demo showing Cortex capabilities without API key"""
        import time

        show_banner()
        console.print()

        # Simulated installation flow
        cx_print("Understanding request: [bold]install docker[/bold]", "thinking")
        time.sleep(0.5)

        cx_print("Planning installation...", "info")
        time.sleep(0.3)

        cx_header("Installation Plan")

        cx_print("[bold]docker.io[/bold] (24.0.5) — Container runtime", "info")
        cx_print("[bold]docker-compose[/bold] (2.20.2) — Multi-container orchestration", "info")
        cx_print("[bold]docker-buildx[/bold] (0.11.2) — Extended build capabilities", "info")

        console.print()
        console.print("[dim]Generated commands:[/dim]")
        console.print("  1. sudo apt update")
        console.print("  2. sudo apt install -y docker.io")
        console.print("  3. sudo systemctl enable docker")
        console.print("  4. sudo systemctl start docker")

        console.print()
        cx_step(1, 4, "Updating package lists...")
        time.sleep(0.3)
        cx_step(2, 4, "Installing docker.io...")
        time.sleep(0.3)
        cx_step(3, 4, "Enabling docker service...")
        time.sleep(0.3)
        cx_step(4, 4, "Starting docker service...")
        time.sleep(0.3)

        console.print()
        cx_print("Installation complete!", "success")
        cx_print("Docker is ready to use.", "info")

        console.print()
        console.print("[dim]━━━ This was a demo. No packages were installed. ━━━[/dim]")
        console.print()
        cx_print("To get started for real:", "info")
        console.print("  1. Set your API key: [bold]export ANTHROPIC_API_KEY='your-key'[/bold]")
        console.print("  2. Install something: [bold]cortex install docker --execute[/bold]")
        console.print()

        return 0


def show_rich_help():
    """Display beautifully formatted help using Rich"""
    from rich.table import Table

    show_banner(show_version=True)
    console.print()

    console.print("[bold]AI-powered package manager for Linux[/bold]")
    console.print("[dim]Just tell Cortex what you want to install.[/dim]")
    console.print()

    # Commands table
    table = Table(show_header=True, header_style="bold cyan", box=None)
    table.add_column("Command", style="green")
    table.add_column("Description")

    table.add_row("demo", "See Cortex in action (no API key needed)")
    table.add_row("wizard", "Configure API key interactively")
    table.add_row("status", "Show system status and security features")
    table.add_row("install <pkg>", "Install software using natural language")
    table.add_row("history", "View installation history")
    table.add_row("rollback <id>", "Undo an installation")

    console.print(table)
    console.print()

    # Quick start
    console.print("[bold cyan]Quick Start:[/bold cyan]")
    console.print("  1. [dim]Set API key:[/dim]  export ANTHROPIC_API_KEY='sk-ant-...'")
    console.print("  2. [dim]Install:[/dim]      cortex install docker --execute")
    console.print()

    # Flags
    console.print("[bold cyan]Flags:[/bold cyan]")
    console.print("  --execute    Actually run the commands (default: preview only)")
    console.print("  --dry-run    Show what would happen without doing anything")
    console.print("  --verbose    Show debug information")
    console.print("  --version    Show version number")
    console.print()

    console.print("[dim]Learn more: https://cortexlinux.com/docs[/dim]")


def main():
    parser = argparse.ArgumentParser(
        prog='cortex',
        description='AI-powered Linux command interpreter',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cortex install docker
  cortex install docker --execute
  cortex install "python 3.11 with pip"
  cortex install nginx --dry-run
  cortex history
  cortex history show <id>
  cortex rollback <id>
  cortex config list
  cortex config get conflicts.saved_resolutions
  cortex config set llm.provider openai
  cortex config reset
  cortex config export ~/cortex-config.json
  cortex config import ~/cortex-config.json
  cortex demo                       # See Cortex in action (no API key needed)
  cortex install docker             # Plan docker installation
  cortex install docker --execute   # Actually install docker
  cortex install "python 3.11"      # Natural language works too
  cortex history                    # View installation history
  cortex rollback <id>              # Undo an installation

Environment Variables:
  ANTHROPIC_API_KEY   Anthropic API key for Claude (recommended)
  OPENAI_API_KEY      OpenAI API key for GPT-4
        """
    )

    # Global flags
    parser.add_argument('--version', '-V', action='version', version=f'cortex {VERSION}')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed output')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Demo command (first - show this to new users)
    demo_parser = subparsers.add_parser('demo', help='See Cortex in action (no API key needed)')

    # Wizard command
    wizard_parser = subparsers.add_parser('wizard', help='Configure API key interactively')

    # Status command
    status_parser = subparsers.add_parser('status', help='Show system status and security features')

    # Install command
    install_parser = subparsers.add_parser('install', help='Install software using natural language')
    install_parser.add_argument('software', type=str, help='Software to install (natural language)')
    install_parser.add_argument('--execute', action='store_true', help='Execute the generated commands')
    install_parser.add_argument('--dry-run', action='store_true', help='Show commands without executing')
    
    # History command
    history_parser = subparsers.add_parser('history', help='View installation history')
    history_parser.add_argument('--limit', type=int, default=20, help='Number of records to show')
    history_parser.add_argument('--status', choices=['success', 'failed', 'rolled_back', 'in_progress'], 
                               help='Filter by status')
    history_parser.add_argument('show_id', nargs='?', help='Show details for specific installation ID')
    
    # Rollback command
    rollback_parser = subparsers.add_parser('rollback', help='Rollback an installation')
    rollback_parser.add_argument('id', help='Installation ID to rollback')
    rollback_parser.add_argument('--dry-run', action='store_true', help='Show rollback actions without executing')
    
    # Config command
    config_parser = subparsers.add_parser('config', help='Manage user preferences and configuration')
    config_parser.add_argument('action', 
                              choices=['list', 'get', 'set', 'reset', 'validate', 'info', 'export', 'import'],
                              help='Configuration action')
    config_parser.add_argument('key', nargs='?', help='Preference key or file path')
    config_parser.add_argument('value', nargs='?', help='Preference value (for set action)')
    
    args = parser.parse_args()
    
    if not args.command:
        show_rich_help()
        return 0

    cli = CortexCLI(verbose=args.verbose)
    
    try:
        if args.command == 'demo':
            return cli.demo()
        elif args.command == 'wizard':
            return cli.wizard()
        elif args.command == 'status':
            return cli.status()
        elif args.command == 'install':
            return cli.install(args.software, execute=args.execute, dry_run=args.dry_run)
        elif args.command == 'history':
            return cli.history(limit=args.limit, status=args.status, show_id=args.show_id)
        elif args.command == 'rollback':
            return cli.rollback(args.id, dry_run=args.dry_run)
        elif args.command == 'config':
            return cli.config(args.action, args.key, args.value)
        else:
            parser.print_help()
            return 1
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled by user", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
