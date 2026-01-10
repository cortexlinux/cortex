"""
First-Run Wizard Module for Cortex Linux

Provides a seamless onboarding experience for new users, guiding them
through initial setup, configuration, and feature discovery.
"""

import json
import logging
import os
import random
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

# Main branch import for encrypted storage
from cortex.env_manager import get_env_manager
from cortex.utils.api_key_validator import validate_anthropic_api_key, validate_openai_api_key
from cortex.env_manager import get_env_manager

logger = logging.getLogger(__name__)

# Application name for storing cortex API keys
CORTEX_APP_NAME = "cortex"

# Examples for dry run prompts (your addition)
DRY_RUN_EXAMPLES = [
    "Machine learning module",
    "libraries for video compression tool",
    "web development framework",
    "data analysis tools",
    "image processing library",
    "database management system",
    "text editor with plugins",
    "networking utilities",
    "game development engine",
    "scientific computing tools",
]


# ============================================================================
# YOUR HELPER FUNCTIONS (with fixed default path for api_key_detector sync)
# ============================================================================

def get_env_file_path() -> Path:
    """Get the path to the .env file.

    Returns the first existing .env file found, or ~/.cortex/.env as default.
    This ensures compatibility with api_key_detector which checks ~/.cortex/.env
    as priority #2.
    """
    possible_paths = [
        Path.home() / ".cortex" / ".env",  # Check this FIRST (sync with api_key_detector)
        Path.cwd() / ".env",
        Path(__file__).parent.parent / ".env",
        Path(__file__).parent.parent.parent / ".env",
    ]
    for path in possible_paths:
        if path.exists():
            return path
    # DEFAULT: ~/.cortex/.env (syncs with api_key_detector priority #2)
    return Path.home() / ".cortex" / ".env"


def read_key_from_env_file(key_name: str) -> str | None:
    """
    Read an API key directly from the .env file.
    Returns the key value or None if not found/blank.
    """
    env_path = get_env_file_path()

    if not env_path.exists():
        return None
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    if key == key_name:
                        value = value.strip()
                        if value and len(value) > 0:
                            return value
                        return None
    except Exception as e:
        logger.warning(f"Error reading .env file: {e}")
    return None


def save_key_to_env_file(key_name: str, key_value: str) -> bool:
    """
    Save an API key to the .env file.
    Updates existing key or adds new one.
    Ensures parent directory exists.
    """
    env_path = get_env_file_path()

    # Ensure ~/.cortex directory exists
    env_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    key_found = False

    if env_path.exists():
        try:
            with open(env_path) as f:
                lines = f.readlines()
        except Exception:
            pass

    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            existing_key = stripped.split("=")[0].strip()
            if existing_key == key_name:
                new_lines.append(f'{key_name}="{key_value}"\n')
                key_found = True
                continue
        new_lines.append(line)

    if not key_found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")
        new_lines.append(f'{key_name}="{key_value}"\n')

    try:
        with open(env_path, "w") as f:
            f.writelines(new_lines)
        return True
    except Exception as e:
        logger.warning(f"Error saving to .env file: {e}")
        return False


def is_valid_api_key(key: str | None, key_type: str = "generic") -> bool:
    """Check if an API key is valid (non-blank and properly formatted)."""
    if key is None:
        return False

    key = key.strip()
    if not key:
        return False

    if key_type == "anthropic":
        return key.startswith("sk-ant-")
    elif key_type == "openai":
        return key.startswith("sk-")
    return True


def get_valid_api_key(env_var: str, key_type: str = "generic") -> str | None:
    """
    Get a valid API key from .env file first, then environment variable.
    Treats blank keys as missing. Honors shell-exported keys if .env is empty.
    """
    key_from_file = read_key_from_env_file(env_var)

    env_path = get_env_file_path()
    logger.debug(f"Checking {env_var} in {env_path}: '{key_from_file}'")

    # First priority: valid key from .env file
    if key_from_file is not None and len(key_from_file) > 0:
        if is_valid_api_key(key_from_file, key_type):
            os.environ[env_var] = key_from_file
            logger.debug(f"Using {env_var} from .env file")
            return key_from_file
        else:
            logger.debug(f"Key in .env file for {env_var} is invalid (wrong format)")

    # Second priority: valid key from shell environment (already exported)
    key_from_env = os.environ.get(env_var)
    if key_from_env is not None and len(key_from_env.strip()) > 0:
        key_from_env = key_from_env.strip()
        if is_valid_api_key(key_from_env, key_type):
            logger.debug(f"Using {env_var} from shell environment")
            return key_from_env
        else:
            logger.debug(f"Key in os.environ for {env_var} is invalid (wrong format)")

    logger.debug(f"No valid key found for {env_var}")
    return None


def detect_available_providers() -> list[str]:
    """Detect available providers based on valid (non-blank) API keys in .env file."""
    providers = []

    if get_valid_api_key("ANTHROPIC_API_KEY", "anthropic"):
        providers.append("anthropic")
    if get_valid_api_key("OPENAI_API_KEY", "openai"):
        providers.append("openai")
    if shutil.which("ollama"):
        providers.append("ollama")

    return providers


# ============================================================================
# WIZARD CLASSES
# ============================================================================

class WizardStep(Enum):
    """Steps in the first-run wizard."""

    WELCOME = "welcome"
    API_SETUP = "api_setup"
    HARDWARE_DETECTION = "hardware_detection"
    PREFERENCES = "preferences"
    SHELL_INTEGRATION = "shell_integration"
    TEST_COMMAND = "test_command"
    COMPLETE = "complete"


@dataclass
class WizardState:
    """Tracks the current state of the wizard."""

    current_step: WizardStep = WizardStep.WELCOME
    completed_steps: list[WizardStep] = field(default_factory=list)
    skipped_steps: list[WizardStep] = field(default_factory=list)
    collected_data: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None

    def mark_completed(self, step: WizardStep) -> None:
        if step not in self.completed_steps:
            self.completed_steps.append(step)

    def mark_skipped(self, step: WizardStep) -> None:
        if step not in self.skipped_steps:
            self.skipped_steps.append(step)

    def is_completed(self, step: WizardStep) -> bool:
        return step in self.completed_steps

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_step": self.current_step.value,
            "completed_steps": [s.value for s in self.completed_steps],
            "skipped_steps": [s.value for s in self.skipped_steps],
            "collected_data": self.collected_data,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WizardState":
        return cls(
            current_step=WizardStep(data.get("current_step", "welcome")),
            completed_steps=[WizardStep(s) for s in data.get("completed_steps", [])],
            skipped_steps=[WizardStep(s) for s in data.get("skipped_steps", [])],
            collected_data=data.get("collected_data", {}),
            started_at=(
                datetime.fromisoformat(data["started_at"])
                if data.get("started_at")
                else datetime.now()
            ),
            completed_at=(
                datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
            ),
        )


@dataclass
class StepResult:
    """Result of a wizard step."""

    success: bool
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    next_step: WizardStep | None = None
    skip_to: WizardStep | None = None


class FirstRunWizard:
    """Interactive first-run wizard for Cortex Linux."""

    CONFIG_DIR = Path.home() / ".cortex"
    STATE_FILE = CONFIG_DIR / "wizard_state.json"
    CONFIG_FILE = CONFIG_DIR / "config.json"
    SETUP_COMPLETE_FILE = CONFIG_DIR / ".setup_complete"

    def __init__(self, interactive: bool = True) -> None:
        self.interactive = interactive
        self.state = WizardState()
        self.config: dict[str, Any] = {}
        self._ensure_config_dir()

    def _ensure_config_dir(self) -> None:
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def needs_setup(self) -> bool:
        return not self.SETUP_COMPLETE_FILE.exists()

    def _get_current_provider(self) -> str | None:
        """Get the currently configured provider from config file."""
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE) as f:
                    config = json.load(f)
                    return config.get("api_provider")
            except Exception:
                pass
        return None

    def load_state(self) -> bool:
        if self.STATE_FILE.exists():
            try:
                with open(self.STATE_FILE) as f:
                    data = json.load(f)
                    self.state = WizardState.from_dict(data)
                    return True
            except Exception as e:
                logger.warning(f"Could not load wizard state: {e}")
        return False

    def save_state(self) -> None:
        try:
            with open(self.STATE_FILE, "w") as f:
                json.dump(self.state.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save wizard state: {e}")

    def save_config(self) -> None:
        try:
            with open(self.CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save config: {e}")

    def mark_setup_complete(self) -> None:
        self.SETUP_COMPLETE_FILE.touch()
        self.state.completed_at = datetime.now()
        self.save_state()

    def _prompt_for_api_key(self, key_type: str) -> str | None:
        """Prompt user for a valid API key, rejecting blank inputs."""
        if key_type == "anthropic":
            prefix = "sk-ant-"
            provider_name = "Claude (Anthropic)"
            print("\nTo get a Claude API key:")
            print("  1. Go to https://console.anthropic.com")
            print("  2. Sign up or log in")
            print("  3. Create an API key\n")
        else:
            prefix = "sk-"
            provider_name = "OpenAI"
            print("\nTo get an OpenAI API key:")
            print("  1. Go to https://platform.openai.com")
            print("  2. Sign up or log in")
            print("  3. Create an API key\n")

        while True:
            key = self._prompt(f"Enter your {provider_name} API key (or 'q' to cancel): ")

            if key.lower() == "q":
                return None

            if not key or not key.strip():
                print("\n⚠ API key cannot be blank. Please enter a valid key.")
                continue

            key = key.strip()

            if not key.startswith(prefix):
                print(f"\n⚠ Invalid key format. {provider_name} keys should start with '{prefix}'")
                continue

            return key

    def _install_suggested_packages(self) -> None:
        """Offer to install suggested packages."""
        suggestions = ["python", "numpy", "requests"]
        print("\nTry installing a package to verify Cortex is ready:")
        for pkg in suggestions:
            print(f"  cortex install {pkg}")
        resp = self._prompt("Would you like to install these packages now? [Y/n]: ", default="y")
        if resp.strip().lower() in ("", "y", "yes"):
            env = os.environ.copy()
            for pkg in suggestions:
                print(f"\nInstalling {pkg}...")
                try:
                    result = subprocess.run(
                        [sys.executable, "-m", "cortex.cli", "install", pkg],
                        capture_output=True,
                        text=True,
                        env=env,
                        check=False,
                    )
                    print(result.stdout)
                    if result.stderr:
                        print(result.stderr)
                except Exception as e:
                    print(f"Error installing {pkg}: {e}")

    def run(self) -> bool:
        """
        Main wizard flow.

        1. Reload and check .env file for API keys
        2. Always show provider selection menu (with all options)
        3. Show "Skip reconfiguration" only on second run onwards
        4. If selected provider's key is blank in .env, prompt for key
        5. Save key to .env file
        6. Run dry run to verify
        """
        self._clear_screen()
        self._print_banner()

        env_path = get_env_file_path()
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=env_path, override=False)
        except ImportError:
            pass

        available_providers = detect_available_providers()
        has_ollama = shutil.which("ollama") is not None

        current_provider = self._get_current_provider()
        is_first_run = current_provider is None

        provider_names = {
            "anthropic": "Anthropic (Claude)",
            "openai": "OpenAI",
            "ollama": "Ollama (local)",
            "none": "None",
        }

        print("\nSelect your preferred LLM provider:\n")

        option_num = 1
        provider_map = {}

        if not is_first_run and current_provider and current_provider != "none":
            current_name = provider_names.get(current_provider, current_provider)
            print(f"  {option_num}. Skip reconfiguration (current: {current_name})")
            provider_map[str(option_num)] = "skip_reconfig"
            option_num += 1

        anthropic_status = " ✓" if "anthropic" in available_providers else " (key not found)"
        print(f"  {option_num}. Anthropic (Claude){anthropic_status} - Recommended")
        provider_map[str(option_num)] = "anthropic"
        option_num += 1

        openai_status = " ✓" if "openai" in available_providers else " (key not found)"
        print(f"  {option_num}. OpenAI{openai_status}")
        provider_map[str(option_num)] = "openai"
        option_num += 1

        ollama_status = " ✓" if has_ollama else " (not installed)"
        print(f"  {option_num}. Ollama (local){ollama_status}")
        provider_map[str(option_num)] = "ollama"

        valid_choices = list(provider_map.keys())
        default_choice = "1"

        choice = self._prompt(
            f"\nChoose a provider [{'-'.join([valid_choices[0], valid_choices[-1]])}]: ",
            default=default_choice,
        )

        provider = provider_map.get(choice)

        if not provider:
            print(f"Invalid choice. Please enter a number between {valid_choices[0]} and {valid_choices[-1]}.")
            return False

        if provider == "skip_reconfig":
            print(f"\n✓ Keeping current provider: {provider_names.get(current_provider, current_provider)}")
            self.mark_setup_complete()
            return True

        if provider == "anthropic":
            existing_key = get_valid_api_key("ANTHROPIC_API_KEY", "anthropic")

            if existing_key:
                print("\n✓ Existing Anthropic API key found.")
                replace = self._prompt("Do you want to replace it with a new key? [y/N]: ", default="n")
                if replace.strip().lower() in ("y", "yes"):
                    key = self._prompt_for_api_key("anthropic")
                    if key is None:
                        print("\nSetup cancelled.")
                        return False
                    self._save_env_var("ANTHROPIC_API_KEY", key)
                    os.environ["ANTHROPIC_API_KEY"] = key
                else:
                    print("\n✓ Keeping existing API key.")
            else:
                print("\nNo valid Anthropic API key found.")
                key = self._prompt_for_api_key("anthropic")
                if key is None:
                    print("\nSetup cancelled.")
                    return False
                self._save_env_var("ANTHROPIC_API_KEY", key)
                os.environ["ANTHROPIC_API_KEY"] = key

            self.config["api_provider"] = "anthropic"
            self.config["api_key_configured"] = True

            # Dry run verification
            random_example = random.choice(DRY_RUN_EXAMPLES)
            print(f'\nVerifying setup with dry run: cortex install "{random_example}"...')
            try:
                from cortex.cli import CortexCLI
                cli = CortexCLI()
                result = cli.install(random_example, execute=False, dry_run=True, forced_provider="claude")
                if result != 0:
                    print("\n❌ Dry run failed. Please check your API key and network.")
                    return False
                print("\n✅ API key verified successfully!")
            except Exception as e:
                print(f"\n❌ Error during verification: {e}")
                return False

        elif provider == "openai":
            existing_key = get_valid_api_key("OPENAI_API_KEY", "openai")

            if existing_key:
                print("\n✓ Existing OpenAI API key found.")
                replace = self._prompt("Do you want to replace it with a new key? [y/N]: ", default="n")
                if replace.strip().lower() in ("y", "yes"):
                    key = self._prompt_for_api_key("openai")
                    if key is None:
                        print("\nSetup cancelled.")
                        return False
                    self._save_env_var("OPENAI_API_KEY", key)
                    os.environ["OPENAI_API_KEY"] = key
                else:
                    print("\n✓ Keeping existing API key.")
            else:
                print("\nNo valid OpenAI API key found.")
                key = self._prompt_for_api_key("openai")
                if key is None:
                    print("\nSetup cancelled.")
                    return False
                self._save_env_var("OPENAI_API_KEY", key)
                os.environ["OPENAI_API_KEY"] = key

            self.config["api_provider"] = "openai"
            self.config["api_key_configured"] = True

            # Dry run verification
            random_example = random.choice(DRY_RUN_EXAMPLES)
            print(f'\nVerifying setup with dry run: cortex install "{random_example}"...')
            try:
                from cortex.cli import CortexCLI
                cli = CortexCLI()
                result = cli.install(random_example, execute=False, dry_run=True, forced_provider="openai")
                if result != 0:
                    print("\n❌ Dry run failed. Please check your API key and network.")
                    return False
                print("\n✅ API key verified successfully!")
            except Exception as e:
                print(f"\n❌ Error during verification: {e}")
                return False

        elif provider == "ollama":
            if not has_ollama:
                print("\n⚠ Ollama is not installed.")
                print("Install it from: https://ollama.ai")
                return False

            # Model selection from MAIN branch
            print("\nWhich Ollama model would you like to use?")
            print("  1. llama3.2 (2GB) - Recommended for most users")
            print("  2. llama3.2:1b (1.3GB) - Faster, less RAM")
            print("  3. mistral (4GB) - Alternative quality model")
            print("  4. phi3 (2.3GB) - Microsoft's efficient model")
            print("  5. Custom (enter your own)")

            model_choices = {
                "1": "llama3.2",
                "2": "llama3.2:1b",
                "3": "mistral",
                "4": "phi3",
            }

            model_choice = self._prompt("\nEnter choice [1]: ", default="1")

            if model_choice == "5":
                model_name = self._prompt("Enter model name: ", default="llama3.2")
            elif model_choice in model_choices:
                model_name = model_choices[model_choice]
            else:
                print(f"Invalid choice '{model_choice}', using default model llama3.2")
                model_name = "llama3.2"

            # Pull the selected model
            print(f"\nPulling {model_name} model (this may take a few minutes)...")
            try:
                subprocess.run(["ollama", "pull", model_name], check=True)
                print("\n✓ Model ready!")
            except subprocess.CalledProcessError:
                print(f"\n⚠ Could not pull model - you can do this later with: ollama pull {model_name}")

            self.config["api_provider"] = "ollama"
            self.config["ollama_model"] = model_name
            self.config["api_key_configured"] = True

        self.save_config()
        self.mark_setup_complete()

        print(f"\n[✔] Setup complete! Provider '{provider}' is ready for AI workloads.")
        print("You can rerun this wizard anytime with: cortex wizard")
        return True

    def _clear_screen(self) -> None:
        if self.interactive:
            os.system("clear" if os.name == "posix" else "cls")

    def _print_banner(self) -> None:
        banner = """
       ____           _
      / ___|___  _ __| |_ _____  __
     | |   / _ \\| '__| __/ _ \\ \\/ /
     | |__| (_) | |  | ||  __/>  <
      \\____\\___/|_|   \\__\\___/_/\\_\\

        Linux that understands you.
    """
        print(banner)

    def _print_header(self, title: str) -> None:
        print("\n" + "=" * 50)
        print(f"  {title}")
        print("=" * 50 + "\n")

    def _print_error(self, message: str) -> None:
        print(f"\n❌ {message}\n")

    def _prompt(self, message: str, default: str = "") -> str:
        if not self.interactive:
            return default
        try:
            response = input(message).strip()
            return response if response else default
        except (EOFError, KeyboardInterrupt):
            return default

    def _save_env_var(self, name: str, value: str) -> None:
        """Save API key to BOTH .env file AND encrypted storage.

        This ensures compatibility with:
        - api_key_detector (reads from ~/.cortex/.env)
        - Main branch encrypted storage (reads from env_manager)
        """
        # Set for current session
        os.environ[name] = value

        # Method 1: Save to ~/.cortex/.env (for api_key_detector compatibility)
        if save_key_to_env_file(name, value):
            print(f"✓ API key saved to {get_env_file_path()}")
        else:
            # Fallback to shell config
            self._save_to_shell_config(name, value)

        # Method 2: Save to encrypted storage (main branch approach)
        try:
            env_mgr = get_env_manager()
            provider_name_raw = name.replace("_API_KEY", "")
            if provider_name_raw == "OPENAI":
                provider_name_display = "OpenAI"
            elif provider_name_raw == "ANTHROPIC":
                provider_name_display = "Anthropic"
            else:
                provider_name_display = provider_name_raw.replace("_", " ").title()

            env_mgr.set_variable(
                app=CORTEX_APP_NAME,
                key=name,
                value=value,
                encrypt=True,
                description=f"API key for {provider_name_display}",
            )
            logger.info(f"Saved {name} to encrypted storage")
        except ImportError:
            logger.warning(f"cryptography package not installed. {name} saved to .env only.")
        except Exception as e:
            logger.warning(f"Could not save to encrypted storage: {e}")

    def _save_to_shell_config(self, name: str, value: str) -> None:
        """Fallback: Save environment variable to shell config."""
        shell = os.environ.get("SHELL", "/bin/bash")
        shell_name = os.path.basename(shell)
        config_file = self._get_shell_config(shell_name)
        export_line = f'\nexport {name}="{value}"\n'
        try:
            with open(config_file, "a") as f:
                f.write(export_line)
            print(f"✓ API key saved to {config_file}")
        except Exception as e:
            logger.warning(f"Could not save env var: {e}")

    def _get_shell_config(self, shell: str) -> Path:
        """Get the shell config file path."""
        home = Path.home()
        configs = {
            "bash": home / ".bashrc",
            "zsh": home / ".zshrc",
            "fish": home / ".config" / "fish" / "config.fish",
        }
        return configs.get(shell, home / ".profile")

    # ========================================================================
    # LEGACY METHODS (for backward compatibility with tests)
    # ========================================================================

    def _step_welcome(self) -> StepResult:
        """Welcome step - legacy method for tests."""
        self._print_banner()
        return StepResult(success=True)

    def _step_api_setup(self) -> StepResult:
        """API key configuration step."""
        self._clear_screen()
        self._print_header("Step 1: API Configuration")

        existing_claude = os.environ.get("ANTHROPIC_API_KEY")
        existing_openai = os.environ.get("OPENAI_API_KEY")

        claude_status = " ✓ (key found)" if existing_claude else ""
        openai_status = " ✓ (key found)" if existing_openai else ""

        print(f"""
Cortex uses AI to understand your commands. You can use:

  1. Claude API (Anthropic){claude_status} - Recommended
  2. OpenAI API{openai_status}
  3. Local LLM (Ollama) - Free, runs on your machine
  4. Skip for now (limited functionality)
""")

        if not self.interactive:
            if existing_claude:
                self.config["api_provider"] = "anthropic"
                self.config["api_key_configured"] = True
                return StepResult(success=True, data={"api_provider": "anthropic"})
            if existing_openai:
                self.config["api_provider"] = "openai"
                self.config["api_key_configured"] = True
                return StepResult(success=True, data={"api_provider": "openai"})
            return StepResult(
                success=True,
                message="Non-interactive mode - skipping API setup",
                data={"api_provider": "none"},
            )

        choice = self._prompt("Choose an option [1-4]: ", default="1")

        if choice == "1":
            if existing_claude:
                print("\n✓ Using existing Claude API key!")
                self.config["api_provider"] = "anthropic"
                self.config["api_key_configured"] = True
                return StepResult(success=True, data={"api_provider": "anthropic"})
            return self._setup_claude_api()
        elif choice == "2":
            if existing_openai:
                print("\n✓ Using existing OpenAI API key!")
                self.config["api_provider"] = "openai"
                self.config["api_key_configured"] = True
                return StepResult(success=True, data={"api_provider": "openai"})
            return self._setup_openai_api()
        elif choice == "3":
            return self._setup_ollama()
        else:
            print("\n⚠ Running without AI - you'll only have basic apt functionality")
            return StepResult(success=True, data={"api_provider": "none"})

    def _setup_claude_api(self) -> StepResult:
        """Set up Claude API."""
        print("\nTo get a Claude API key:")
        print("  1. Go to https://console.anthropic.com")
        print("  2. Sign up or log in")
        print("  3. Create an API key\n")

        api_key = self._prompt("Enter your Claude API key: ")

        if not api_key or not api_key.startswith("sk-ant-"):
            print("\n⚠ Invalid API key format")
            return StepResult(success=True, data={"api_provider": "none"})

        self._save_env_var("ANTHROPIC_API_KEY", api_key)

        self.config["api_provider"] = "anthropic"
        self.config["api_key_configured"] = True

        print("\n✓ Claude API key saved!")
        return StepResult(success=True, data={"api_provider": "anthropic"})

    def _setup_openai_api(self) -> StepResult:
        """Set up OpenAI API."""
        print("\nTo get an OpenAI API key:")
        print("  1. Go to https://platform.openai.com")
        print("  2. Sign up or log in")
        print("  3. Create an API key\n")

        api_key = self._prompt("Enter your OpenAI API key: ")

        if not api_key or not api_key.startswith("sk-"):
            print("\n⚠ Invalid API key format")
            return StepResult(success=True, data={"api_provider": "none"})

        self._save_env_var("OPENAI_API_KEY", api_key)

        self.config["api_provider"] = "openai"
        self.config["api_key_configured"] = True

        print("\n✓ OpenAI API key saved!")
        return StepResult(success=True, data={"api_provider": "openai"})

    def _setup_ollama(self) -> StepResult:
        """Set up Ollama for local LLM."""
        print("\nChecking for Ollama...")

        ollama_path = shutil.which("ollama")

        if not ollama_path:
            print("\nOllama is not installed. Install it with:")
            print("  curl -fsSL https://ollama.ai/install.sh | sh")

            install = self._prompt("\nInstall Ollama now? [y/N]: ", default="n")

            if install.lower() == "y":
                try:
                    subprocess.run(
                        "curl -fsSL https://ollama.ai/install.sh | sh", shell=True, check=True
                    )
                    print("\n✓ Ollama installed!")
                except subprocess.CalledProcessError:
                    print("\n✗ Failed to install Ollama")
                    return StepResult(success=True, data={"api_provider": "none"})

        self.config["api_provider"] = "ollama"
        # Let user choose model or use default
        print("\nWhich Ollama model would you like to use?")
        print("  1. llama3.2 (2GB) - Recommended for most users")
        print("  2. llama3.2:1b (1.3GB) - Faster, less RAM")
        print("  3. mistral (4GB) - Alternative quality model")
        print("  4. phi3 (2.3GB) - Microsoft's efficient model")
        print("  5. Custom (enter your own)")

        model_choices = {
            "1": "llama3.2",
            "2": "llama3.2:1b",
            "3": "mistral",
            "4": "phi3",
        }

        choice = self._prompt("\nEnter choice [1]: ", default="1")

        if choice == "5":
            model_name = self._prompt("Enter model name: ", default="llama3.2")
        elif choice in model_choices:
            model_name = model_choices[choice]
        else:
            print(f"Invalid choice '{choice}', using default model llama3.2")
            model_name = "llama3.2"

        # Pull the selected model
        print(f"\nPulling {model_name} model (this may take a few minutes)...")
        try:
            subprocess.run(["ollama", "pull", model_name], check=True)
            print("\n✓ Model ready!")
        except subprocess.CalledProcessError:
            print(
                f"\n⚠ Could not pull model - you can do this later with: ollama pull {model_name}"
            )

        self.config["api_provider"] = "ollama"
        self.config["ollama_model"] = model_name

        return StepResult(success=True, data={"api_provider": "ollama"})

    def _step_hardware_detection(self) -> StepResult:
        """Hardware detection step."""
        hardware_info = self._detect_hardware()
        self.config["hardware"] = hardware_info
        return StepResult(success=True, data={"hardware": hardware_info})

    def _step_preferences(self) -> StepResult:
        """Preferences step."""
        preferences = {"auto_confirm": False, "verbosity": "normal", "enable_cache": True}
        self.config["preferences"] = preferences
        return StepResult(success=True, data={"preferences": preferences})

    def _step_shell_integration(self) -> StepResult:
        """Shell integration step."""
        return StepResult(success=True, data={"shell_integration": False})

    def _step_test_command(self) -> StepResult:
        """Test command step."""
        return StepResult(success=True, data={"test_completed": False})

    def _step_complete(self) -> StepResult:
        """Completion step."""
        self.save_config()
        return StepResult(success=True)

    def _detect_hardware(self) -> dict[str, Any]:
        """Detect system hardware."""
        try:
            from dataclasses import asdict

            from cortex.hardware_detection import detect_hardware
            info = detect_hardware()
            return asdict(info)
        except Exception as e:
            logger.warning(f"Hardware detection failed: {e}")
            return {
                "cpu": {"vendor": "unknown", "model": "unknown"},
                "gpu": [],
                "memory": {"total_gb": 0},
            }

    def _generate_completion_script(self, shell: str) -> str:
        if shell in ["bash", "sh"]:
            return """
# Cortex bash completion
_cortex_completion() {
    local cur="${COMP_WORDS[COMP_CWORD]}"
    local commands="install remove update search info undo history help"
    if [ $COMP_CWORD -eq 1 ]; then
        COMPREPLY=($(compgen -W "$commands" -- "$cur"))
    fi
}
complete -F _cortex_completion cortex
"""
        elif shell == "zsh":
            return """
# Cortex zsh completion
_cortex() {
    local commands=(
        'install:Install packages'
        'remove:Remove packages'
        'update:Update system'
        'search:Search for packages'
        'info:Show package info'
        'undo:Undo last operation'
        'history:Show history'
        'help:Show help'
    )
    _describe 'command' commands
}
compdef _cortex cortex
"""
        elif shell == "fish":
            return """
# Cortex fish completion
complete -c cortex -f
complete -c cortex -n "__fish_use_subcommand" -a "install" -d "Install packages"
complete -c cortex -n "__fish_use_subcommand" -a "remove" -d "Remove packages"
complete -c cortex -n "__fish_use_subcommand" -a "update" -d "Update system"
complete -c cortex -n "__fish_use_subcommand" -a "search" -d "Search packages"
complete -c cortex -n "__fish_use_subcommand" -a "undo" -d "Undo last operation"
complete -c cortex -n "__fish_use_subcommand" -a "history" -d "Show history"
"""
        return "# No completion available for this shell"


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

        if not self.interactive:
            return StepResult(success=True, data={"test_completed": False})

        run_test = self._prompt("Run test now? [Y/n]: ", default="y")

        if run_test.lower() == "n":
            return StepResult(success=True, data={"test_completed": False})

        print("\n" + "=" * 50)

        # Simulate or run actual test
        try:
            # Check if cortex command exists
            cortex_path = shutil.which("cortex")
            if cortex_path:
                result = subprocess.run(
                    ["cortex", "search", "text", "editors"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                print(result.stdout)
                if result.returncode == 0:
                    print("\n✓ Test successful!")
                else:
                    print(f"\n⚠ Test completed with warnings: {result.stderr}")
            else:
                # Fallback to apt search
                print("Running: apt search text-editor")
                subprocess.run(["apt", "search", "text-editor"], timeout=30)
                print("\n✓ Basic functionality working!")
        except subprocess.TimeoutExpired:
            print("\n⚠ Test timed out - this is OK, Cortex is still usable")
        except Exception as e:
            print(f"\n⚠ Test failed: {e}")

        print("=" * 50)

        if self.interactive:
            self._prompt("\nPress Enter to continue: ")

        return StepResult(success=True, data={"test_completed": True})

    def _step_complete(self) -> StepResult:
        """Completion step."""
        self._clear_screen()
        self._print_header("Setup Complete! 🎉")

        # Save all config
        self.save_config()

        print(
            """
Cortex is ready to use! Here are some things to try:

  📦 Install packages:
     cortex install docker
     cortex install a web server

  🔍 Search packages:
     cortex search image editors
     cortex search something for pdf

  🔄 Update system:
     cortex update everything

  ⏪ Undo mistakes:
     cortex undo

  📖 Get help:
     cortex help

"""
        )

        # Show configuration summary
        print("Configuration Summary:")
        print(f"  • API Provider: {self.config.get('api_provider', 'none')}")

        hardware = self.config.get("hardware", {})
        if hardware.get("gpu_vendor"):
            print(f"  • GPU: {hardware.get('gpu', 'Detected')}")

        prefs = self.config.get("preferences", {})
        print(f"  • Verbosity: {prefs.get('verbosity', 'normal')}")
        print(f"  • Caching: {'enabled' if prefs.get('enable_cache') else 'disabled'}")

        print("\n" + "=" * 50)
        print("Happy computing! 🐧")
        print("=" * 50 + "\n")

        return StepResult(success=True)

    # Helper methods
    def _clear_screen(self):
        """Clear the terminal screen."""
        if self.interactive:
            os.system("clear" if os.name == "posix" else "cls")

    def _print_banner(self):
        """Print the Cortex banner."""
        banner = """
   ____           _
  / ___|___  _ __| |_ _____  __
 | |   / _ \\| '__| __/ _ \\ \\/ /
 | |__| (_) | |  | ||  __/>  <
  \\____\\___/|_|   \\__\\___/_/\\_\\

        Linux that understands you.
"""
        print(banner)

    def _print_header(self, title: str):
        """Print a section header."""
        print("\n" + "=" * 50)
        print(f"  {title}")
        print("=" * 50 + "\n")

    def _print_error(self, message: str):
        """Print an error message."""
        print(f"\n❌ {message}\n")

    def _prompt(self, message: str, default: str = "") -> str:
        """Prompt for user input."""
        if not self.interactive:
            return default

        try:
            response = input(message).strip()
            return response if response else default
        except (EOFError, KeyboardInterrupt):
            return default

    def _save_env_var(self, name: str, value: str):
        """Save environment variable securely using encrypted storage.

        API keys are stored encrypted in ~/.cortex/environments/cortex.json
        using Fernet encryption. The encryption key is stored in
        ~/.cortex/.env_key with restricted permissions (chmod 600).
        """
        # Set for current session regardless of storage success
        os.environ[name] = value

        try:
            env_mgr = get_env_manager()

            # Handle brand names correctly (e.g., "OpenAI" not "Openai")
            provider_name_raw = name.replace("_API_KEY", "")
            if provider_name_raw == "OPENAI":
                provider_name_display = "OpenAI"
            elif provider_name_raw == "ANTHROPIC":
                provider_name_display = "Anthropic"
            else:
                provider_name_display = provider_name_raw.replace("_", " ").title()

            env_mgr.set_variable(
                app=CORTEX_APP_NAME,
                key=name,
                value=value,
                encrypt=True,
                description=f"API key for {provider_name_display}",
            )
            logger.info(f"Saved {name} to encrypted storage")
        except ImportError:
            logger.warning(
                f"cryptography package not installed. {name} set for current session only. "
                "Install cryptography for persistent encrypted storage: pip install cryptography"
            )
        except Exception as e:
            logger.warning(f"Could not save env var to encrypted storage: {e}")


# Convenience functions
def needs_first_run() -> bool:
    """Check if first-run wizard is needed."""
    return FirstRunWizard(interactive=False).needs_setup()


def run_wizard(interactive: bool = True) -> bool:
    """Run the first-run wizard."""
    wizard = FirstRunWizard(interactive=interactive)
    return wizard.run()


def get_config() -> dict[str, Any]:
    """Get the saved configuration."""
    config_file = FirstRunWizard.CONFIG_FILE
    if config_file.exists():
        with open(config_file) as f:
            return json.load(f)
    return {}


__all__ = [
    "FirstRunWizard",
    "WizardState",
    "WizardStep",
    "StepResult",
    "needs_first_run",
    "run_wizard",
    "get_config",
]

if __name__ == "__main__":
    if needs_first_run() or "--force" in sys.argv:
        success = run_wizard()
        sys.exit(0 if success else 1)
    else:
        print("Setup already complete. Use --force to run again.")
