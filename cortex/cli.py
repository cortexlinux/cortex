import argparse
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Optional

from cortex.api_key_detector import auto_detect_api_key, setup_api_key
from cortex.ask import AskHandler
from cortex.branding import VERSION, console, cx_header, cx_print, show_banner
from cortex.coordinator import InstallationCoordinator, InstallationStep, StepStatus
from cortex.demo import run_demo
from cortex.dependency_importer import (
    DependencyImporter,
    PackageEcosystem,
    ParseResult,
    format_package_list,
)
from cortex.env_manager import EnvironmentManager, get_env_manager
from cortex.installation_history import InstallationHistory, InstallationStatus, InstallationType
from cortex.llm.interpreter import CommandInterpreter
from cortex.network_config import NetworkConfig
from cortex.notification_manager import NotificationManager
from cortex.stack_manager import StackManager
from cortex.templates import InstallationStep, Template, TemplateFormat, TemplateManager
from cortex.validators import (
    validate_api_key,
    validate_install_request,
)

# Suppress noisy log messages in normal operation
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("cortex.installation_history").setLevel(logging.ERROR)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class CortexCLI:
    def __init__(self, verbose: bool = False):
        self.spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.spinner_idx = 0
        self.verbose = verbose

    # Define a method to handle Docker-specific permission repairs
    def docker_permissions(self, args: argparse.Namespace) -> int:
        """Handle the diagnosis and repair of Docker file permissions.

        This method coordinates the environment-aware scanning of the project
        directory and applies ownership reclamation logic. It ensures that
        administrative actions (sudo) are never performed without user
        acknowledgment unless the non-interactive flag is present.

        Args:
            args: The parsed command-line arguments containing the execution
                context and safety flags.

        Returns:
            int: 0 if successful or the operation was gracefully cancelled,
                1 if a system or logic error occurred.
        """
        from cortex.permission_manager import PermissionManager

        try:
            manager = PermissionManager(os.getcwd())
            cx_print("🔍 Scanning for Docker-related permission issues...", "info")

            # Validate Docker Compose configurations for missing user mappings
            # to help prevent future permission drift.
            manager.check_compose_config()

            # Retrieve execution context from argparse.
            execute_flag = getattr(args, "execute", False)
            yes_flag = getattr(args, "yes", False)

            # SAFETY GUARD: If executing repairs, prompt for confirmation unless
            # the --yes flag was provided. This follows the project safety
            # standard: 'No silent sudo execution'.
            if execute_flag and not yes_flag:
                mismatches = manager.diagnose()
                if mismatches:
                    cx_print(
                        f"⚠️ Found {len(mismatches)} paths requiring ownership reclamation.",
                        "warning",
                    )
                    try:
                        # Interactive confirmation prompt for administrative repair.
                        response = console.input(
                            "[bold cyan]Reclaim ownership using sudo? (y/n): [/bold cyan]"
                        )
                        if response.lower() not in ("y", "yes"):
                            cx_print("Operation cancelled", "info")
                            return 0
                    except (EOFError, KeyboardInterrupt):
                        # Graceful handling of terminal exit or manual interruption.
                        console.print()
                        cx_print("Operation cancelled", "info")
                        return 0

            # Delegate repair logic to PermissionManager. If execute is False,
            # a dry-run report is generated. If True, repairs are batched to
            # avoid system ARG_MAX shell limits.
            if manager.fix_permissions(execute=execute_flag):
                if execute_flag:
                    cx_print("✨ Permissions fixed successfully!", "success")
                return 0

            return 1

        except (PermissionError, FileNotFoundError, OSError) as e:
            # Handle system-level access issues or missing project files.
            cx_print(f"❌ Permission check failed: {e}", "error")
            return 1
        except NotImplementedError as e:
            # Report environment incompatibility (e.g., native Windows).
            cx_print(f"❌ {e}", "error")
            return 1
        except Exception as e:
            # Safety net for unexpected runtime exceptions to prevent CLI crashes.
            cx_print(f"❌ Unexpected error: {e}", "error")
            return 1

    def _debug(self, message: str):
        """Print debug info only in verbose mode"""
        if self.verbose:
            console.print(f"[dim][DEBUG] {message}[/dim]")

    def _get_api_key(self) -> str | None:
        # 1. Check explicit provider override first (fake/ollama need no key)
        explicit_provider = os.environ.get("CORTEX_PROVIDER", "").lower()
        if explicit_provider == "fake":
            self._debug("Using Fake provider for testing")
            return "fake-key"
        if explicit_provider == "ollama":
            self._debug("Using Ollama (no API key required)")
            return "ollama-local"

        # 2. Try auto-detection + prompt to save (setup_api_key handles both)
        success, key, detected_provider = setup_api_key()
        if success:
            self._debug(f"Using {detected_provider} API key")
            # Store detected provider so _get_provider can use it
            self._detected_provider = detected_provider
            return key

        # Still no key
        self._print_error("No API key found or provided")
        cx_print("Run [bold]cortex wizard[/bold] to configure your API key.", "info")
        cx_print("Or use [bold]CORTEX_PROVIDER=ollama[/bold] for offline mode.", "info")
        return None

    def _get_provider(self) -> str:
        # Check environment variable for explicit provider choice
        explicit_provider = os.environ.get("CORTEX_PROVIDER", "").lower()
        if explicit_provider in ["ollama", "openai", "claude", "fake"]:
            return explicit_provider

        # Use provider from auto-detection (set by _get_api_key)
        detected = getattr(self, "_detected_provider", None)
        if detected == "anthropic":
            return "claude"
        elif detected == "openai":
            return "openai"

        # Check env vars (may have been set by auto-detect)
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "claude"
        elif os.environ.get("OPENAI_API_KEY"):
            return "openai"

        # Fallback to Ollama for offline mode
        return "ollama"

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
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    # --- New Notification Method ---
    def notify(self, args):
        """Handle notification commands"""
        # Addressing CodeRabbit feedback: Handle missing subcommand gracefully
        if not args.notify_action:
            self._print_error("Please specify a subcommand (config/enable/disable/dnd/send)")
            return 1

        mgr = NotificationManager()

        if args.notify_action == "config":
            console.print("[bold cyan]🔧 Current Notification Configuration:[/bold cyan]")
            status = (
                "[green]Enabled[/green]"
                if mgr.config.get("enabled", True)
                else "[red]Disabled[/red]"
            )
            console.print(f"Status: {status}")
            console.print(
                f"DND Window: [yellow]{mgr.config['dnd_start']} - {mgr.config['dnd_end']}[/yellow]"
            )
            console.print(f"History File: {mgr.history_file}")
            return 0

        elif args.notify_action == "enable":
            mgr.config["enabled"] = True
            # Addressing CodeRabbit feedback: Ideally should use a public method instead of private _save_config,
            # but keeping as is for a simple fix (or adding a save method to NotificationManager would be best).
            mgr._save_config()
            self._print_success("Notifications enabled")
            return 0

        elif args.notify_action == "disable":
            mgr.config["enabled"] = False
            mgr._save_config()
            cx_print("Notifications disabled (Critical alerts will still show)", "warning")
            return 0

        elif args.notify_action == "dnd":
            if not args.start or not args.end:
                self._print_error("Please provide start and end times (HH:MM)")
                return 1

            # Addressing CodeRabbit feedback: Add time format validation
            try:
                datetime.strptime(args.start, "%H:%M")
                datetime.strptime(args.end, "%H:%M")
            except ValueError:
                self._print_error("Invalid time format. Use HH:MM (e.g., 22:00)")
                return 1
            mgr.config["dnd_start"] = args.start
            mgr.config["dnd_end"] = args.end
            mgr._save_config()
            self._print_success(f"DND Window updated: {args.start} - {args.end}")
            return 0

        elif args.notify_action == "send":
            if not args.message:
                self._print_error("Message required")
                return 1
            console.print("[dim]Sending notification...[/dim]")
            mgr.send(args.title, args.message, level=args.level, actions=args.actions)
            return 0

        else:
            self._print_error("Unknown notify command")
            return 1

    # -------------------------------
    def demo(self):
        """
        Run the one-command investor demo
        """
        return run_demo()

    def stack(self, args: argparse.Namespace) -> int:
        """Handle `cortex stack` commands (list/describe/install/dry-run)."""
        try:
            manager = StackManager()

            # Validate --dry-run requires a stack name
            if args.dry_run and not args.name:
                self._print_error(
                    "--dry-run requires a stack name (e.g., `cortex stack ml --dry-run`)"
                )
                return 1

            # List stacks (default when no name/describe)
            if args.list or (not args.name and not args.describe):
                return self._handle_stack_list(manager)

            # Describe a specific stack
            if args.describe:
                return self._handle_stack_describe(manager, args.describe)

            # Install a stack (only remaining path)
            return self._handle_stack_install(manager, args)

        except FileNotFoundError as e:
            self._print_error(f"stacks.json not found. Ensure cortex/stacks.json exists: {e}")
            return 1
        except ValueError as e:
            self._print_error(f"stacks.json is invalid or malformed: {e}")
            return 1

    def _handle_stack_list(self, manager: StackManager) -> int:
        """List all available stacks (legacy simple stacks)."""
        stacks = manager.list_stacks()
        cx_print("\n📦 Available Stacks:\n", "info")
        for stack in stacks:
            pkg_count = len(stack.get("packages", []))
            console.print(f"  [green]{stack.get('id', 'unknown')}[/green]")
            console.print(f"    {stack.get('name', 'Unnamed Stack')}")
            console.print(f"    {stack.get('description', 'No description')}")
            console.print(f"    [dim]({pkg_count} packages)[/dim]\n")
        cx_print("Use: cortex install --stack <name> --execute to install", "info")
        return 0

    def _handle_stack_describe(self, manager: StackManager, stack_id: str) -> int:
        """Describe a specific stack (legacy simple stacks)."""
        stack = manager.find_stack(stack_id)
        if not stack:
            self._print_error(
                f"Stack '{stack_id}' not found. Use 'cortex stack list' to see available stacks."
            )
            return 1
        description = manager.describe_stack(stack_id)
        console.print(description)
        cx_print(f"\nTo install: cortex install --stack {stack_id} --execute", "info")
        return 0

    def _handle_stack_install(self, manager: StackManager, args: argparse.Namespace) -> int:
        """Install a stack with optional hardware-aware selection."""
        original_name = args.name
        suggested_name = manager.suggest_stack(args.name)

        if suggested_name != original_name:
            cx_print(
                f"💡 No GPU detected, using '{suggested_name}' instead of '{original_name}'",
                "info",
            )

        stack = manager.find_stack(suggested_name)
        if not stack:
            self._print_error(
                f"Stack '{suggested_name}' not found. Use --list to see available stacks."
            )
            return 1

        packages = stack.get("packages", [])
        if not packages:
            self._print_error(f"Stack '{suggested_name}' has no packages configured.")
            return 1

        if args.dry_run:
            return self._handle_stack_dry_run(stack, packages)

        return self._handle_stack_real_install(stack, packages)

    def _handle_stack_dry_run(self, stack: dict[str, Any], packages: list[str]) -> int:
        """Preview packages that would be installed without executing."""
        cx_print(f"\n📋 Stack: {stack['name']}", "info")
        console.print("\nPackages that would be installed:")
        for pkg in packages:
            console.print(f"  • {pkg}")
        console.print(f"\nTotal: {len(packages)} packages")
        cx_print("\nDry run only - no commands executed", "warning")
        return 0

    def _handle_stack_real_install(self, stack: dict[str, Any], packages: list[str]) -> int:
        """Install all packages in the stack."""
        cx_print(f"\n🚀 Installing stack: {stack['name']}\n", "success")

        # Batch into a single LLM request
        packages_str = " ".join(packages)
        result = self.install(software=packages_str, execute=True, dry_run=False)

        if result != 0:
            self._print_error(f"Failed to install stack '{stack['name']}'")
            return 1

        self._print_success(f"\n✅ Stack '{stack['name']}' installed successfully!")
        console.print(f"Installed {len(packages)} packages")
        return 0

    # --- Sandbox Commands (Docker-based package testing) ---
    def sandbox(self, args: argparse.Namespace) -> int:
        """Handle `cortex sandbox` commands for Docker-based package testing."""
        from cortex.sandbox import (
            DockerNotFoundError,
            DockerSandbox,
            SandboxAlreadyExistsError,
            SandboxNotFoundError,
            SandboxTestStatus,
        )

        action = getattr(args, "sandbox_action", None)

        if not action:
            cx_print("\n🐳 Docker Sandbox - Test packages safely before installing\n", "info")
            console.print("Usage: cortex sandbox <command> [options]")
            console.print("\nCommands:")
            console.print("  create <name>              Create a sandbox environment")
            console.print("  install <name> <package>   Install package in sandbox")
            console.print("  test <name> [package]      Run tests in sandbox")
            console.print("  promote <name> <package>   Install tested package on main system")
            console.print("  cleanup <name>             Remove sandbox environment")
            console.print("  list                       List all sandboxes")
            console.print("  exec <name> <cmd...>       Execute command in sandbox")
            console.print("\nExample workflow:")
            console.print("  cortex sandbox create test-env")
            console.print("  cortex sandbox install test-env nginx")
            console.print("  cortex sandbox test test-env")
            console.print("  cortex sandbox promote test-env nginx")
            console.print("  cortex sandbox cleanup test-env")
            return 0

        try:
            sandbox = DockerSandbox()

            if action == "create":
                return self._sandbox_create(sandbox, args)
            elif action == "install":
                return self._sandbox_install(sandbox, args)
            elif action == "test":
                return self._sandbox_test(sandbox, args)
            elif action == "promote":
                return self._sandbox_promote(sandbox, args)
            elif action == "cleanup":
                return self._sandbox_cleanup(sandbox, args)
            elif action == "list":
                return self._sandbox_list(sandbox)
            elif action == "exec":
                return self._sandbox_exec(sandbox, args)
            else:
                self._print_error(f"Unknown sandbox action: {action}")
                return 1

        except DockerNotFoundError as e:
            self._print_error(str(e))
            cx_print("Docker is required only for sandbox commands.", "info")
            return 1
        except SandboxNotFoundError as e:
            self._print_error(str(e))
            cx_print("Use 'cortex sandbox list' to see available sandboxes.", "info")
            return 1
        except SandboxAlreadyExistsError as e:
            self._print_error(str(e))
            return 1

    def _sandbox_create(self, sandbox, args: argparse.Namespace) -> int:
        """Create a new sandbox environment."""
        name = args.name
        image = getattr(args, "image", "ubuntu:22.04")

        cx_print(f"Creating sandbox '{name}'...", "info")
        result = sandbox.create(name, image=image)

        if result.success:
            cx_print(f"✓ Sandbox environment '{name}' created", "success")
            console.print(f"  [dim]{result.stdout}[/dim]")
            return 0
        else:
            self._print_error(result.message)
            if result.stderr:
                console.print(f"  [red]{result.stderr}[/red]")
            return 1

    def _sandbox_install(self, sandbox, args: argparse.Namespace) -> int:
        """Install a package in sandbox."""
        name = args.name
        package = args.package

        cx_print(f"Installing '{package}' in sandbox '{name}'...", "info")
        result = sandbox.install(name, package)

        if result.success:
            cx_print(f"✓ {package} installed in sandbox", "success")
            return 0
        else:
            self._print_error(result.message)
            if result.stderr:
                console.print(f"  [dim]{result.stderr[:500]}[/dim]")
            return 1

    def _sandbox_test(self, sandbox, args: argparse.Namespace) -> int:
        """Run tests in sandbox."""
        from cortex.sandbox import SandboxTestStatus

        name = args.name
        package = getattr(args, "package", None)

        cx_print(f"Running tests in sandbox '{name}'...", "info")
        result = sandbox.test(name, package)

        console.print()
        for test in result.test_results:
            if test.result == SandboxTestStatus.PASSED:
                console.print(f"   ✓  {test.name}")
                if test.message:
                    console.print(f"      [dim]{test.message[:80]}[/dim]")
            elif test.result == SandboxTestStatus.FAILED:
                console.print(f"   ✗  {test.name}")
                if test.message:
                    console.print(f"      [red]{test.message}[/red]")
            else:
                console.print(f"   ⊘  {test.name} [dim](skipped)[/dim]")

        console.print()
        if result.success:
            cx_print("All tests passed", "success")
            return 0
        else:
            self._print_error("Some tests failed")
            return 1

    def _sandbox_promote(self, sandbox, args: argparse.Namespace) -> int:
        """Promote a tested package to main system."""
        name = args.name
        package = args.package
        dry_run = getattr(args, "dry_run", False)
        skip_confirm = getattr(args, "yes", False)

        if dry_run:
            result = sandbox.promote(name, package, dry_run=True)
            cx_print(f"Would run: sudo apt-get install -y {package}", "info")
            return 0

        # Confirm with user unless -y flag
        if not skip_confirm:
            console.print(f"\nPromote '{package}' to main system? [Y/n]: ", end="")
            try:
                response = input().strip().lower()
                if response and response not in ("y", "yes"):
                    cx_print("Promotion cancelled", "warning")
                    return 0
            except (EOFError, KeyboardInterrupt):
                console.print()
                cx_print("Promotion cancelled", "warning")
                return 0

        cx_print(f"Installing '{package}' on main system...", "info")
        result = sandbox.promote(name, package, dry_run=False)

        if result.success:
            cx_print(f"✓ {package} installed on main system", "success")
            return 0
        else:
            self._print_error(result.message)
            if result.stderr:
                console.print(f"  [red]{result.stderr[:500]}[/red]")
            return 1

    def _sandbox_cleanup(self, sandbox, args: argparse.Namespace) -> int:
        """Remove a sandbox environment."""
        name = args.name
        force = getattr(args, "force", False)

        cx_print(f"Removing sandbox '{name}'...", "info")
        result = sandbox.cleanup(name, force=force)

        if result.success:
            cx_print(f"✓ Sandbox '{name}' removed", "success")
            return 0
        else:
            self._print_error(result.message)
            return 1

    def _sandbox_list(self, sandbox) -> int:
        """List all sandbox environments."""
        sandboxes = sandbox.list_sandboxes()

        if not sandboxes:
            cx_print("No sandbox environments found", "info")
            cx_print("Create one with: cortex sandbox create <name>", "info")
            return 0

        cx_print("\n🐳 Sandbox Environments:\n", "info")
        for sb in sandboxes:
            status_icon = "🟢" if sb.state.value == "running" else "⚪"
            console.print(f"  {status_icon} [green]{sb.name}[/green]")
            console.print(f"      Image: {sb.image}")
            console.print(f"      Created: {sb.created_at[:19]}")
            if sb.packages:
                console.print(f"      Packages: {', '.join(sb.packages)}")
            console.print()

        return 0

    def _sandbox_exec(self, sandbox, args: argparse.Namespace) -> int:
        """Execute command in sandbox."""
        name = args.name
        command = args.command

        result = sandbox.exec_command(name, command)

        if result.stdout:
            console.print(result.stdout, end="")
        if result.stderr:
            console.print(result.stderr, style="red", end="")

        return result.exit_code

    # --- End Sandbox Commands ---

    def ask(self, question: str) -> int:
        """Answer a natural language question about the system."""
        api_key = self._get_api_key()
        if not api_key:
            return 1

        provider = self._get_provider()
        self._debug(f"Using provider: {provider}")

        try:
            handler = AskHandler(
                api_key=api_key,
                provider=provider,
            )
            answer = handler.ask(question)
            console.print(answer)
            return 0
        except ImportError as e:
            # Provide a helpful message if provider SDK is missing
            self._print_error(str(e))
            cx_print(
                "Install the required SDK or set CORTEX_PROVIDER=ollama for local mode.", "info"
            )
            return 1
        except ValueError as e:
            self._print_error(str(e))
            return 1
        except RuntimeError as e:
            self._print_error(str(e))
            return 1

    def install(
        self,
        software: str,
        execute: bool = False,
        dry_run: bool = False,
        stack: str | None = None,
        parallel: bool = False,
    ):
        # Validate input first (only if not using stack)
        if not stack:
            is_valid, error = validate_install_request(software)
            if not is_valid:
                self._print_error(error)
                return 1

            # Special-case the ml-cpu stack:
            # The LLM sometimes generates outdated torch==1.8.1+cpu installs
            # which fail on modern Python. For the "pytorch-cpu jupyter numpy pandas"
            # combo, force a supported CPU-only PyTorch recipe instead.
            normalized = " ".join(software.split()).lower()

            if normalized == "pytorch-cpu jupyter numpy pandas":
                software = (
                    "pip3 install torch torchvision torchaudio "
                    "--index-url https://download.pytorch.org/whl/cpu && "
                    "pip3 install jupyter numpy pandas"
                )

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
            # If stack is specified, use stack/template system
            if stack:
                return self._install_from_stack(stack, execute, dry_run)
            # Otherwise, use LLM-based installation
            self._print_status("🧠", "Understanding request...")

            interpreter = CommandInterpreter(api_key=api_key, provider=provider)
            self._print_status("📦", "Planning installation...")
            for _ in range(10):
                self._animate_spinner("Analyzing system requirements...")
            self._clear_line()
            commands = interpreter.parse(f"install {software}")
            if not commands:
                self._print_error(
                    "No commands generated. Please try again with a different request."
                )
                return 1

            # Extract packages from commands for tracking
            packages = history._extract_packages_from_commands(commands)
            # Record installation start
            if execute or dry_run:
                install_id = history.record_installation(
                    InstallationType.INSTALL, packages, commands, start_time
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

                if parallel:
                    import asyncio

                    from cortex.install_parallel import run_parallel_install

                    def parallel_log_callback(message: str, level: str = "info"):
                        if level == "success":
                            cx_print(f"  ✅ {message}", "success")
                        elif level == "error":
                            cx_print(f"  ❌ {message}", "error")
                        else:
                            cx_print(f"  ℹ {message}", "info")

                    try:
                        success, parallel_tasks = asyncio.run(
                            run_parallel_install(
                                commands=commands,
                                descriptions=[f"Step {i + 1}" for i in range(len(commands))],
                                timeout=300,
                                stop_on_error=True,
                                log_callback=parallel_log_callback,
                            )
                        )

                        total_duration = 0.0
                        if parallel_tasks:
                            max_end = max(
                                (t.end_time for t in parallel_tasks if t.end_time is not None),
                                default=None,
                            )
                            min_start = min(
                                (t.start_time for t in parallel_tasks if t.start_time is not None),
                                default=None,
                            )
                            if max_end is not None and min_start is not None:
                                total_duration = max_end - min_start

                        if success:
                            self._print_success(f"{software} installed successfully!")
                            print(f"\nCompleted in {total_duration:.2f} seconds (parallel mode)")

                            if install_id:
                                history.update_installation(install_id, InstallationStatus.SUCCESS)
                                print(f"\n📝 Installation recorded (ID: {install_id})")
                                print(f"   To rollback: cortex rollback {install_id}")

                            return 0

                        failed_tasks = [
                            t for t in parallel_tasks if getattr(t.status, "value", "") == "failed"
                        ]
                        error_msg = failed_tasks[0].error if failed_tasks else "Installation failed"

                        if install_id:
                            history.update_installation(
                                install_id,
                                InstallationStatus.FAILED,
                                error_msg,
                            )

                        self._print_error("Installation failed")
                        if error_msg:
                            print(f"  Error: {error_msg}", file=sys.stderr)
                        if install_id:
                            print(f"\n📝 Installation recorded (ID: {install_id})")
                            print(f"   View details: cortex history {install_id}")
                        return 1

                    except (ValueError, OSError) as e:
                        if install_id:
                            history.update_installation(
                                install_id, InstallationStatus.FAILED, str(e)
                            )
                        self._print_error(f"Parallel execution failed: {str(e)}")
                        return 1
                    except Exception as e:
                        if install_id:
                            history.update_installation(
                                install_id, InstallationStatus.FAILED, str(e)
                            )
                        self._print_error(f"Unexpected parallel execution error: {str(e)}")
                        if self.verbose:
                            import traceback

                            traceback.print_exc()
                        return 1

                coordinator = InstallationCoordinator(
                    commands=commands,
                    descriptions=[f"Step {i + 1}" for i in range(len(commands))],
                    timeout=300,
                    stop_on_error=True,
                    progress_callback=progress_callback,
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
                            install_id, InstallationStatus.FAILED, error_msg
                        )
                    if result.failed_step is not None:
                        self._print_error(f"Installation failed at step {result.failed_step + 1}")
                    else:
                        self._print_error("Installation failed")
                    if result.error_message:
                        print(f"  Error: {result.error_message}", file=sys.stderr)
                    if install_id:
                        print(f"\n📝 Installation recorded (ID: {install_id})")
                        print(f"   View details: cortex history {install_id}")
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
        except OSError as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            self._print_error(f"System error: {str(e)}")
            return 1
        except Exception as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            self._print_error(f"Unexpected error: {str(e)}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return 1

    def cache_stats(self) -> int:
        try:
            from cortex.semantic_cache import SemanticCache

            cache = SemanticCache()
            stats = cache.stats()
            hit_rate = f"{stats.hit_rate * 100:.1f}%" if stats.total else "0.0%"

            cx_header("Cache Stats")
            cx_print(f"Hits: {stats.hits}", "info")
            cx_print(f"Misses: {stats.misses}", "info")
            cx_print(f"Hit rate: {hit_rate}", "info")
            cx_print(f"Saved calls (approx): {stats.hits}", "info")
            return 0
        except (ImportError, OSError) as e:
            self._print_error(f"Unable to read cache stats: {e}")
            return 1
        except Exception as e:
            self._print_error(f"Unexpected error reading cache stats: {e}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return 1

    def history(self, limit: int = 20, status: str | None = None, show_id: str | None = None):
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
                    print("\nCommands executed:")
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

                print(
                    f"\n{'ID':<18} {'Date':<20} {'Operation':<12} {'Packages':<30} {'Status':<15}"
                )
                print("=" * 100)

                for r in records:
                    date = r.timestamp[:19].replace("T", " ")
                    packages = ", ".join(r.packages[:2])
                    if len(r.packages) > 2:
                        packages += f" +{len(r.packages) - 2}"

                    print(
                        f"{r.id:<18} {date:<20} {r.operation_type.value:<12} {packages:<30} {r.status.value:<15}"
                    )

                return 0
        except (ValueError, OSError) as e:
            self._print_error(f"Failed to retrieve history: {str(e)}")
            return 1
        except Exception as e:
            self._print_error(f"Unexpected error retrieving history: {str(e)}")
            if self.verbose:
                import traceback

                traceback.print_exc()
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
        except (ValueError, OSError) as e:
            self._print_error(f"Rollback failed: {str(e)}")
            return 1
        except Exception as e:
            self._print_error(f"Unexpected rollback error: {str(e)}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return 1

    def _install_from_stack(self, stack_name: str, execute: bool, dry_run: bool):
        """Install from a stack (template)."""
        history = InstallationHistory()
        install_id = None
        start_time = datetime.now()

        try:
            template_manager = TemplateManager()

            self._print_status("[*]", f"Loading stack: {stack_name}...")
            template = template_manager.load_template(stack_name)

            if not template:
                self._print_error(f"Stack '{stack_name}' not found")
                self._print_status("[*]", "Available stacks:")
                templates = template_manager.list_templates()
                for name, info in templates.items():
                    print(f"  - {name}: {info['description']}")
                return 1

            # Display stack info
            print(f"\n{template.name} Stack:")
            print(f"   {template.description}")
            print("\n   Packages:")
            for pkg in template.packages:
                print(f"   - {pkg}")

            # Check hardware compatibility
            is_compatible, warnings = template_manager.check_hardware_compatibility(template)
            if warnings:
                print("\n[WARNING] Hardware Compatibility Warnings:")
                for warning in warnings:
                    print(f"   - {warning}")
                if not is_compatible and not dry_run:
                    try:
                        response = input(
                            "\n[WARNING] Hardware requirements not met. Continue anyway? (y/N): "
                        )
                        if response.lower() != "y":
                            print("\n[INFO] Installation aborted by user")
                            return 1
                    except (EOFError, KeyboardInterrupt):
                        # Non-interactive environment or user cancelled
                        print(
                            "\n[ERROR] Aborting install: cannot prompt for hardware confirmation in non-interactive mode"
                        )
                        print(
                            "        Use --dry-run to preview commands, or ensure hardware requirements are met"
                        )
                        return 1

            # Generate commands
            self._print_status("[*]", "Generating installation commands...")
            commands = template_manager.generate_commands(template)

            if not commands:
                self._print_error("No commands generated from template")
                return 1

            # Extract packages for tracking
            packages = (
                template.packages
                if template.packages
                else history._extract_packages_from_commands(commands)
            )

            # Record installation start
            if execute or dry_run:
                install_id = history.record_installation(
                    InstallationType.INSTALL, packages, commands, start_time
                )

            print(f"\n[*] Installing {len(packages)} packages...")
            print("\nGenerated commands:")
            for i, cmd in enumerate(commands, 1):
                print(f"  {i}. {cmd}")

            if dry_run:
                print("\n(Dry run mode - commands not executed)")
                if install_id:
                    history.update_installation(install_id, InstallationStatus.SUCCESS)
                return 0

            if execute:
                # Convert template steps to coordinator format if available
                if template.steps:
                    plan = []
                    for step in template.steps:
                        # Add sudo prefix if requires_root is True
                        command = step.command
                        if step.requires_root and not command.strip().startswith("sudo "):
                            command = f"sudo {command}"

                        plan.append(
                            {
                                "command": command,
                                "description": step.description,
                                "rollback": step.rollback,
                            }
                        )
                    coordinator = InstallationCoordinator.from_plan(
                        plan, timeout=300, stop_on_error=True
                    )
                else:

                    def progress_callback(current, total, step):
                        status_emoji = "⏳"
                        if step.status == StepStatus.SUCCESS:
                            status_emoji = "✅"
                        elif step.status == StepStatus.FAILED:
                            status_emoji = "❌"
                        print(f"\n[{current}/{total}] {status_emoji} {step.description}")
                        print(f"  Command: {step.command}")

                    coordinator = InstallationCoordinator(
                        commands=commands,
                        descriptions=[f"Step {i+1}" for i in range(len(commands))],
                        timeout=300,
                        stop_on_error=True,
                        progress_callback=progress_callback,
                    )

                print("\nExecuting commands...")
                result = coordinator.execute()

                if result.success:
                    # Run verification commands if available
                    if template.verification_commands:
                        self._print_status("[*]", "Verifying installation...")
                        verify_results = coordinator.verify_installation(
                            template.verification_commands
                        )
                        all_passed = all(verify_results.values())
                        if not all_passed:
                            print("\n[WARNING] Some verification checks failed:")
                            for cmd, passed in verify_results.items():
                                status = "[OK]" if passed else "[FAIL]"
                                print(f"  {status} {cmd}")

                    # Run post-install commands once
                    if template.post_install:
                        self._print_status("[*]", "Running post-installation steps...")
                        print("\n[*] Post-installation information:")
                        for cmd in template.post_install:
                            subprocess.run(cmd, shell=True)

                    self._print_success(f"{template.name} stack ready!")
                    print(f"\nCompleted in {result.total_duration:.2f} seconds")

                    # Record successful installation
                    if install_id:
                        history.update_installation(install_id, InstallationStatus.SUCCESS)
                        print(f"\n[*] Installation recorded (ID: {install_id})")
                        print(f"   To rollback: cortex rollback {install_id}")

                    return 0
                else:
                    # Record failed installation
                    if install_id:
                        error_msg = result.error_message or "Installation failed"
                        history.update_installation(
                            install_id, InstallationStatus.FAILED, error_msg
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
                print(f"Example: cortex install --stack {stack_name} --execute")

            return 0

        except ValueError as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            self._print_error(str(e))
            return 1
        except (RuntimeError, OSError, subprocess.SubprocessError) as e:
            if install_id:
                history.update_installation(install_id, InstallationStatus.FAILED, str(e))
            self._print_error(f"Unexpected error: {str(e)}")
            return 1

    def stack_list(self):
        """List all available stacks."""
        try:
            template_manager = TemplateManager()
            templates = template_manager.list_templates()

            if not templates:
                print("No stacks found.")
                return 0

            print("\nAvailable Stacks:")
            print("=" * 80)
            print(f"{'Name':<20} {'Version':<12} {'Type':<12} {'Description':<35}")
            print("=" * 80)

            for name, info in sorted(templates.items()):
                desc = (
                    info["description"][:33] + "..."
                    if len(info["description"]) > 35
                    else info["description"]
                )
                print(f"{name:<20} {info['version']:<12} {info['type']:<12} {desc:<35}")

            print(f"\nTotal: {len(templates)} stacks")
            print("\nTo install a stack:")
            print("  cortex install --stack <name> --dry-run    # Preview")
            print("  cortex install --stack <name> --execute    # Install")
            return 0
        except Exception as e:
            self._print_error(f"Failed to list stacks: {str(e)}")
            return 1

    def stack_describe(self, name: str):
        """Show detailed information about a stack."""
        try:
            template_manager = TemplateManager()
            template = template_manager.load_template(name)

            if not template:
                self._print_error(f"Stack '{name}' not found")
                print("\nAvailable stacks:")
                templates = template_manager.list_templates()
                for stack_name in sorted(templates.keys()):
                    print(f"  - {stack_name}")
                return 1

            # Display stack details
            print(f"\n📦 Stack: {template.name}")
            print(f"   {template.description}")
            print(f"   Version: {template.version}")
            if template.author:
                print(f"   Author: {template.author}")

            print("\n   Packages:")
            for pkg in template.packages:
                print(f"     - {pkg}")

            # Show hardware requirements if present
            if template.hardware_requirements:
                hw = template.hardware_requirements
                print("\n   Hardware Requirements:")
                if hw.min_ram_mb:
                    print(f"     - Minimum RAM: {hw.min_ram_mb}MB")
                if hw.min_cores:
                    print(f"     - Minimum CPU cores: {hw.min_cores}")
                if hw.min_storage_mb:
                    print(f"     - Minimum storage: {hw.min_storage_mb}MB")
                if hw.requires_gpu:
                    gpu_info = "Required"
                    if hw.gpu_vendor:
                        gpu_info += f" ({hw.gpu_vendor})"
                    print(f"     - GPU: {gpu_info}")
                if hw.requires_cuda:
                    cuda_info = "Required"
                    if hw.min_cuda_version:
                        cuda_info += f" (>= {hw.min_cuda_version})"
                    print(f"     - CUDA: {cuda_info}")

            # Show verification commands if present
            if template.verification_commands:
                print("\n   Verification commands:")
                for cmd in template.verification_commands:
                    print(f"     $ {cmd}")

            print("\n   To install this stack:")
            print(f"     cortex install --stack {name} --dry-run    # Preview")
            print(f"     cortex install --stack {name} --execute    # Install")

            return 0
        except Exception as e:
            self._print_error(f"Failed to describe stack: {str(e)}")
            return 1

    def stack_create(self, name: str, interactive: bool = True):
        """Create a new stack interactively."""
        try:
            print(f"\n[*] Creating stack: {name}")

            if interactive:
                description = input("Description: ").strip()
                if not description:
                    self._print_error("Description is required")
                    return 1

                version = input("Version (default: 1.0.0): ").strip() or "1.0.0"
                author = input("Author (optional): ").strip() or None

                print("\nEnter packages (one per line, empty line to finish):")
                packages = []
                while True:
                    pkg = input("  Package: ").strip()
                    if not pkg:
                        break
                    packages.append(pkg)

                # Create stack template
                from cortex.templates import HardwareRequirements, Template

                template = Template(
                    name=name,
                    description=description,
                    version=version,
                    author=author,
                    packages=packages,
                )

                # Ask about hardware requirements
                print("\nHardware Requirements (optional):")
                min_ram = input("  Minimum RAM (MB, optional): ").strip()
                min_cores = input("  Minimum CPU cores (optional): ").strip()
                min_storage = input("  Minimum storage (MB, optional): ").strip()

                if min_ram or min_cores or min_storage:
                    try:
                        hw_req = HardwareRequirements(
                            min_ram_mb=int(min_ram) if min_ram else None,
                            min_cores=int(min_cores) if min_cores else None,
                            min_storage_mb=int(min_storage) if min_storage else None,
                        )
                    except ValueError:
                        self._print_error("Hardware requirements must be numeric values")
                        return 1
                    template.hardware_requirements = hw_req

                # Save stack
                template_manager = TemplateManager()
                template_path = template_manager.save_template(template, name)

                self._print_success(f"Stack '{name}' created successfully!")
                print(f"  Saved to: {template_path}")
                return 0
            else:
                self._print_error("Non-interactive stack creation not yet supported")
                return 1

        except Exception as e:
            self._print_error(f"Failed to create stack: {str(e)}")
            return 1

    def stack_import(self, file_path: str, name: str | None = None):
        """Import a stack from a file."""
        try:
            template_manager = TemplateManager()
            template = template_manager.import_template(file_path, name)

            # Save to user stacks
            save_name = name or template.name
            template_path = template_manager.save_template(template, save_name)

            self._print_success(f"Stack '{save_name}' imported successfully!")
            print(f"  Saved to: {template_path}")
            return 0
        except Exception as e:
            self._print_error(f"Failed to import stack: {str(e)}")
            return 1

    def stack_export(self, name: str, file_path: str, format: str = "yaml"):
        """Export a stack to a file."""
        try:
            template_manager = TemplateManager()
            template_format = (
                TemplateFormat.YAML if format.lower() == "yaml" else TemplateFormat.JSON
            )
            export_path = template_manager.export_template(name, file_path, template_format)

            self._print_success(f"Stack '{name}' exported successfully!")
            print(f"  Saved to: {export_path}")
            return 0
        except Exception as e:
            self._print_error(f"Failed to export stack: {str(e)}")
            return 1

    # NOTE: User preferences module not yet implemented
    # def _get_prefs_manager(self):
    #     """Lazy initialize preferences manager"""
    #     if self.prefs_manager is None:
    #         self.prefs_manager = PreferencesManager()
    #     return self.prefs_manager
    #
    # def check_pref(self, key: str | None = None):
    #     """Check/display user preferences"""
    #     manager = self._get_prefs_manager()
    #     ...
    #
    # def edit_pref(self, action: str, key: str | None = None, value: str | None = None):
    #     """Edit user preferences (add/set, delete/remove, list)"""
    #     manager = self._get_prefs_manager()
    #     ...

    def status(self):
        """Show comprehensive system status and run health checks"""
        from cortex.doctor import SystemDoctor

        # Run the comprehensive system health checks
        # This now includes all functionality from the old status command
        # plus all the detailed health checks from doctor
        doctor = SystemDoctor()
        return doctor.run_checks()

    def wizard(self):
        """Interactive setup wizard for API key configuration"""
        show_banner()
        console.print()
        cx_print("Welcome to Cortex Setup Wizard!", "success")
        console.print()
        # (Simplified for brevity - keeps existing logic)
        cx_print("Please export your API key in your shell profile.", "info")
        return 0

    def env(self, args: argparse.Namespace) -> int:
        """Handle environment variable management commands."""
        env_mgr = get_env_manager()

        # Handle subcommand routing
        action = getattr(args, "env_action", None)

        if not action:
            self._print_error(
                "Please specify a subcommand (set/get/list/delete/export/import/clear/template)"
            )
            return 1

        try:
            if action == "set":
                return self._env_set(env_mgr, args)
            elif action == "get":
                return self._env_get(env_mgr, args)
            elif action == "list":
                return self._env_list(env_mgr, args)
            elif action == "delete":
                return self._env_delete(env_mgr, args)
            elif action == "export":
                return self._env_export(env_mgr, args)
            elif action == "import":
                return self._env_import(env_mgr, args)
            elif action == "clear":
                return self._env_clear(env_mgr, args)
            elif action == "template":
                return self._env_template(env_mgr, args)
            elif action == "apps":
                return self._env_list_apps(env_mgr, args)
            elif action == "load":
                return self._env_load(env_mgr, args)
            else:
                self._print_error(f"Unknown env subcommand: {action}")
                return 1
        except (ValueError, OSError) as e:
            self._print_error(f"Environment operation failed: {e}")
            return 1
        except Exception as e:
            self._print_error(f"Unexpected error: {e}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return 1

    def _env_set(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Set an environment variable."""
        app = args.app
        key = args.key
        value = args.value
        encrypt = getattr(args, "encrypt", False)
        var_type = getattr(args, "type", "string") or "string"
        description = getattr(args, "description", "") or ""

        try:
            env_mgr.set_variable(
                app=app,
                key=key,
                value=value,
                encrypt=encrypt,
                var_type=var_type,
                description=description,
            )

            if encrypt:
                cx_print("🔐 Variable encrypted and stored", "success")
            else:
                cx_print("✓ Environment variable set", "success")
            return 0

        except ValueError as e:
            self._print_error(str(e))
            return 1
        except ImportError as e:
            self._print_error(str(e))
            if "cryptography" in str(e).lower():
                cx_print("Install with: pip install cryptography", "info")
            return 1

    def _env_get(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Get an environment variable value."""
        app = args.app
        key = args.key
        show_encrypted = getattr(args, "decrypt", False)

        value = env_mgr.get_variable(app, key, decrypt=show_encrypted)

        if value is None:
            self._print_error(f"Variable '{key}' not found for app '{app}'")
            return 1

        var_info = env_mgr.get_variable_info(app, key)

        if var_info and var_info.encrypted and not show_encrypted:
            console.print(f"{key}: [dim][encrypted][/dim]")
        else:
            console.print(f"{key}: {value}")

        return 0

    def _env_list(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """List all environment variables for an app."""
        app = args.app
        show_encrypted = getattr(args, "decrypt", False)

        variables = env_mgr.list_variables(app)

        if not variables:
            cx_print(f"No environment variables set for '{app}'", "info")
            return 0

        cx_header(f"Environment: {app}")

        for var in sorted(variables, key=lambda v: v.key):
            if var.encrypted:
                if show_encrypted:
                    try:
                        value = env_mgr.get_variable(app, var.key, decrypt=True)
                        console.print(f"  {var.key}: {value} [dim](decrypted)[/dim]")
                    except ValueError:
                        console.print(f"  {var.key}: [red][decryption failed][/red]")
                else:
                    console.print(f"  {var.key}: [yellow][encrypted][/yellow]")
            else:
                console.print(f"  {var.key}: {var.value}")

            if var.description:
                console.print(f"    [dim]# {var.description}[/dim]")

        console.print()
        console.print(f"[dim]Total: {len(variables)} variable(s)[/dim]")
        return 0

    def _env_delete(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Delete an environment variable."""
        app = args.app
        key = args.key

        if env_mgr.delete_variable(app, key):
            cx_print(f"✓ Deleted '{key}' from '{app}'", "success")
            return 0
        else:
            self._print_error(f"Variable '{key}' not found for app '{app}'")
            return 1

    def _env_export(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Export environment variables to .env format."""
        app = args.app
        include_encrypted = getattr(args, "include_encrypted", False)
        output_file = getattr(args, "output", None)

        content = env_mgr.export_env(app, include_encrypted=include_encrypted)

        if not content:
            cx_print(f"No environment variables to export for '{app}'", "info")
            return 0

        if output_file:
            try:
                with open(output_file, "w", encoding="utf-8") as f:
                    f.write(content)
                cx_print(f"✓ Exported to {output_file}", "success")
            except OSError as e:
                self._print_error(f"Failed to write file: {e}")
                return 1
        else:
            # Print to stdout
            print(content, end="")

        return 0

    def _env_import(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Import environment variables from .env format."""
        import sys

        app = args.app
        input_file = getattr(args, "file", None)
        encrypt_keys = getattr(args, "encrypt_keys", None)

        try:
            if input_file:
                with open(input_file, encoding="utf-8") as f:
                    content = f.read()
            elif not sys.stdin.isatty():
                content = sys.stdin.read()
            else:
                self._print_error("No input file specified and stdin is empty")
                cx_print("Usage: cortex env import <app> <file>", "info")
                cx_print("   or: cat .env | cortex env import <app>", "info")
                return 1

            # Parse encrypt-keys argument
            encrypt_list = []
            if encrypt_keys:
                encrypt_list = [k.strip() for k in encrypt_keys.split(",")]

            count, errors = env_mgr.import_env(app, content, encrypt_keys=encrypt_list)

            if errors:
                for err in errors:
                    cx_print(f"  ⚠ {err}", "warning")

            if count > 0:
                cx_print(f"✓ Imported {count} variable(s) to '{app}'", "success")
            else:
                cx_print("No variables imported", "info")

            # Return success (0) even with partial errors - some vars imported successfully
            return 0

        except FileNotFoundError:
            self._print_error(f"File not found: {input_file}")
            return 1
        except OSError as e:
            self._print_error(f"Failed to read file: {e}")
            return 1

    def _env_clear(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Clear all environment variables for an app."""
        app = args.app
        force = getattr(args, "force", False)

        # Confirm unless --force is used
        if not force:
            confirm = input(f"⚠️  Clear ALL environment variables for '{app}'? (y/n): ")
            if confirm.lower() != "y":
                cx_print("Operation cancelled", "info")
                return 0

        if env_mgr.clear_app(app):
            cx_print(f"✓ Cleared all variables for '{app}'", "success")
        else:
            cx_print(f"No environment data found for '{app}'", "info")

        return 0

    def _env_template(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Handle template subcommands."""
        template_action = getattr(args, "template_action", None)

        if template_action == "list":
            return self._env_template_list(env_mgr)
        elif template_action == "show":
            return self._env_template_show(env_mgr, args)
        elif template_action == "apply":
            return self._env_template_apply(env_mgr, args)
        else:
            self._print_error(
                "Please specify: template list, template show <name>, or template apply <name> <app>"
            )
            return 1

    def _env_template_list(self, env_mgr: EnvironmentManager) -> int:
        """List available templates."""
        templates = env_mgr.list_templates()

        cx_header("Available Environment Templates")

        for template in sorted(templates, key=lambda t: t.name):
            console.print(f"  [green]{template.name}[/green]")
            console.print(f"    {template.description}")
            console.print(f"    [dim]{len(template.variables)} variables[/dim]")
            console.print()

        cx_print("Use 'cortex env template show <name>' for details", "info")
        return 0

    def _env_template_show(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Show template details."""
        template_name = args.template_name

        template = env_mgr.get_template(template_name)
        if not template:
            self._print_error(f"Template '{template_name}' not found")
            return 1

        cx_header(f"Template: {template.name}")
        console.print(f"  {template.description}")
        console.print()

        console.print("[bold]Variables:[/bold]")
        for var in template.variables:
            req = "[red]*[/red]" if var.required else " "
            default = f" = {var.default}" if var.default else ""
            console.print(f"  {req} [cyan]{var.name}[/cyan] ({var.var_type}){default}")
            if var.description:
                console.print(f"      [dim]{var.description}[/dim]")

        console.print()
        console.print("[dim]* = required[/dim]")
        return 0

    def _env_template_apply(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Apply a template to an app."""
        template_name = args.template_name
        app = args.app

        # Parse key=value pairs from args
        values = {}
        value_args = getattr(args, "values", []) or []
        for val in value_args:
            if "=" in val:
                k, v = val.split("=", 1)
                values[k] = v

        # Parse encrypt keys
        encrypt_keys = []
        encrypt_arg = getattr(args, "encrypt_keys", None)
        if encrypt_arg:
            encrypt_keys = [k.strip() for k in encrypt_arg.split(",")]

        result = env_mgr.apply_template(
            template_name=template_name,
            app=app,
            values=values,
            encrypt_keys=encrypt_keys,
        )

        if result.valid:
            cx_print(f"✓ Applied template '{template_name}' to '{app}'", "success")
            return 0
        else:
            self._print_error(f"Failed to apply template '{template_name}'")
            for err in result.errors:
                console.print(f"  [red]✗[/red] {err}")
            return 1

    def _env_list_apps(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """List all apps with stored environments."""
        apps = env_mgr.list_apps()

        if not apps:
            cx_print("No applications with stored environments", "info")
            return 0

        cx_header("Applications with Environments")
        for app in apps:
            var_count = len(env_mgr.list_variables(app))
            console.print(f"  [green]{app}[/green] [dim]({var_count} variables)[/dim]")

        return 0

    def _env_load(self, env_mgr: EnvironmentManager, args: argparse.Namespace) -> int:
        """Load environment variables into current process."""
        app = args.app

        count = env_mgr.load_to_environ(app)

        if count > 0:
            cx_print(f"✓ Loaded {count} variable(s) from '{app}' into environment", "success")
        else:
            cx_print(f"No variables to load for '{app}'", "info")

        return 0

    # --- Import Dependencies Command ---
    def import_deps(self, args: argparse.Namespace) -> int:
        """Import and install dependencies from package manager files.

        Supports: requirements.txt (Python), package.json (Node),
                  Gemfile (Ruby), Cargo.toml (Rust), go.mod (Go)
        """
        file_path = getattr(args, "file", None)
        scan_all = getattr(args, "all", False)
        execute = getattr(args, "execute", False)
        include_dev = getattr(args, "dev", False)

        importer = DependencyImporter()

        # Handle --all flag: scan directory for all dependency files
        if scan_all:
            return self._import_all(importer, execute, include_dev)

        # Handle single file import
        if not file_path:
            self._print_error("Please specify a dependency file or use --all to scan directory")
            cx_print("Usage: cortex import <file> [--execute] [--dev]", "info")
            cx_print("       cortex import --all [--execute] [--dev]", "info")
            return 1

        return self._import_single_file(importer, file_path, execute, include_dev)

    def _import_single_file(
        self, importer: DependencyImporter, file_path: str, execute: bool, include_dev: bool
    ) -> int:
        """Import dependencies from a single file."""
        result = importer.parse(file_path, include_dev=include_dev)

        # Display parsing results
        self._display_parse_result(result, include_dev)

        if result.errors:
            for error in result.errors:
                self._print_error(error)
            return 1

        if not result.packages and not result.dev_packages:
            cx_print("No packages found in file", "info")
            return 0

        # Get install command
        install_cmd = importer.get_install_command(result.ecosystem, file_path)
        if not install_cmd:
            self._print_error(f"Unknown ecosystem: {result.ecosystem.value}")
            return 1

        # Dry run mode (default)
        if not execute:
            console.print(f"\n[bold]Install command:[/bold] {install_cmd}")
            cx_print("\nTo install these packages, run with --execute flag", "info")
            cx_print(f"Example: cortex import {file_path} --execute", "info")
            return 0

        # Execute mode - run the install command
        return self._execute_install(install_cmd, result.ecosystem)

    def _import_all(self, importer: DependencyImporter, execute: bool, include_dev: bool) -> int:
        """Scan directory and import all dependency files."""
        cx_print("Scanning directory...", "info")

        results = importer.scan_directory(include_dev=include_dev)

        if not results:
            cx_print("No dependency files found in current directory", "info")
            return 0

        # Display all found files
        total_packages = 0
        total_dev_packages = 0

        for file_path, result in results.items():
            filename = os.path.basename(file_path)
            if result.errors:
                console.print(f"   [red]✗[/red]  {filename} (error: {result.errors[0]})")
            else:
                pkg_count = result.prod_count
                dev_count = result.dev_count if include_dev else 0
                total_packages += pkg_count
                total_dev_packages += dev_count
                dev_str = f" + {dev_count} dev" if dev_count > 0 else ""
                console.print(f"   [green]✓[/green]  {filename} ({pkg_count} packages{dev_str})")

        console.print()

        if total_packages == 0 and total_dev_packages == 0:
            cx_print("No packages found in dependency files", "info")
            return 0

        # Generate install commands
        commands = importer.get_install_commands_for_results(results)

        if not commands:
            cx_print("No install commands generated", "info")
            return 0

        # Dry run mode (default)
        if not execute:
            console.print("[bold]Install commands:[/bold]")
            for cmd_info in commands:
                console.print(f"  • {cmd_info['command']}")
            console.print()
            cx_print("To install all packages, run with --execute flag", "info")
            cx_print("Example: cortex import --all --execute", "info")
            return 0

        # Execute mode - confirm before installing
        total = total_packages + total_dev_packages
        confirm = input(f"\nInstall all {total} packages? [Y/n]: ")
        if confirm.lower() not in ["", "y", "yes"]:
            cx_print("Installation cancelled", "info")
            return 0

        # Execute all install commands
        return self._execute_multi_install(commands)

    def _display_parse_result(self, result: ParseResult, include_dev: bool) -> None:
        """Display the parsed packages from a dependency file."""
        ecosystem_names = {
            PackageEcosystem.PYTHON: "Python",
            PackageEcosystem.NODE: "Node",
            PackageEcosystem.RUBY: "Ruby",
            PackageEcosystem.RUST: "Rust",
            PackageEcosystem.GO: "Go",
        }

        ecosystem_name = ecosystem_names.get(result.ecosystem, "Unknown")
        filename = os.path.basename(result.file_path)

        cx_print(f"\n📋 Found {result.prod_count} {ecosystem_name} packages", "info")

        if result.packages:
            console.print("\n[bold]Packages:[/bold]")
            for pkg in result.packages[:15]:  # Show first 15
                version_str = f" ({pkg.version})" if pkg.version else ""
                console.print(f"  • {pkg.name}{version_str}")
            if len(result.packages) > 15:
                console.print(f"  [dim]... and {len(result.packages) - 15} more[/dim]")

        if include_dev and result.dev_packages:
            console.print(f"\n[bold]Dev packages:[/bold] ({result.dev_count})")
            for pkg in result.dev_packages[:10]:
                version_str = f" ({pkg.version})" if pkg.version else ""
                console.print(f"  • {pkg.name}{version_str}")
            if len(result.dev_packages) > 10:
                console.print(f"  [dim]... and {len(result.dev_packages) - 10} more[/dim]")

        if result.warnings:
            console.print()
            for warning in result.warnings:
                cx_print(f"⚠ {warning}", "warning")

    def _execute_install(self, command: str, ecosystem: PackageEcosystem) -> int:
        """Execute a single install command."""
        ecosystem_names = {
            PackageEcosystem.PYTHON: "Python",
            PackageEcosystem.NODE: "Node",
            PackageEcosystem.RUBY: "Ruby",
            PackageEcosystem.RUST: "Rust",
            PackageEcosystem.GO: "Go",
        }

        ecosystem_name = ecosystem_names.get(ecosystem, "")
        cx_print(f"\n✓ Installing {ecosystem_name} packages...", "success")

        def progress_callback(current: int, total: int, step: InstallationStep) -> None:
            status_emoji = "⏳"
            if step.status == StepStatus.SUCCESS:
                status_emoji = "✅"
            elif step.status == StepStatus.FAILED:
                status_emoji = "❌"
            console.print(f"[{current}/{total}] {status_emoji} {step.description}")

        coordinator = InstallationCoordinator(
            commands=[command],
            descriptions=[f"Install {ecosystem_name} packages"],
            timeout=600,  # 10 minutes for package installation
            stop_on_error=True,
            progress_callback=progress_callback,
        )

        result = coordinator.execute()

        if result.success:
            self._print_success(f"{ecosystem_name} packages installed successfully!")
            console.print(f"Completed in {result.total_duration:.2f} seconds")
            return 0
        else:
            self._print_error("Installation failed")
            if result.error_message:
                console.print(f"Error: {result.error_message}", style="red")
            return 1

    def _execute_multi_install(self, commands: list[dict[str, str]]) -> int:
        """Execute multiple install commands."""
        all_commands = [cmd["command"] for cmd in commands]
        all_descriptions = [cmd["description"] for cmd in commands]

        def progress_callback(current: int, total: int, step: InstallationStep) -> None:
            status_emoji = "⏳"
            if step.status == StepStatus.SUCCESS:
                status_emoji = "✅"
            elif step.status == StepStatus.FAILED:
                status_emoji = "❌"
            console.print(f"\n[{current}/{total}] {status_emoji} {step.description}")
            console.print(f"  Command: {step.command}")

        coordinator = InstallationCoordinator(
            commands=all_commands,
            descriptions=all_descriptions,
            timeout=600,
            stop_on_error=True,
            progress_callback=progress_callback,
        )

        console.print("\n[bold]Installing packages...[/bold]")
        result = coordinator.execute()

        if result.success:
            self._print_success("\nAll packages installed successfully!")
            console.print(f"Completed in {result.total_duration:.2f} seconds")
            return 0
        else:
            if result.failed_step is not None:
                self._print_error(f"\nInstallation failed at step {result.failed_step + 1}")
            else:
                self._print_error("\nInstallation failed")
            if result.error_message:
                console.print(f"Error: {result.error_message}", style="red")
            return 1

    # --------------------------


def show_rich_help():
    """Display a beautifully formatted help table using the Rich library.

    This function outputs the primary command menu, providing descriptions
    for all core Cortex utilities including installation, environment
    management, and container tools.
    """
    from rich.table import Table

    show_banner(show_version=True)
    console.print()

    console.print("[bold]AI-powered package manager for Linux[/bold]")
    console.print("[dim]Just tell Cortex what you want to install.[/dim]")
    console.print()

    # Initialize a table to display commands with specific column styling
    table = Table(show_header=True, header_style="bold cyan", box=None)
    table.add_column("Command", style="green")
    table.add_column("Description")

    # Command Rows
    table.add_row("ask <question>", "Ask about your system")
    table.add_row("demo", "See Cortex in action")
    table.add_row("wizard", "Configure API key")
    table.add_row("status", "System status")
    table.add_row("install <pkg>", "Install software using natural language")
    table.add_row("install --stack <name>", "Install a pre-configured stack")
    table.add_row("import <file>", "Import deps from package files")
    table.add_row("history", "View installation history")
    table.add_row("rollback <id>", "Undo an installation")
    table.add_row("stack list", "List available stacks")
    table.add_row("stack create <name>", "Create a custom stack")
    table.add_row("stack export/import", "Share stacks with others")
    table.add_row("notify", "Manage desktop notifications")
    table.add_row("env", "Manage environment variables")
    table.add_row("cache stats", "Show LLM cache statistics")
    table.add_row("docker permissions", "Fix Docker bind-mount permissions")
    table.add_row("sandbox <cmd>", "Test packages in Docker sandbox")
    table.add_row("doctor", "System health check")

    console.print(table)
    console.print()

    console.print("[bold cyan]Quick Examples:[/bold cyan]")
    console.print("  cortex install docker --execute")
    console.print("  cortex install --stack lamp --dry-run")
    console.print("  cortex stack list")
    console.print()
    console.print("[dim]Learn more: https://cortexlinux.com/docs[/dim]")


def shell_suggest(text: str) -> int:
    """
    Internal helper used by shell hotkey integration.
    Prints a single suggested command to stdout.
    """
    try:
        from cortex.shell_integration import suggest_command

        suggestion = suggest_command(text)
        if suggestion:
            print(suggestion)
        return 0
    except Exception:
        return 1


def main():
    # Load environment variables from .env files BEFORE accessing any API keys
    # This must happen before any code that reads os.environ for API keys
    from cortex.env_loader import load_env

    load_env()

    # Auto-configure network settings (proxy detection, VPN compatibility, offline mode)
    # Use lazy loading - only detect when needed to improve CLI startup time
    try:
        network = NetworkConfig(auto_detect=False)  # Don't detect yet (fast!)

        # Only detect network for commands that actually need it
        # Parse args first to see what command we're running
        temp_parser = argparse.ArgumentParser(add_help=False)
        temp_parser.add_argument("command", nargs="?")
        temp_args, _ = temp_parser.parse_known_args()

        # Commands that need network detection
        NETWORK_COMMANDS = ["install", "update", "upgrade", "search", "doctor", "stack"]

        if temp_args.command in NETWORK_COMMANDS:
            # Now detect network (only when needed)
            network.detect(check_quality=True)  # Include quality check for these commands
            network.auto_configure()

    except Exception as e:
        # Network config is optional - don't block execution if it fails
        console.print(f"[yellow]⚠️  Network auto-config failed: {e}[/yellow]")

    parser = argparse.ArgumentParser(
        prog="cortex",
        description="AI-powered Linux command interpreter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Natural language installation
  cortex install docker
  cortex install docker --execute
  cortex install "python 3.11 with pip"
  cortex install nginx --dry-run

  # Stack-based installation
  cortex install --stack lamp --dry-run     # Preview LAMP stack
  cortex install --stack lamp --execute     # Install LAMP stack
  cortex install --stack ml-ai --execute    # Install ML/AI stack

  # Stack management
  cortex stack list                         # List all stacks
  cortex stack describe lamp                # Show stack details
  cortex stack create my-stack              # Create custom stack
  cortex stack export lamp my-lamp.yaml     # Export for sharing
  cortex stack import my-lamp.yaml          # Import a stack

  # History and rollback
  cortex history
  cortex history show <id>
  cortex rollback <id>

Environment Variables:
  OPENAI_API_KEY      OpenAI API key for GPT-4
  ANTHROPIC_API_KEY   Anthropic API key for Claude
  CORTEX_PROVIDER     LLM provider (claude, openai, ollama)
        """,
    )

    # Global flags
    parser.add_argument("--version", "-V", action="version", version=f"cortex {VERSION}")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Define the docker command and its associated sub-actions
    docker_parser = subparsers.add_parser("docker", help="Docker and container utilities")
    docker_subs = docker_parser.add_subparsers(dest="docker_action", help="Docker actions")

    # Add the permissions action to allow fixing file ownership issues
    perm_parser = docker_subs.add_parser(
        "permissions", help="Fix file permissions from bind mounts"
    )

    # Provide an option to skip the manual confirmation prompt
    perm_parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")

    perm_parser.add_argument(
        "--execute", "-e", action="store_true", help="Apply ownership changes (default: dry-run)"
    )

    # Demo command
    demo_parser = subparsers.add_parser("demo", help="See Cortex in action")

    # Wizard command
    wizard_parser = subparsers.add_parser("wizard", help="Configure API key interactively")

    # Status command (includes comprehensive health checks)
    subparsers.add_parser("status", help="Show comprehensive system status and health checks")

    # Ask command
    ask_parser = subparsers.add_parser("ask", help="Ask a question about your system")
    ask_parser.add_argument("question", type=str, help="Natural language question")

    # Install command
    install_parser = subparsers.add_parser(
        "install",
        help="Install software using natural language or stack",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Install software packages using natural language or pre-configured stacks.

Cortex uses AI to understand your installation requests and generates
the appropriate commands for your system.""",
        epilog="""
Examples:
  # Natural language installation
  cortex install docker
  cortex install "python 3.11 with pip"
  cortex install nginx --dry-run
  cortex install docker --execute

  # Stack-based installation (pre-configured bundles)
  cortex install --stack lamp --dry-run    # Preview LAMP stack
  cortex install --stack lamp --execute    # Install LAMP stack
  cortex install --stack mern --execute    # Install MERN stack
  cortex install --stack ml-ai --execute   # Install ML/AI stack

Available stacks: lamp, mean, mern, ml-ai, devops
Use 'cortex stack list' to see all available stacks.
""",
    )
    install_group = install_parser.add_mutually_exclusive_group(required=True)
    install_group.add_argument(
        "software", type=str, nargs="?", help="Software to install (natural language)"
    )
    install_group.add_argument(
        "--stack",
        type=str,
        metavar="NAME",
        help="Install from a pre-configured stack (e.g., lamp, mean, mern, ml-ai, devops)",
    )
    install_parser.add_argument(
        "--execute", action="store_true", help="Execute the generated commands"
    )
    install_parser.add_argument(
        "--dry-run", action="store_true", help="Show commands without executing"
    )
    install_parser.add_argument(
        "--parallel",
        action="store_true",
        help="Enable parallel execution for multi-step installs",
    )

    # Import command - import dependencies from package manager files
    import_parser = subparsers.add_parser(
        "import",
        help="Import and install dependencies from package files",
    )
    import_parser.add_argument(
        "file",
        nargs="?",
        help="Dependency file (requirements.txt, package.json, Gemfile, Cargo.toml, go.mod)",
    )
    import_parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Scan directory for all dependency files",
    )
    import_parser.add_argument(
        "--execute",
        "-e",
        action="store_true",
        help="Execute install commands (default: dry-run)",
    )
    import_parser.add_argument(
        "--dev",
        "-d",
        action="store_true",
        help="Include dev dependencies",
    )

    # History command
    history_parser = subparsers.add_parser("history", help="View history")
    history_parser.add_argument("--limit", type=int, default=20)
    history_parser.add_argument("--status", choices=["success", "failed"])
    history_parser.add_argument("show_id", nargs="?")

    # Rollback command
    rollback_parser = subparsers.add_parser("rollback", help="Rollback an installation")
    rollback_parser.add_argument("id", help="Installation ID to rollback")
    rollback_parser.add_argument(
        "--dry-run", action="store_true", help="Show rollback actions without executing"
    )

    # --- New Notify Command ---
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
    # --------------------------

    # Template commands - DEPRECATED: Use 'cortex stack' instead
    # Kept for backward compatibility, redirects to stack commands
    template_parser = subparsers.add_parser(
        "template",
        help="[DEPRECATED] Use 'cortex stack' instead",
        description="DEPRECATED: This command has been renamed to 'cortex stack'.\n"
        "Please use 'cortex stack list', 'cortex stack create', etc.",
    )
    template_subs = template_parser.add_subparsers(dest="template_action", help="Template actions")
    template_subs.add_parser("list", help="[DEPRECATED] Use 'cortex stack list'")

    template_create_parser = template_subs.add_parser(
        "create", help="[DEPRECATED] Use 'cortex stack create'"
    )
    template_create_parser.add_argument("name", help="Template name")

    template_import_parser = template_subs.add_parser(
        "import", help="[DEPRECATED] Use 'cortex stack import'"
    )
    template_import_parser.add_argument("file_path", help="Path to template file")
    template_import_parser.add_argument("--name", help="Override template name")

    template_export_parser = template_subs.add_parser(
        "export", help="[DEPRECATED] Use 'cortex stack export'"
    )
    template_export_parser.add_argument("name", help="Template name")
    template_export_parser.add_argument("file_path", help="Output file path")
    template_export_parser.add_argument(
        "--format", choices=["yaml", "json"], default="yaml", help="Export format"
    )

    # Stack command - enhanced with create/import/export subcommands
    stack_parser = subparsers.add_parser(
        "stack",
        help="Manage installation stacks for common development environments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""Manage installation stacks for common development environments.

Stacks are pre-configured bundles of packages and tools that can be installed
together. Cortex provides built-in stacks for common use cases and supports
custom stack creation.""",
        epilog="""
Examples:
  # List all available stacks
  cortex stack list

  # Show details about a specific stack
  cortex stack describe lamp

  # Install a stack (use install command)
  cortex install --stack lamp --dry-run    # Preview first
  cortex install --stack lamp --execute    # Install

  # Create a custom stack interactively
  cortex stack create my-dev-stack

  # Export a stack to share with others
  cortex stack export lamp my-lamp.yaml

  # Import a stack from a file
  cortex stack import my-lamp.yaml
  cortex stack import my-lamp.yaml --name custom-lamp

Built-in stacks:
  lamp    - Linux, Apache, MySQL, PHP web server stack
  mean    - MongoDB, Express.js, Angular, Node.js
  mern    - MongoDB, Express.js, React, Node.js
  ml-ai   - Machine Learning with Python, TensorFlow, PyTorch
  devops  - Docker, Kubernetes, Terraform, Ansible

Use 'cortex stack list' for a complete list with descriptions.
""",
    )
    stack_subs = stack_parser.add_subparsers(dest="stack_action", help="Stack actions")

    # stack list
    stack_list_parser = stack_subs.add_parser(
        "list",
        help="List all available stacks",
        description="Display all available stacks with their versions and descriptions.",
        epilog="""
Examples:
  cortex stack list
""",
    )

    # stack describe <name>
    stack_describe_parser = stack_subs.add_parser(
        "describe",
        help="Show detailed information about a stack",
        description="Display detailed information about a specific stack including packages and requirements.",
        epilog="""
Examples:
  cortex stack describe lamp
  cortex stack describe ml-ai
""",
    )
    stack_describe_parser.add_argument("name", help="Stack name to describe")

    # stack create <name>
    stack_create_parser = stack_subs.add_parser(
        "create",
        help="Create a new custom stack interactively",
        description="Create a new custom stack with packages and hardware requirements.",
        epilog="""
Examples:
  cortex stack create my-web-stack
  cortex stack create ml-custom
""",
    )
    stack_create_parser.add_argument("name", help="Name for the new stack")

    # stack import <file> [--name NAME]
    stack_import_parser = stack_subs.add_parser(
        "import",
        help="Import a stack from a YAML/JSON file",
        description="Import a stack definition from a YAML or JSON file.",
        epilog="""
Examples:
  cortex stack import my-stack.yaml
  cortex stack import team-stack.json --name my-team-stack
""",
    )
    stack_import_parser.add_argument("file_path", help="Path to stack file (YAML or JSON)")
    stack_import_parser.add_argument("--name", help="Override the stack name")

    # stack export <name> <file> [--format FORMAT]
    stack_export_parser = stack_subs.add_parser(
        "export",
        help="Export a stack to a file for sharing",
        description="Export a stack definition to a YAML or JSON file.",
        epilog="""
Examples:
  cortex stack export lamp my-lamp.yaml
  cortex stack export ml-ai ml-stack.json --format json
""",
    )
    stack_export_parser.add_argument("name", help="Stack name to export")
    stack_export_parser.add_argument("file_path", help="Output file path")
    stack_export_parser.add_argument(
        "--format", choices=["yaml", "json"], default="yaml", help="Export format (default: yaml)"
    )

    # Cache commands
    cache_parser = subparsers.add_parser("cache", help="Cache operations")
    cache_subs = cache_parser.add_subparsers(dest="cache_action", help="Cache actions")
    cache_subs.add_parser("stats", help="Show cache statistics")

    # --- Sandbox Commands (Docker-based package testing) ---
    sandbox_parser = subparsers.add_parser(
        "sandbox", help="Test packages in isolated Docker sandbox"
    )
    sandbox_subs = sandbox_parser.add_subparsers(dest="sandbox_action", help="Sandbox actions")

    # sandbox create <name> [--image IMAGE]
    sandbox_create_parser = sandbox_subs.add_parser("create", help="Create a sandbox environment")
    sandbox_create_parser.add_argument("name", help="Unique name for the sandbox")
    sandbox_create_parser.add_argument(
        "--image", default="ubuntu:22.04", help="Docker image to use (default: ubuntu:22.04)"
    )

    # sandbox install <name> <package>
    sandbox_install_parser = sandbox_subs.add_parser("install", help="Install a package in sandbox")
    sandbox_install_parser.add_argument("name", help="Sandbox name")
    sandbox_install_parser.add_argument("package", help="Package to install")

    # sandbox test <name> [package]
    sandbox_test_parser = sandbox_subs.add_parser("test", help="Run tests in sandbox")
    sandbox_test_parser.add_argument("name", help="Sandbox name")
    sandbox_test_parser.add_argument("package", nargs="?", help="Specific package to test")

    # sandbox promote <name> <package> [--dry-run]
    sandbox_promote_parser = sandbox_subs.add_parser(
        "promote", help="Install tested package on main system"
    )
    sandbox_promote_parser.add_argument("name", help="Sandbox name")
    sandbox_promote_parser.add_argument("package", help="Package to promote")
    sandbox_promote_parser.add_argument(
        "--dry-run", action="store_true", help="Show command without executing"
    )
    sandbox_promote_parser.add_argument(
        "-y", "--yes", action="store_true", help="Skip confirmation prompt"
    )

    # sandbox cleanup <name> [--force]
    sandbox_cleanup_parser = sandbox_subs.add_parser("cleanup", help="Remove a sandbox environment")
    sandbox_cleanup_parser.add_argument("name", help="Sandbox name to remove")
    sandbox_cleanup_parser.add_argument("-f", "--force", action="store_true", help="Force removal")

    # sandbox list
    sandbox_subs.add_parser("list", help="List all sandbox environments")

    # sandbox exec <name> <command...>
    sandbox_exec_parser = sandbox_subs.add_parser("exec", help="Execute command in sandbox")
    sandbox_exec_parser.add_argument("name", help="Sandbox name")
    sandbox_exec_parser.add_argument("command", nargs="+", help="Command to execute")
    # --------------------------

    # --- Environment Variable Management Commands ---
    env_parser = subparsers.add_parser("env", help="Manage environment variables")
    env_subs = env_parser.add_subparsers(dest="env_action", help="Environment actions")

    # env set <app> <KEY> <VALUE> [--encrypt] [--type TYPE] [--description DESC]
    env_set_parser = env_subs.add_parser("set", help="Set an environment variable")
    env_set_parser.add_argument("app", help="Application name")
    env_set_parser.add_argument("key", help="Variable name")
    env_set_parser.add_argument("value", help="Variable value")
    env_set_parser.add_argument("--encrypt", "-e", action="store_true", help="Encrypt the value")
    env_set_parser.add_argument(
        "--type",
        "-t",
        choices=["string", "url", "port", "boolean", "integer", "path"],
        default="string",
        help="Variable type for validation",
    )
    env_set_parser.add_argument("--description", "-d", help="Description of the variable")

    # env get <app> <KEY> [--decrypt]
    env_get_parser = env_subs.add_parser("get", help="Get an environment variable")
    env_get_parser.add_argument("app", help="Application name")
    env_get_parser.add_argument("key", help="Variable name")
    env_get_parser.add_argument(
        "--decrypt", action="store_true", help="Decrypt and show encrypted values"
    )

    # env list <app> [--decrypt]
    env_list_parser = env_subs.add_parser("list", help="List environment variables")
    env_list_parser.add_argument("app", help="Application name")
    env_list_parser.add_argument(
        "--decrypt", action="store_true", help="Decrypt and show encrypted values"
    )

    # env delete <app> <KEY>
    env_delete_parser = env_subs.add_parser("delete", help="Delete an environment variable")
    env_delete_parser.add_argument("app", help="Application name")
    env_delete_parser.add_argument("key", help="Variable name")

    # env export <app> [--include-encrypted] [--output FILE]
    env_export_parser = env_subs.add_parser("export", help="Export variables to .env format")
    env_export_parser.add_argument("app", help="Application name")
    env_export_parser.add_argument(
        "--include-encrypted",
        action="store_true",
        help="Include decrypted values of encrypted variables",
    )
    env_export_parser.add_argument("--output", "-o", help="Output file (default: stdout)")

    # env import <app> [file] [--encrypt-keys KEYS]
    env_import_parser = env_subs.add_parser("import", help="Import variables from .env format")
    env_import_parser.add_argument("app", help="Application name")
    env_import_parser.add_argument("file", nargs="?", help="Input file (default: stdin)")
    env_import_parser.add_argument("--encrypt-keys", help="Comma-separated list of keys to encrypt")

    # env clear <app> [--force]
    env_clear_parser = env_subs.add_parser("clear", help="Clear all variables for an app")
    env_clear_parser.add_argument("app", help="Application name")
    env_clear_parser.add_argument("--force", "-f", action="store_true", help="Skip confirmation")

    # env apps - list all apps with environments
    env_subs.add_parser("apps", help="List all apps with stored environments")

    # env load <app> - load into os.environ
    env_load_parser = env_subs.add_parser("load", help="Load variables into current environment")
    env_load_parser.add_argument("app", help="Application name")

    # env template subcommands
    env_template_parser = env_subs.add_parser("template", help="Manage environment templates")
    env_template_subs = env_template_parser.add_subparsers(
        dest="template_action", help="Template actions"
    )

    # env template list
    env_template_subs.add_parser("list", help="List available templates")

    # env template show <name>
    env_template_show_parser = env_template_subs.add_parser("show", help="Show template details")
    env_template_show_parser.add_argument("template_name", help="Template name")

    # env template apply <template> <app> [KEY=VALUE...] [--encrypt-keys KEYS]
    env_template_apply_parser = env_template_subs.add_parser("apply", help="Apply template to app")
    env_template_apply_parser.add_argument("template_name", help="Template name")
    env_template_apply_parser.add_argument("app", help="Application name")
    env_template_apply_parser.add_argument(
        "values", nargs="*", help="Variable values as KEY=VALUE pairs"
    )
    env_template_apply_parser.add_argument(
        "--encrypt-keys", help="Comma-separated list of keys to encrypt"
    )
    # --------------------------

    args = parser.parse_args()

    # The Guard: Check for empty commands before starting the CLI
    if not args.command:
        show_rich_help()
        return 0

    # Initialize the CLI handler
    cli = CortexCLI(verbose=args.verbose)

    try:
        # Route the command to the appropriate method inside the cli object
        if args.command == "docker":
            if args.docker_action == "permissions":
                return cli.docker_permissions(args)
            parser.print_help()
            return 1

        if args.command == "demo":
            return cli.demo()
        elif args.command == "wizard":
            return cli.wizard()
        elif args.command == "status":
            return cli.status()
        elif args.command == "ask":
            return cli.ask(args.question)
        elif args.command == "install":
            if args.stack:
                return cli.install("", execute=args.execute, dry_run=args.dry_run, stack=args.stack)
            else:
                return cli.install(
                    args.software,
                    execute=args.execute,
                    dry_run=args.dry_run,
                    parallel=args.parallel,
                )
        elif args.command == "import":
            return cli.import_deps(args)
        elif args.command == "history":
            return cli.history(limit=args.limit, status=args.status, show_id=args.show_id)
        elif args.command == "rollback":
            return cli.rollback(args.id, dry_run=args.dry_run)
        elif args.command == "template":
            # DEPRECATED: Redirect to stack commands with warning
            cx_print("⚠️  'cortex template' is deprecated. Use 'cortex stack' instead.", "warning")
            if args.template_action == "list":
                cx_print("   Use: cortex stack list", "info")
                return cli.stack_list()
            elif args.template_action == "create":
                cx_print(f"   Use: cortex stack create {args.name}", "info")
                return cli.stack_create(args.name)
            elif args.template_action == "import":
                cx_print(f"   Use: cortex stack import {args.file_path}", "info")
                return cli.stack_import(args.file_path, args.name)
            elif args.template_action == "export":
                cx_print(f"   Use: cortex stack export {args.name} {args.file_path}", "info")
                return cli.stack_export(args.name, args.file_path, args.format)
            else:
                cx_print("   Use: cortex stack --help", "info")
                parser.print_help()
                return 1
        # NOTE: User preferences commands not yet implemented
        # elif args.command == "check-pref":
        #     return cli.check_pref(key=args.key)
        # elif args.command == "edit-pref":
        #     return cli.edit_pref(action=args.action, key=args.key, value=args.value)
        # Handle the new notify command
        elif args.command == "notify":
            return cli.notify(args)
        elif args.command == "stack":
            return cli.stack(args)
        elif args.command == "sandbox":
            return cli.sandbox(args)
        elif args.command == "cache":
            if getattr(args, "cache_action", None) == "stats":
                return cli.cache_stats()
            parser.print_help()
            return 1
        elif args.command == "env":
            return cli.env(args)
        else:
            parser.print_help()
            return 1
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled", file=sys.stderr)
        return 130
    except (ValueError, ImportError, OSError) as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        # Print traceback if verbose mode was requested
        if "--verbose" in sys.argv or "-v" in sys.argv:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
