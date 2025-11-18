import sys
import os
import argparse
import time
import json
from typing import List, Optional, Any
import subprocess
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from LLM.interpreter import CommandInterpreter
from cortex.coordinator import InstallationCoordinator, StepStatus
from installation_history import (
    InstallationHistory,
    InstallationType,
    InstallationStatus
)
from user_preferences import PreferencesManager, VerbosityLevel


class CortexCLI:
    def __init__(self):
        self.spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.spinner_idx = 0
        self.prefs_manager = PreferencesManager()
        try:
            self.prefs_manager.load()
        except Exception:
            pass
    
    def _cred_path(self) -> Path:
        """Return path to credentials file"""
        base = Path.home() / ".cortex"
        base.mkdir(parents=True, exist_ok=True)
        return base / "credentials.json"
    
    def _load_creds(self) -> dict:
        """Load persisted credentials"""
        try:
            p = self._cred_path()
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}
    
    def _get_api_key(self) -> Optional[str]:
        api_key = os.environ.get('OPENAI_API_KEY') or os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            self._print_error("API key not found. Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable.")
            return None
        return api_key
    
    def _get_provider(self) -> str:
        if os.environ.get('OPENAI_API_KEY'):
            return 'openai'
        elif os.environ.get('ANTHROPIC_API_KEY'):
            return 'claude'
        return 'openai'
    
    def _print_status(self, label: str, message: str):
        print(f"{label} {message}")
    
    def _print_error(self, message: str):
        print(f"[ERROR] {message}", file=sys.stderr)
    
    def _print_success(self, message: str):
        print(f"[SUCCESS] {message}")
    
    def _animate_spinner(self, message: str):
        sys.stdout.write(f"\r{self.spinner_chars[self.spinner_idx]} {message}")
        sys.stdout.flush()
        self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner_chars)
        time.sleep(0.1)
    
    def _clear_line(self):
        sys.stdout.write('\r\033[K')
        sys.stdout.flush()
    
    def install(self, software: str, execute: bool = False, dry_run: bool = False):
        api_key = self._get_api_key()
        if not api_key:
            return 1
        
        provider = self._get_provider()
        
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
        """Manage user preferences and configuration"""
        try:
            if action == "list":
                # List all preferences
                prefs = self.prefs_manager.list_all()
                
                print("\n[INFO] Current Configuration:")
                print("=" * 60)
                import yaml
                print(yaml.dump(prefs, default_flow_style=False, sort_keys=False))
                
                # Show config file location
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
                
                # Parse value type
                parsed_value = self._parse_config_value(value)
                
                self.prefs_manager.set(key, parsed_value)
                self.prefs_manager.save()
                
                self._print_success(f"Set {key} = {parsed_value}")
                return 0
            
            elif action == "reset":
                if key:
                    # Reset specific key
                    self.prefs_manager.reset(key)
                    self._print_success(f"Reset {key} to default")
                else:
                    # Reset all preferences
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
                
                from pathlib import Path
                output_path = Path(key)
                self.prefs_manager.export_json(output_path)
                self._print_success(f"Configuration exported to {output_path}")
                return 0
            
            elif action == "import":
                if not key:
                    self._print_error("Input path required for 'import' action")
                    return 1
                
                from pathlib import Path
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
        """Parse configuration value from string"""
        # Handle boolean values
        if value.lower() in ('true', 'yes', 'on', '1'):
            return True
        if value.lower() in ('false', 'no', 'off', '0'):
            return False
        
        # Handle integers
        try:
            return int(value)
        except ValueError:
            pass
        
        # Handle lists (comma-separated)
        if ',' in value:
            return [item.strip() for item in value.split(',')]
        
        # Return as string
        return value


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
  cortex config get ai.model
  cortex config set ai.model gpt-4
  cortex config reset
  cortex config validate

Environment Variables:
  OPENAI_API_KEY      OpenAI API key for GPT-4
  ANTHROPIC_API_KEY   Anthropic API key for Claude
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
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
        parser.print_help()
        return 1
    
    cli = CortexCLI()
    
    try:
        if args.command == 'install':
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
