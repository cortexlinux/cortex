"""
First-Run Wizard Module for Cortex Linux.

Provides a seamless onboarding experience for new users, guiding them
through initial setup, configuration, and feature discovery.

Syncs with api_key_detector for consistent API key detection and storage.
"""

import json
import logging
import os
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from cortex.env_manager import get_env_manager

# Import the merged api_key_detector for consistent key detection
try:
    from cortex.api_key_detector import (
        SUPPORTED_PROVIDERS,
        detect_api_key,
        get_detected_provider,
    )

    HAS_API_KEY_DETECTOR = True
except ImportError:
    HAS_API_KEY_DETECTOR = False

logger = logging.getLogger(__name__)

CORTEX_APP_NAME = "cortex"

# Canonical location for storing API keys (syncs with api_key_detector priority #2)
CORTEX_ENV_FILE = Path.home() / ".cortex" / ".env"

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


def get_env_file_path() -> Path:
    """Get the canonical path to the .env file.

    Always returns ~/.cortex/.env for consistency with api_key_detector.
    This is priority #2 in api_key_detector's search order, and the
    recommended location for user-configured keys.

    Returns:
        Path to the .env file (~/.cortex/.env).
    """
    return CORTEX_ENV_FILE


def read_key_from_env_file(key_name: str) -> str | None:
    """Read an API key directly from the .env file.

    Args:
        key_name: The environment variable name to look for.

    Returns:
        The key value or None if not found/blank.
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
                    if key == key_name and value:
                        return value
    except OSError as e:
        logger.warning("Error reading .env file: %s", e)
    return None


def save_key_to_env_file(key_name: str, key_value: str) -> bool:
    """Save an API key to the .env file.

    Saves to ~/.cortex/.env which is checked by api_key_detector (priority #2).

    Args:
        key_name: The environment variable name.
        key_value: The value to save.

    Returns:
        True if saved successfully, False otherwise.
    """
    env_path = get_env_file_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    key_found = False

    if env_path.exists():
        try:
            with open(env_path) as f:
                lines = f.readlines()
        except OSError:
            pass

    new_lines: list[str] = []
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
    except OSError as e:
        logger.warning("Error saving to .env file: %s", e)
        return False


def is_valid_api_key(key: str | None, key_type: str = "generic") -> bool:
    """Check if an API key is valid (non-blank and properly formatted).

    Args:
        key: The API key to validate.
        key_type: Type of key ('anthropic', 'openai', or 'generic').

    Returns:
        True if the key is valid, False otherwise.
    """
    if not key or not key.strip():
        return False

    key = key.strip()
    if key_type == "anthropic":
        return key.startswith("sk-ant-")
    if key_type == "openai":
        # OpenAI keys start with "sk-" but NOT "sk-ant-" (that's Anthropic)
        return key.startswith("sk-") and not key.startswith("sk-ant-")
    return True


def get_valid_api_key(env_var: str, key_type: str = "generic") -> str | None:
    """Get a valid API key from standard locations.

    Checks locations in order of priority:
    1. ~/.cortex/.env
    2. Environment variables
    3. ~/.config/anthropic/credentials.json (Claude CLI)
    4. ~/.config/openai/credentials.json (OpenAI CLI)
    5. .env in current directory

    Args:
        env_var: The environment variable name.
        key_type: Type of key for validation.

    Returns:
        The valid API key or None if not found.
    """
    # Check ~/.cortex/.env first (highest priority for first-run wizard)
    key_from_file = read_key_from_env_file(env_var)
    if key_from_file and is_valid_api_key(key_from_file, key_type):
        logger.debug("Using %s from ~/.cortex/.env", env_var)
        # Set in environment for this session
        os.environ[env_var] = key_from_file
        return key_from_file

    # Check environment variable
    key_from_env = os.environ.get(env_var, "").strip()
    if key_from_env and is_valid_api_key(key_from_env, key_type):
        logger.debug("Using %s from environment variable", env_var)
        return key_from_env

    # Use api_key_detector for additional locations if available
    if HAS_API_KEY_DETECTOR:
        provider = "anthropic" if env_var == "ANTHROPIC_API_KEY" else "openai"
        try:
            detected_key = detect_api_key(provider)
            if detected_key and is_valid_api_key(detected_key, key_type):
                logger.debug("Using %s from api_key_detector", env_var)
                return detected_key
        except Exception as e:
            logger.debug("api_key_detector failed: %s", e)

    logger.debug("No valid key found for %s", env_var)
    return None


def detect_available_providers() -> list[str]:
    """Detect available providers based on valid API keys.

    Uses api_key_detector if available to check all supported locations.

    Returns:
        List of available provider names ('anthropic', 'openai', 'ollama').
    """
    providers = []

    # Use api_key_detector if available
    if HAS_API_KEY_DETECTOR:
        try:
            detected = get_detected_provider()
            if detected:
                providers.append(detected)
                # Check for additional providers
                for provider in SUPPORTED_PROVIDERS:
                    if provider not in providers:
                        key = detect_api_key(provider)
                        if key:
                            providers.append(provider)
                if shutil.which("ollama") and "ollama" not in providers:
                    providers.append("ollama")
                return providers
        except Exception as e:
            logger.debug("api_key_detector detection failed: %s", e)

    # Fallback detection
    if get_valid_api_key("ANTHROPIC_API_KEY", "anthropic"):
        providers.append("anthropic")
    if get_valid_api_key("OPENAI_API_KEY", "openai"):
        providers.append("openai")
    if shutil.which("ollama"):
        providers.append("ollama")

    return providers


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
        """Mark a step as completed."""
        if step not in self.completed_steps:
            self.completed_steps.append(step)

    def mark_skipped(self, step: WizardStep) -> None:
        """Mark a step as skipped."""
        if step not in self.skipped_steps:
            self.skipped_steps.append(step)

    def is_completed(self, step: WizardStep) -> bool:
        """Check if a step is completed."""
        return step in self.completed_steps

    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary."""
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
        """Create state from dictionary."""
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

    PROVIDER_NAMES = {
        "anthropic": "Anthropic (Claude)",
        "openai": "OpenAI",
        "ollama": "Ollama (local)",
        "none": "None",
    }

    MODEL_CHOICES = {
        "1": "llama3.2",
        "2": "llama3.2:1b",
        "3": "mistral",
        "4": "phi3",
    }

    def __init__(self, interactive: bool = True) -> None:
        """Initialize the wizard.

        Args:
            interactive: Whether to run in interactive mode.
        """
        self.interactive = interactive
        self.state = WizardState()
        self.config: dict[str, Any] = {}
        self._ensure_config_dir()

    def _ensure_config_dir(self) -> None:
        """Ensure the config directory exists."""
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def needs_setup(self) -> bool:
        """Check if setup is needed."""
        return not self.SETUP_COMPLETE_FILE.exists()

    def _get_current_provider(self) -> str | None:
        """Get the currently configured provider from config file."""
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE) as f:
                    config = json.load(f)
                    return config.get("api_provider")
            except (OSError, json.JSONDecodeError):
                pass
        return None

    def load_state(self) -> bool:
        """Load wizard state from file."""
        if self.STATE_FILE.exists():
            try:
                with open(self.STATE_FILE) as f:
                    data = json.load(f)
                    self.state = WizardState.from_dict(data)
                    return True
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("Could not load wizard state: %s", e)
        return False

    def save_state(self) -> None:
        """Save wizard state to file."""
        try:
            with open(self.STATE_FILE, "w") as f:
                json.dump(self.state.to_dict(), f, indent=2)
        except OSError as e:
            logger.warning("Could not save wizard state: %s", e)

    def save_config(self) -> None:
        """Save configuration to file."""
        try:
            with open(self.CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=2)
        except OSError as e:
            logger.warning("Could not save config: %s", e)

    def mark_setup_complete(self) -> None:
        """Mark setup as complete."""
        self.SETUP_COMPLETE_FILE.touch()
        self.state.completed_at = datetime.now()
        self.save_state()

    def _clear_screen(self) -> None:
        """Clear the terminal screen."""
        if self.interactive:
            os.system("clear" if os.name == "posix" else "cls")  # noqa: S605, S607

    def _print_banner(self) -> None:
        """Print the Cortex banner."""
        banner = r"""
       ____           _
      / ___|___  _ __| |_ _____  __
     | |   / _ \| '__| __/ _ \ \/ /
     | |__| (_) | |  | ||  __/>  <
      \____\___/|_|   \__\___/_/\_\

        Linux that understands you.
    """
        print(banner)

    def _print_header(self, title: str) -> None:
        """Print a section header."""
        print("\n" + "=" * 50)
        print(f"  {title}")
        print("=" * 50 + "\n")

    def _prompt(self, message: str, default: str = "") -> str:
        """Prompt for user input."""
        if not self.interactive:
            return default
        try:
            response = input(message).strip()
            return response if response else default
        except (EOFError, KeyboardInterrupt):
            return default

    def _prompt_for_api_key(self, key_type: str) -> str | None:
        """Prompt user for a valid API key.

        Args:
            key_type: Either 'anthropic' or 'openai'.

        Returns:
            The validated API key or None if cancelled.
        """
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

            if not key.strip():
                print("\n⚠ API key cannot be blank. Please enter a valid key.")
                continue

            key = key.strip()
            if not key.startswith(prefix):
                print(f"\n⚠ Invalid key format. {provider_name} keys start with '{prefix}'")
                continue

            return key

    def _save_env_var(self, name: str, value: str) -> None:
        """Save API key to .env file and encrypted storage.

        Saves to ~/.cortex/.env which is detected by api_key_detector (priority #2).

        Args:
            name: Environment variable name.
            value: The API key value.
        """
        # Set for current session
        os.environ[name] = value

        # Save to ~/.cortex/.env (syncs with api_key_detector priority #2)
        if save_key_to_env_file(name, value):
            print(f"✓ API key saved to {get_env_file_path()}")
        else:
            self._save_to_shell_config(name, value)

        # Also save to encrypted storage
        try:
            env_mgr = get_env_manager()
            provider_raw = name.replace("_API_KEY", "")
            provider_display = {
                "OPENAI": "OpenAI",
                "ANTHROPIC": "Anthropic",
            }.get(provider_raw, provider_raw.replace("_", " ").title())

            env_mgr.set_variable(
                app=CORTEX_APP_NAME,
                key=name,
                value=value,
                encrypt=True,
                description=f"API key for {provider_display}",
            )
            logger.info("Saved %s to encrypted storage", name)
        except ImportError:
            logger.warning("cryptography not installed. %s saved to .env only.", name)
        except Exception as e:
            logger.warning("Could not save to encrypted storage: %s", e)

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
        except OSError as e:
            logger.warning("Could not save env var: %s", e)

    def _get_shell_config(self, shell: str) -> Path:
        """Get the shell config file path."""
        home = Path.home()
        configs = {
            "bash": home / ".bashrc",
            "zsh": home / ".zshrc",
            "fish": home / ".config" / "fish" / "config.fish",
        }
        return configs.get(shell, home / ".profile")

    def _verify_api_key(self, provider: str) -> bool:
        """Verify API key with a dry run.

        Args:
            provider: The provider name ('claude' or 'openai').

        Returns:
            True if verification succeeded, False otherwise.
        """
        # Use secrets.choice for cryptographically secure random selection
        random_example = secrets.choice(DRY_RUN_EXAMPLES)
        print(f'\nVerifying setup with dry run: cortex install "{random_example}"...')
        try:
            from cortex.cli import CortexCLI

            cli = CortexCLI()
            result = cli.install(
                random_example, execute=False, dry_run=True, forced_provider=provider
            )
            if result != 0:
                print("\n❌ Dry run failed. Please check your API key and network.")
                return False
            print("\n✅ API key verified successfully!")
            return True
        except Exception as e:
            print(f"\n❌ Error during verification: {e}")
            return False

    def _setup_provider_key(self, provider: str, key_type: str, env_var: str) -> bool:
        """Set up API key for a provider.

        Uses api_key_detector to check if key already exists in any location.

        Args:
            provider: Provider name for display.
            key_type: Key type for validation.
            env_var: Environment variable name.

        Returns:
            True if setup succeeded, False otherwise.
        """
        # Use get_valid_api_key which checks via api_key_detector
        existing_key = get_valid_api_key(env_var, key_type)

        if existing_key:
            print(f"\n✓ Existing {provider} API key detected.")
            # Show where it was found (if api_key_detector available)
            if HAS_API_KEY_DETECTOR:
                print("  (Found via automatic detection)")
            replace = self._prompt("Do you want to replace it with a new key? [y/N]: ", "n")
            if replace.lower() not in ("y", "yes"):
                print("\n✓ Keeping existing API key.")
                # Ensure it's in the environment for this session
                os.environ[env_var] = existing_key
                return True

        if not existing_key:
            print(f"\nNo valid {provider} API key found in any location.")

        key = self._prompt_for_api_key(key_type)
        if key is None:
            print("\nSetup cancelled.")
            return False

        self._save_env_var(env_var, key)
        return True

    def _setup_ollama(self) -> bool:
        """Set up Ollama for local LLM.

        Returns:
            True if setup succeeded, False otherwise.
        """
        has_ollama = shutil.which("ollama") is not None
        if not has_ollama:
            print("\n⚠ Ollama is not installed.")
            print("Install it from: https://ollama.ai")
            return False

        print("\nWhich Ollama model would you like to use?")
        print("  1. llama3.2 (2GB) - Recommended for most users")
        print("  2. llama3.2:1b (1.3GB) - Faster, less RAM")
        print("  3. mistral (4GB) - Alternative quality model")
        print("  4. phi3 (2.3GB) - Microsoft's efficient model")
        print("  5. Custom (enter your own)")

        choice = self._prompt("\nEnter choice [1]: ", default="1")

        if choice == "5":
            model_name = self._prompt("Enter model name: ", default="llama3.2")
        elif choice in self.MODEL_CHOICES:
            model_name = self.MODEL_CHOICES[choice]
        else:
            print(f"Invalid choice '{choice}', using default model llama3.2")
            model_name = "llama3.2"

        print(f"\nPulling {model_name} model (this may take a few minutes)...")
        try:
            subprocess.run(["ollama", "pull", model_name], check=True)  # noqa: S603, S607
            print("\n✓ Model ready!")
        except subprocess.CalledProcessError:
            print(f"\n⚠ Could not pull model - run later: ollama pull {model_name}")

        self.config["ollama_model"] = model_name
        return True

    def run(self) -> bool:
        """Run the main wizard flow.

        Returns:
            True if setup completed successfully, False otherwise.
        """
        self._clear_screen()
        self._print_banner()

        # Load environment from ~/.cortex/.env if exists
        env_path = get_env_file_path()
        try:
            from dotenv import load_dotenv

            load_dotenv(dotenv_path=env_path, override=False)
        except ImportError:
            pass

        # Detect available providers (uses api_key_detector if available)
        available_providers = detect_available_providers()
        has_ollama = shutil.which("ollama") is not None
        current_provider = self._get_current_provider()
        is_first_run = current_provider is None

        print("\nSelect your preferred LLM provider:\n")

        option_num = 1
        provider_map: dict[str, str] = {}

        # Show "skip" option only if already configured
        if not is_first_run and current_provider and current_provider != "none":
            current_name = self.PROVIDER_NAMES.get(current_provider, current_provider)
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
        choice = self._prompt(
            f"\nChoose a provider [{valid_choices[0]}-{valid_choices[-1]}]: ",
            default="1",
        )

        provider = provider_map.get(choice)
        if not provider:
            print(f"Invalid choice. Enter {valid_choices[0]}-{valid_choices[-1]}.")
            return False

        if provider == "skip_reconfig":
            current_name = self.PROVIDER_NAMES.get(current_provider or "", current_provider)
            print(f"\n✓ Keeping current provider: {current_name}")
            self.mark_setup_complete()
            return True

        if provider == "anthropic":
            if not self._setup_provider_key("Anthropic", "anthropic", "ANTHROPIC_API_KEY"):
                return False
            self.config["api_provider"] = "anthropic"
            self.config["api_key_configured"] = True
            if not self._verify_api_key("claude"):
                return False

        elif provider == "openai":
            if not self._setup_provider_key("OpenAI", "openai", "OPENAI_API_KEY"):
                return False
            self.config["api_provider"] = "openai"
            self.config["api_key_configured"] = True
            if not self._verify_api_key("openai"):
                return False

        elif provider == "ollama":
            if not self._setup_ollama():
                return False
            self.config["api_provider"] = "ollama"
            self.config["api_key_configured"] = True

        self.save_config()
        self.mark_setup_complete()

        print(f"\n[✔] Setup complete! Provider '{provider}' is ready for AI workloads.")
        print("You can rerun this wizard anytime with: cortex wizard")
        return True

    def _detect_hardware(self) -> dict[str, Any]:
        """Detect system hardware."""
        try:
            from dataclasses import asdict

            from cortex.hardware_detection import detect_hardware

            info = detect_hardware()
            return asdict(info)
        except Exception as e:
            logger.warning("Hardware detection failed: %s", e)
            return {
                "cpu": {"vendor": "unknown", "model": "unknown"},
                "gpu": [],
                "memory": {"total_gb": 0},
            }

    def _step_welcome(self) -> StepResult:
        """Welcome step - legacy method for tests."""
        self._print_banner()
        return StepResult(success=True)

    def _step_api_setup(self) -> StepResult:
        """API key configuration step."""
        self._clear_screen()
        self._print_header("Step 1: API Configuration")

        existing_claude = get_valid_api_key("ANTHROPIC_API_KEY", "anthropic")
        existing_openai = get_valid_api_key("OPENAI_API_KEY", "openai")

        claude_status = " ✓ (key found)" if existing_claude else ""
        openai_status = " ✓ (key found)" if existing_openai else ""

        print(
            f"""
Cortex uses AI to understand your commands. You can use:

  1. Claude API (Anthropic){claude_status} - Recommended
  2. OpenAI API{openai_status}
  3. Local LLM (Ollama) - Free, runs on your machine
  4. Skip for now (limited functionality)
"""
        )

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
        if choice == "2":
            if existing_openai:
                print("\n✓ Using existing OpenAI API key!")
                self.config["api_provider"] = "openai"
                self.config["api_key_configured"] = True
                return StepResult(success=True, data={"api_provider": "openai"})
            return self._setup_openai_api()
        if choice == "3":
            return self._setup_ollama_legacy()

        print("\n⚠ Running without AI - you'll only have basic apt functionality")
        return StepResult(success=True, data={"api_provider": "none"})

    def _setup_claude_api(self) -> StepResult:
        """Set up Claude API (legacy)."""
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
        """Set up OpenAI API (legacy)."""
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

    def _setup_ollama_legacy(self) -> StepResult:
        """Set up Ollama for local LLM (legacy)."""
        print("\nChecking for Ollama...")

        if not shutil.which("ollama"):
            print("\nOllama is not installed. Install it with:")
            print("  curl -fsSL https://ollama.ai/install.sh | sh")

            install = self._prompt("\nInstall Ollama now? [y/N]: ", default="n")

            if install.lower() == "y":
                try:
                    subprocess.run(
                        "curl -fsSL https://ollama.ai/install.sh | sh",
                        shell=True,  # noqa: S602
                        check=True,
                    )
                    print("\n✓ Ollama installed!")
                except subprocess.CalledProcessError:
                    print("\n✗ Failed to install Ollama")
                    return StepResult(success=True, data={"api_provider": "none"})

        if self._setup_ollama():
            self.config["api_provider"] = "ollama"
            return StepResult(success=True, data={"api_provider": "ollama"})
        return StepResult(success=True, data={"api_provider": "none"})

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

    def _generate_completion_script(self, shell: str) -> str:
        """Generate shell completion script for the given shell.

        Args:
            shell: Shell type ('bash', 'zsh', 'fish', etc.)

        Returns:
            Completion script as string
        """
        if shell == "bash":
            return """# Bash completion for cortex
_cortex_completion() {
    local cur prev words cword
    _init_completion || return

    # Basic command completion
    COMPREPLY=($(compgen -W "install search info doctor" -- "$cur"))
} && complete -F _cortex_completion cortex"""
        elif shell == "zsh":
            return """# Zsh completion for cortex
_cortex() {
    local -a commands
    commands=(
        'install:install packages'
        'search:search for packages'
        'info:show package information'
        'doctor:diagnose system issues'
    )
    _describe 'command' commands
}
compdef _cortex cortex"""
        elif shell == "fish":
            return """# Fish completion for cortex
complete -c cortex -f
complete -c cortex -a 'install' -d 'Install packages'
complete -c cortex -a 'search' -d 'Search for packages'
complete -c cortex -a 'info' -d 'Show package information'
complete -c cortex -a 'doctor' -d 'Diagnose system issues'"""
        else:
            return f"# No completion available for shell: {shell}"


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
