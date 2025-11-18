"""Command-line interface entry point for the Cortex automation toolkit."""

import argparse
import json
import os
import subprocess
import sys
import time
from typing import List, Optional
from getpass import getpass
from pathlib import Path

from LLM.interpreter import CommandInterpreter
from cortex.coordinator import InstallationCoordinator, StepStatus


class ProviderExecutionError(RuntimeError):
    """Raised when an API provider fails in a recoverable way."""


class CortexCLI:
    """Command-line interface for Cortex AI-powered software installation."""

    def __init__(self) -> None:
        """Initialise spinner state used for interactive progress updates."""
        self.spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.spinner_idx = 0

    # -----------------------
    # Credential persistence
    # -----------------------
    def _cred_path(self) -> Path:
        """Return the path to the user credentials file ("~/.cortex/credentials.json")."""
        base = Path.home() / ".cortex"
        base.mkdir(parents=True, exist_ok=True)
        return base / "credentials.json"

    def _load_creds(self) -> dict:
        """Load persisted credentials if present; return an empty dict on first use."""
        try:
            p = self._cred_path()
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_api_key(self, provider: str, key: str) -> None:
        """Persist API key for ``provider`` into the credentials file."""
        data = self._load_creds()
        data.setdefault("providers", {})[provider] = {"api_key": key}
        self._cred_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
        self._print_success(f"Saved {provider} API key to ~/.cortex/credentials.json")

    def _provider_priority(self) -> List[str]:
        """Return providers in the order we auto-select them when no override is given."""
        return ['groq', 'openai', 'claude', 'kimi', 'fake']

    def _get_provider(self) -> str:
        """Detect which LLM provider to use based on configuration and credentials."""
        provider_override = os.environ.get('CORTEX_PROVIDER')
        if provider_override:
            return provider_override.lower()

        for provider in self._provider_priority():
            if self._provider_has_credentials(provider):
                return provider

        return 'openai'

    def _env_var_for(self, provider: str) -> Optional[str]:
        """Return the environment variable name for the given provider."""
        return {
            'groq': 'GROQ_API_KEY',
            'openai': 'OPENAI_API_KEY',
            'claude': 'ANTHROPIC_API_KEY',
            'kimi': 'KIMI_API_KEY',
        }.get(provider)

    def _provider_has_credentials(self, provider: str) -> bool:
        """Return ``True`` if we can find credentials for the provider."""
        if provider == 'fake':
            return bool(os.environ.get('CORTEX_FAKE_COMMANDS'))

        env_var = self._env_var_for(provider)
        if env_var and os.environ.get(env_var):
            return True

        creds = self._load_creds().get('providers', {})
        return bool(creds.get(provider, {}).get('api_key'))

    def _provider_candidates(self, primary: str) -> List[str]:
        """Return a deduplicated provider attempt order for fallback handling."""
        ordered = [primary] + [p for p in self._provider_priority() if p != primary]
        candidates: List[str] = []
        for provider in ordered:
            if provider in candidates:
                continue
            if self._provider_has_credentials(provider):
                candidates.append(provider)

        if not candidates:
            candidates.append(primary)
        return candidates

    def _get_api_key(self, provider: str, silent: bool = False) -> Optional[str]:
        """Return the API key for the specified provider or emit guidance if missing.

        Order of resolution:
        1. Environment variables (session overrides)
        2. Persisted credentials in ``~/.cortex/credentials.json``
        """
        env_var = self._env_var_for(provider)
        if not env_var:
            return None

        api_key = os.environ.get(env_var)
        if api_key:
            return api_key

        # Fallback to persisted credentials
        creds = self._load_creds()
        key = creds.get("providers", {}).get(provider, {}).get("api_key")
        if key:
            return key

        if not silent:
            self._print_error(f"API key not found. Set {env_var} or run 'cortex --set-{provider}'.")
        return None

    def _print_status(self, label: str, message: str) -> None:
        """Emit informational output with a consistent status label."""
        print(f"{label} {message}")

    def _print_error(self, message: str) -> None:
        """Emit an error message to ``stderr`` with standard formatting."""
        print(f"[ERROR] {message}", file=sys.stderr)

    def _print_success(self, message: str) -> None:
        """Emit a success message to ``stdout`` with the success label."""
        print(f"[SUCCESS] {message}")

    def _animate_spinner(self, message: str) -> None:
        """Render a single spinner frame with the supplied ``message``."""
        sys.stdout.write(f"\r{self.spinner_chars[self.spinner_idx]} {message}")
        sys.stdout.flush()
        self.spinner_idx = (self.spinner_idx + 1) % len(self.spinner_chars)
        time.sleep(0.1)

    def _clear_line(self) -> None:
        """Clear the active terminal line to hide spinner artifacts."""
        sys.stdout.write('\r\033[K')
        sys.stdout.flush()

    def install(self, software: str, execute: bool = False, dry_run: bool = False) -> int:
        """Interpret a natural-language request and optionally execute the plan with fallback."""

        primary_provider = self._get_provider()
        candidates = self._provider_candidates(primary_provider)
        failure_messages: List[str] = []

        for index, provider in enumerate(candidates):
            is_fake = provider == 'fake'
            if is_fake:
                api_key = os.environ.get('CORTEX_FAKE_API_KEY', 'fake-api-key')
            else:
                api_key = self._get_api_key(provider, silent=index != 0)
                if not api_key:
                    failure_messages.append(f"{provider}: missing API key")
                    continue

            if provider != primary_provider:
                self._print_status("[INFO]", f"Switching to {provider} provider...")

            try:
                return self._install_with_provider(provider, api_key, software, execute, dry_run)
            except ProviderExecutionError as exc:
                failure_messages.append(f"{provider}: {str(exc)}")
                self._print_error(f"{provider} provider failed. Trying next option...")
                continue

        self._print_error("All configured providers failed. Please verify your API keys and try again.")
        if failure_messages:
            print("Details:", file=sys.stderr)
            for message in failure_messages:
                print(f"  - {message}", file=sys.stderr)
        return 1

    def _install_with_provider(
        self,
        provider: str,
        api_key: str,
        software: str,
        execute: bool,
        dry_run: bool,
    ) -> int:
        """Execute the install flow against a specific provider."""

        try:
            self._print_status("[INFO]", "Understanding request...")

            interpreter = CommandInterpreter(api_key=api_key, provider=provider)

            self._print_status("[PLAN]", "Planning installation...")

            for _ in range(10):
                self._animate_spinner("Analyzing system requirements...")
            self._clear_line()

            commands = interpreter.parse(f"install {software}")

            if not commands:
                self._print_error("No commands generated. Please try again with a different request.")
                return 1

            self._print_status("[EXEC]", f"Installing {software}...")
            print("\nGenerated commands:")
            for index, command in enumerate(commands, 1):
                print(f"  {index}. {command}")

            if dry_run:
                print("\n(Dry run mode - commands not executed)")
                return 0

            if execute:
                def progress_callback(current: int, total: int, step) -> None:
                    status_label = "[PENDING]"
                    if step.status == StepStatus.SUCCESS:
                        status_label = "[OK]"
                    elif step.status == StepStatus.FAILED:
                        status_label = "[FAIL]"
                    print(f"\n[{current}/{total}] {status_label} {step.description}")
                    print(f"  Command: {step.command}")

                print("\nExecuting commands...")

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
                    return 0

                if result.failed_step is not None:
                    self._print_error(f"Installation failed at step {result.failed_step + 1}")
                else:
                    self._print_error("Installation failed")
                if result.error_message:
                    print(f"  Error: {result.error_message}", file=sys.stderr)
                return 1

            print("\nTo execute these commands, run with --execute flag")
            print("Example: cortex install docker --execute")
            return 0

        except ValueError as exc:
            raise ProviderExecutionError(str(exc)) from exc
        except RuntimeError as exc:
            raise ProviderExecutionError(f"API call failed: {str(exc)}") from exc
        except Exception as exc:
            raise ProviderExecutionError(f"Unexpected error: {str(exc)}") from exc

    # -----------------------
    # Support commands
    # -----------------------
    def set_api_key(self, provider: str) -> int:
        """Prompt user for API key and persist it for the selected provider."""
        names = {
            'groq': 'Groq',
            'openai': 'OpenAI',
            'claude': 'Anthropic Claude',
            'kimi': 'Moonshot Kimi',
        }
        pretty = names.get(provider, provider.capitalize())
        print(f"Enter {pretty} API key (input hidden): ", end="", flush=True)
        key = getpass("")
        if not key:
            self._print_error("No key entered. Nothing changed.")
            return 1
        self._save_api_key(provider, key)
        # Also set in current process so it works immediately
        env_map = {
            'openai': 'OPENAI_API_KEY',
            'claude': 'ANTHROPIC_API_KEY',
            'kimi': 'KIMI_API_KEY',
            'openrouter': 'OPENROUTER_API_KEY',
        }
        env_var = env_map.get(provider)
        if env_var:
            os.environ[env_var] = key
        self._print_success(f"{pretty} key is now active in this session.")
        print("Tip: Run 'cortex --test-api' to verify connectivity.")
        return 0

    def test_api(self, provider: Optional[str] = None) -> int:
        """Validate API connectivity and provide simple, human-readable feedback."""
        import requests

        prov = provider or self._get_provider()
        if prov == 'fake':
            print("[WARN] No real provider configured. Set a key or use --test-fake.")
            return 1
        key = self._get_api_key(prov)
        if not key:
            return 1

        try:
            if prov == 'openai':
                url = 'https://api.openai.com/v1/models'
                headers = {"Authorization": f"Bearer {key}"}
            elif prov == 'claude':
                url = 'https://api.anthropic.com/v1/models'
                headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
            elif prov == 'kimi':
                base = os.environ.get('KIMI_API_BASE_URL', 'https://api.moonshot.cn')
                url = f"{base.rstrip('/')}/v1/models"
                headers = {"Authorization": f"Bearer {key}"}
            elif prov == 'groq':
                base = os.environ.get('GROQ_BASE_URL', 'https://api.groq.com/openai/v1')
                url = f"{base.rstrip('/')}/models"
                headers = {"Authorization": f"Bearer {key}"}
            else:
                self._print_error("Unknown provider for API test.")
                return 1

            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # Try to pull a few model ids if present
                ids = []
                if isinstance(data, dict) and isinstance(data.get('data'), list):
                    ids = [it.get('id') for it in data['data'] if isinstance(it, dict) and 'id' in it][:3]
                models = (", ".join([m for m in ids if m])) or "(model list available)"
                self._print_success(f"API connection OK ({prov}). Example models: {models}")
                return 0

            if resp.status_code in (401, 403):
                self._print_error("Invalid or unauthorized API key. Please re-check your key.")
                print("Hint: Reset it via 'cortex --set-gpt' / '--set-claude' / '--set-kimi'.")
                return 1
            if resp.status_code == 429:
                self._print_error("Rate limited. You might be out of credits or hitting limits.")
                print("Try again later or check your account usage.")
                return 1

            msg = resp.text.strip()
            self._print_error(f"Service returned {resp.status_code}. Details: {msg[:200]}")
            return 1

        except Exception as exc:
            self._print_error(f"Network check failed: {str(exc)}")
            print("Please verify your internet connection and firewall settings.")
            return 1

    def test_fake(self) -> int:
        """Run a tiny fake-provider demo with clear warnings for end users."""
        print("[WARN] Running in TEST MODE with a fake AI provider.")
        print("No real API keys are needed, and no changes are made.")
        os.environ['CORTEX_PROVIDER'] = 'fake'
        # Prefer a deterministic fake output if none provided
        os.environ.setdefault('CORTEX_FAKE_COMMANDS', json.dumps({
            "commands": [
                "echo Checking system...",
                "echo Simulating install...",
                "echo All good!"
            ]
        }))
        # Show a single dry-run flow to keep it simple
        return self.install("docker", execute=False, dry_run=True)


def main() -> int:
    """Entry point for the cortex CLI command."""

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
  cortex --test

Environment Variables:
  GROQ_API_KEY        Groq API key for Llama models
  OPENAI_API_KEY      OpenAI API key for GPT models
  ANTHROPIC_API_KEY   Anthropic API key for Claude models
  KIMI_API_KEY        Moonshot Kimi API key for K2 models
  CORTEX_PROVIDER     Optional override (groq|openai|claude|kimi|fake)
        """
    )

    parser.add_argument('--test', action='store_true', help='Run all developer test suites')
    parser.add_argument('--test-api', action='store_true', help='Test API connection for your configured provider')
    parser.add_argument('--provider', choices=['groq','openai','claude','kimi','fake','all'], help='Provider to use for this command or for --test-api (use "all" only with --test-api)')
    parser.add_argument('--test-fake', action='store_true', help='Quick check without API keys (uses fake commands)')
    parser.add_argument('--set-gpt', action='store_true', help='Set your OpenAI API key')
    parser.add_argument('--set-claude', dest='set_claude', action='store_true', help='Set your Anthropic Claude API key')
    parser.add_argument('--set-kimi', action='store_true', help='Set your Moonshot Kimi API key')
    parser.add_argument('--set-groq', action='store_true', help='Set your Groq API key')

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    install_parser = subparsers.add_parser('install', help='Install software using natural language')
    install_parser.add_argument('software', type=str, help='Software to install (natural language)')
    install_parser.add_argument('--execute', action='store_true', help='Execute the generated commands')
    install_parser.add_argument('--dry-run', action='store_true', help='Show commands without executing')

    args = parser.parse_args()

    if args.set_gpt:
        return CortexCLI().set_api_key('openai')

    if getattr(args, 'set_claude', False):
        return CortexCLI().set_api_key('claude')

    if args.set_kimi:
        return CortexCLI().set_api_key('kimi')

    if args.set_groq:
        return CortexCLI().set_api_key('groq')

    # If user supplied a provider on the CLI (e.g. `--provider groq`), make it
    # active for this invocation. The special value `all` is only meaningful
    # when used with `--test-api` and is not applied as an active provider.
    if args.provider and args.provider != 'all':
        os.environ['CORTEX_PROVIDER'] = args.provider

    if args.test_api:
        cli = CortexCLI()
        if args.provider == 'all':
            any_success = False
            for prov in cli._provider_priority():
                if prov == 'fake':
                    continue
                if not cli._provider_has_credentials(prov):
                    continue
                print(f"\n[CHECK] Testing {prov}...")
                rc = cli.test_api(prov)
                any_success = any_success or (rc == 0)
            return 0 if any_success else 1
        if args.provider:
            return cli.test_api(args.provider)
        return cli.test_api()

    if args.test_fake:
        return CortexCLI().test_fake()

    if args.test:
        test_dir = os.path.join(os.path.dirname(__file__), '..', 'test')
        test_runner = os.path.join(test_dir, 'run_all_tests.py')

        if not os.path.exists(test_runner):
            print("[ERROR] Test runner not found", file=sys.stderr)
            return 1

        result = subprocess.run([sys.executable, test_runner], check=False)
        return result.returncode

    if not args.command:
        parser.print_help()
        return 1

    cli = CortexCLI()

    if args.command == 'install':
        return cli.install(args.software, execute=args.execute, dry_run=args.dry_run)

    return 0


if __name__ == '__main__':
    sys.exit(main())
