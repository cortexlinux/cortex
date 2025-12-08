import sys
import os
import argparse
import time
import logging
from typing import List, Optional
import subprocess
from datetime import datetime

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
from cortex.preflight_checker import PreflightChecker, format_report, export_report
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
    
    def install(self, software: str, execute: bool = False, dry_run: bool = False, simulate: bool = False):
        # Handle simulation mode first - no API key needed
        if simulate:
            return self._run_simulation(software)
        
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
            self._print_status("🧠", "Understanding request...")
            
            interpreter = CommandInterpreter(api_key=api_key, provider=provider)
            
            self._print_status("📦", "Planning installation...")
            
            for _ in range(10):
                self._animate_spinner("Analyzing system requirements...")
            self._clear_line()
            
            commands = interpreter.parse(f"install {software}")
            
            if not commands:
                self._print_error("No commands generated. Please try again with a different request.")
                return 1
            
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
            
            self._print_status("⚙️", f"Installing {software}...")
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
                    status_emoji = "⏳"
                    if step.status == StepStatus.SUCCESS:
                        status_emoji = "✅"
                    elif step.status == StepStatus.FAILED:
                        status_emoji = "❌"
                    print(f"\n[{current}/{total}] {status_emoji} {step.description}")
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
                        print(f"\n📝 Installation recorded (ID: {install_id})")
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
                        print(f"\n📝 Installation recorded (ID: {install_id})")
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
    
    def _run_simulation(self, software: str) -> int:
        """Run preflight simulation check for installation"""
        try:
            # Get API key for LLM-powered package info (optional).
            api_key = os.environ.get('OPENAI_API_KEY') or os.environ.get('ANTHROPIC_API_KEY')
            provider = self._get_provider() if api_key else 'openai'
            
            # Create checker with optional API key for enhanced accuracy
            checker = PreflightChecker(api_key=api_key, provider=provider)
            report = checker.run_all_checks(software)
            
            # Print formatted report
            output = format_report(report, software)
            print(output)
            
            # Return error code if blocking issues found
            if report.errors:
                return 1
            return 0
            
        except Exception as e:
            self._print_error(f"Simulation failed: {str(e)}")
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

    def _get_prefs_manager(self):
        """Lazy initialize preferences manager"""
        if self.prefs_manager is None:
            self.prefs_manager = PreferencesManager()
        return self.prefs_manager

    def check_pref(self, key: Optional[str] = None):
        """Check/display user preferences"""
        manager = self._get_prefs_manager()
        
        try:
            if key:
                # Show specific preference
                value = manager.get(key)
                if value is None:
                    self._print_error(f"Preference key '{key}' not found")
                    print("\nAvailable preference keys:")
                    print("  - verbosity")
                    print("  - theme")
                    print("  - language")
                    print("  - timezone")
                    print("  - confirmations.before_install")
                    print("  - confirmations.before_remove")
                    print("  - confirmations.before_upgrade")
                    print("  - confirmations.before_system_changes")
                    print("  - auto_update.check_on_start")
                    print("  - auto_update.auto_install")
                    print("  - auto_update.frequency_hours")
                    print("  - ai.model")
                    print("  - ai.creativity")
                    print("  - ai.explain_steps")
                    print("  - ai.suggest_alternatives")
                    print("  - ai.learn_from_history")
                    print("  - ai.max_suggestions")
                    print("  - packages.default_sources")
                    print("  - packages.prefer_latest")
                    print("  - packages.auto_cleanup")
                    print("  - packages.backup_before_changes")
                    return 1
                
                print(f"\n{key} = {format_preference_value(value)}")
                return 0
            else:
                # Show all preferences
                print_all_preferences(manager)
                
                # Show validation status
                print("\nValidation Status:")
                errors = manager.validate()
                if errors:
                    print("❌ Configuration has errors:")
                    for error in errors:
                        print(f"  - {error}")
                    return 1
                else:
                    print("✅ Configuration is valid")
                
                # Show config info
                info = manager.get_config_info()
                print(f"\nConfiguration file: {info['config_path']}")
                print(f"File size: {info['config_size_bytes']} bytes")
                if info['last_modified']:
                    print(f"Last modified: {info['last_modified']}")
                
                return 0
                
        except Exception as e:
            self._print_error(f"Failed to read preferences: {str(e)}")
            return 1

    def edit_pref(self, action: str, key: Optional[str] = None, value: Optional[str] = None):
        """Edit user preferences (add/set, delete/remove, list)"""
        manager = self._get_prefs_manager()
        
        try:
            if action in ['add', 'set', 'update']:
                # Set/update a preference
                if not key:
                    self._print_error("Key is required for set/add/update action")
                    print("Usage: cortex edit-pref set <key> <value>")
                    print("Example: cortex edit-pref set ai.model gpt-4")
                    return 1
                
                if not value:
                    self._print_error("Value is required for set/add/update action")
                    print("Usage: cortex edit-pref set <key> <value>")
                    return 1
                
                # Get current value for comparison
                old_value = manager.get(key)
                
                # Set new value
                manager.set(key, value)
                
                self._print_success(f"Updated {key}")
                if old_value is not None:
                    print(f"  Old value: {format_preference_value(old_value)}")
                print(f"  New value: {format_preference_value(manager.get(key))}")
                
                # Validate after change
                errors = manager.validate()
                if errors:
                    print("\n⚠️  Warning: Configuration has validation errors:")
                    for error in errors:
                        print(f"  - {error}")
                    print("\nYou may want to fix these issues.")
                
                return 0
                
            elif action in ['delete', 'remove', 'reset-key']:
                # Reset a specific key to default
                if not key:
                    self._print_error("Key is required for delete/remove/reset-key action")
                    print("Usage: cortex edit-pref delete <key>")
                    print("Example: cortex edit-pref delete ai.model")
                    return 1
                
                # To "delete" a key, we reset entire config and reload (since we can't delete individual keys)
                # Instead, we'll reset to the default value for that key
                print(f"Resetting {key} to default value...")
                
                # Create a new manager with defaults
                from cortex.user_preferences import UserPreferences
                defaults = UserPreferences()
                
                # Get the default value
                parts = key.split('.')
                obj = defaults
                for part in parts:
                    obj = getattr(obj, part)
                default_value = obj
                
                # Set to default
                manager.set(key, format_preference_value(default_value))
                
                self._print_success(f"Reset {key} to default")
                print(f"  Value: {format_preference_value(manager.get(key))}")
                
                return 0
                
            elif action in ['list', 'show', 'display']:
                # List all preferences (same as check-pref)
                return self.check_pref()
                
            elif action == 'reset-all':
                # Reset all preferences to defaults
                confirm = input("⚠️  This will reset ALL preferences to defaults. Continue? (yes/no): ")
                if confirm.lower() not in ['yes', 'y']:
                    print("Operation cancelled.")
                    return 0
                
                manager.reset()
                self._print_success("All preferences reset to defaults")
                return 0
                
            elif action == 'validate':
                # Validate configuration
                errors = manager.validate()
                if errors:
                    print("❌ Configuration has errors:")
                    for error in errors:
                        print(f"  - {error}")
                    return 1
                else:
                    self._print_success("Configuration is valid")
                    return 0
                    
            elif action == 'export':
                # Export preferences to file
                if not key:  # Using key as filepath
                    self._print_error("Filepath is required for export action")
                    print("Usage: cortex edit-pref export <filepath>")
                    print("Example: cortex edit-pref export ~/cortex-prefs.json")
                    return 1
                
                from pathlib import Path
                manager.export_json(Path(key))
                return 0
                
            elif action == 'import':
                # Import preferences from file
                if not key:  # Using key as filepath
                    self._print_error("Filepath is required for import action")
                    print("Usage: cortex edit-pref import <filepath>")
                    print("Example: cortex edit-pref import ~/cortex-prefs.json")
                    return 1
                
                from pathlib import Path
                filepath = Path(key)
                if not filepath.exists():
                    self._print_error(f"File not found: {filepath}")
                    return 1
                
                manager.import_json(filepath)
                return 0
                
            else:
                self._print_error(f"Unknown action: {action}")
                print("\nAvailable actions:")
                print("  set/add/update <key> <value>  - Set a preference value")
                print("  delete/remove <key>           - Reset a preference to default")
                print("  list/show/display             - Display all preferences")
                print("  reset-all                     - Reset all preferences to defaults")
                print("  validate                      - Validate configuration")
                print("  export <filepath>             - Export preferences to JSON")
                print("  import <filepath>             - Import preferences from JSON")
                return 1
                
        except AttributeError as e:
            self._print_error(f"Invalid preference key: {key}")
            print("Use 'cortex check-pref' to see available keys")
            return 1
        except Exception as e:
            self._print_error(f"Failed to edit preferences: {str(e)}")
            import traceback
            traceback.print_exc()
            return 1

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
  cortex install docker --simulate
  cortex install "python 3.11 with pip"
  cortex install nginx --dry-run
  cortex history
  cortex history show <id>
  cortex rollback <id>
  cortex check-pref
  cortex check-pref ai.model
  cortex edit-pref set ai.model gpt-4
  cortex edit-pref delete theme
  cortex edit-pref reset-all
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
    install_parser.add_argument('--simulate', action='store_true', help='Simulate installation without making changes')
    
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
    
    # Check preferences command
    check_pref_parser = subparsers.add_parser('check-pref', help='Check/display user preferences')
    check_pref_parser.add_argument('key', nargs='?', help='Specific preference key to check (optional)')
    
    # Edit preferences command
    edit_pref_parser = subparsers.add_parser('edit-pref', help='Edit user preferences')
    edit_pref_parser.add_argument('action', 
                                  choices=['set', 'add', 'update', 'delete', 'remove', 'reset-key', 
                                          'list', 'show', 'display', 'reset-all', 'validate', 'export', 'import'],
                                  help='Action to perform')
    edit_pref_parser.add_argument('key', nargs='?', help='Preference key or filepath (for export/import)')
    edit_pref_parser.add_argument('value', nargs='?', help='Preference value (for set/add/update)')
    
    args = parser.parse_args()
    
    if not args.command:
        show_rich_help()
        return 0

    cli = CortexCLI(verbose=args.verbose)
    
    try:
        if args.command == 'install':
            return cli.install(args.software, execute=args.execute, dry_run=args.dry_run, simulate=args.simulate)
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
        elif args.command == 'check-pref':
            return cli.check_pref(key=args.key)
        elif args.command == 'edit-pref':
            return cli.edit_pref(action=args.action, key=args.key, value=args.value)
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
