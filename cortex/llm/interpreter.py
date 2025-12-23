import json
import os
import sqlite3
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from cortex.semantic_cache import SemanticCache


class APIProvider(Enum):
    CLAUDE = "claude"
    OPENAI = "openai"
    OLLAMA = "ollama"
    FAKE = "fake"


class CommandInterpreter:
    """Interprets natural language commands into executable shell commands using LLM APIs.

    Supports multiple providers (OpenAI, Claude, Ollama) with optional semantic caching
    and offline mode for cached responses.
    """

    def __init__(
        self,
        api_key: str,
        provider: str = "openai",
        model: str | None = None,
        offline: bool = False,
        cache: Optional["SemanticCache"] = None,
    ):
        """Initialize the command interpreter.

        Args:
            api_key: API key for the LLM provider
            provider: Provider name ("openai", "claude", or "ollama")
            model: Optional model name override
            offline: If True, only use cached responses
            cache: Optional SemanticCache instance for response caching
        """
        self.api_key = api_key
        self.provider = APIProvider(provider.lower())
        self.offline = offline

        if cache is None:
            try:
                from cortex.semantic_cache import SemanticCache

                self.cache: SemanticCache | None = SemanticCache()
            except (ImportError, OSError):
                # Cache initialization can fail due to missing dependencies or permissions
                self.cache = None
        else:
            self.cache = cache

        if model:
            self.model = model
        else:
            if self.provider == APIProvider.OPENAI:
                self.model = "gpt-4"
            elif self.provider == APIProvider.CLAUDE:
                self.model = "claude-sonnet-4-20250514"
            elif self.provider == APIProvider.OLLAMA:
                self.model = "llama3.2"  # Default Ollama model
            elif self.provider == APIProvider.FAKE:
                self.model = "fake"  # Fake provider doesn't use a real model

        self._initialize_client()

    def _initialize_client(self):
        if self.provider == APIProvider.OPENAI:
            try:
                from openai import OpenAI

                self.client = OpenAI(api_key=self.api_key)
            except ImportError:
                raise ImportError("OpenAI package not installed. Run: pip install openai")
        elif self.provider == APIProvider.CLAUDE:
            try:
                from anthropic import Anthropic

                self.client = Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError("Anthropic package not installed. Run: pip install anthropic")
        elif self.provider == APIProvider.OLLAMA:
            # Ollama uses local HTTP API, no special client needed
            self.ollama_url = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
            self.client = None  # Will use requests
        elif self.provider == APIProvider.FAKE:
            # Fake provider uses predefined commands from environment
            self.client = None  # No client needed for fake provider

    def _get_system_prompt(self) -> str:
        return """You are a Linux system command expert. Convert natural language requests into safe, validated bash commands.

    Rules:
    1. Return ONLY a JSON array of commands
    2. Each command must be a safe, executable bash command
    3. Commands should be atomic and sequential
    4. Avoid destructive operations without explicit user confirmation
    5. Use package managers appropriate for Debian/Ubuntu systems (apt)
    6. Include necessary privilege escalation (sudo) when required
    7. Validate command syntax before returning

    Format:
    {"commands": ["command1", "command2", ...]}

    Example request: "install docker with nvidia support"
    Example response: {"commands": ["sudo apt update", "sudo apt install -y docker.io", "sudo apt install -y nvidia-docker2", "sudo systemctl restart docker"]}"""

    def _extract_intent_ollama(self, user_input: str) -> dict:
        import urllib.error
        import urllib.request

        prompt = f"""
    {self._get_intent_prompt()}

    User request:
    {user_input}
    """

        data = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2},
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            f"{self.ollama_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                raw = json.loads(response.read().decode("utf-8"))
                text = raw.get("response", "")
                return self._parse_intent_from_text(text)

        except Exception:
            # True failure → unknown intent
            return {
                "action": "unknown",
                "domain": "unknown",
                "description": "Failed to extract intent",
                "ambiguous": True,
                "confidence": 0.0,
            }

    def _get_intent_prompt(self) -> str:
        return """You are an intent extraction engine for a Linux package manager.

        Given a user request, extract intent as JSON with:
        - action: install | remove | update | unknown
        - domain: short category (machine_learning, web_server, python_dev, containerization, unknown)
        - description: brief explanation of what the user wants
        - ambiguous: true/false
        - confidence: float between 0 and 1
        Also determine the most appropriate install_mode:
        - system (apt, requires sudo)
        - python (pip, virtualenv)
        - mixed

        Rules:
        - Do NOT suggest commands
        - Do NOT list packages
        - If unsure, set ambiguous=true
        - Respond ONLY in JSON with the following fields:
        - action: install | remove | update | unknown
        - domain: short category describing the request
        - install_mode: system | python | mixed
        - description: brief explanation
        - ambiguous: true or false
        - confidence: number between 0 and 1
        - Use install_mode = "python" for Python libraries, data science, or machine learning.
        - Use install_mode = "system" for system software like docker, nginx, kubernetes.
        - Use install_mode = "mixed" if both are required.

        Format:
        {
        "action": "...",
        "domain": "...",
        "install_mode" "..."
        "description": "...",
        "ambiguous": true/false,
        "confidence": 0.0
        }
        """

    def _call_openai(self, user_input: str) -> list[str]:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": user_input},
                ],
                temperature=0.3,
                max_tokens=1000,
            )

            content = response.choices[0].message.content.strip()
            return self._parse_commands(content)
        except Exception as e:
            raise RuntimeError(f"OpenAI API call failed: {str(e)}")

    def _extract_intent_openai(self, user_input: str) -> dict:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self._get_intent_prompt()},
                {"role": "user", "content": user_input},
            ],
            temperature=0.2,
            max_tokens=300,
        )

        content = response.choices[0].message.content.strip()
        return json.loads(content)

    def _parse_intent_from_text(self, text: str) -> dict:
        """
        Extract intent JSON from loose LLM output.
        No semantic assumptions.
        """
        # Try to locate JSON block
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                parsed = json.loads(text[start : end + 1])

                # Minimal validation (structure only)
                for key in ["action", "domain", "install_mode", "ambiguous", "confidence"]:
                    if key not in parsed:
                        raise ValueError("Missing intent field")

                return parsed
        except Exception:
            pass

        # If parsing fails, do NOT guess meaning
        return {
            "action": "unknown",
            "domain": "unknown",
            "description": "Unstructured intent output",
            "ambiguous": True,
            "confidence": 0.0,
        }

    def _call_claude(self, user_input: str) -> list[str]:
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0.3,
                system=self._get_system_prompt(),
                messages=[{"role": "user", "content": user_input}],
            )

            content = response.content[0].text.strip()
            return self._parse_commands(content)
        except Exception as e:
            raise RuntimeError(f"Claude API call failed: {str(e)}")

    def _call_ollama(self, user_input: str) -> list[str]:
        """Call local Ollama instance for offline/local inference"""
        import urllib.error
        import urllib.request

        try:
            url = f"{self.ollama_url}/api/generate"
            prompt = f"{self._get_system_prompt()}\n\nUser request: {user_input}"

            data = json.dumps(
                {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3},
                }
            ).encode("utf-8")

            req = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"}
            )

            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))
                content = result.get("response", "").strip()
                return self._parse_commands(content)

        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama not available at {self.ollama_url}: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Ollama API call failed: {str(e)}")

    def _call_fake(self, user_input: str) -> list[str]:
        """Return predefined fake commands from environment for testing."""
        fake_commands_env = os.environ.get("CORTEX_FAKE_COMMANDS")
        if not fake_commands_env:
            raise RuntimeError("CORTEX_FAKE_COMMANDS environment variable not set")

        try:
            data = json.loads(fake_commands_env)
            commands = data.get("commands", [])
            if not isinstance(commands, list):
                raise ValueError("Commands must be a list in CORTEX_FAKE_COMMANDS")
            return [cmd for cmd in commands if cmd and isinstance(cmd, str)]
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse CORTEX_FAKE_COMMANDS: {str(e)}")

    def _parse_commands(self, content: str) -> list[str]:
        """
        Robust command parser.
        Handles strict JSON (OpenAI/Claude) and loose output (Ollama).
        """
        try:
            # Remove code fences
            if "```" in content:
                parts = content.split("```")
                content = next((p for p in parts if "commands" in p), content)

            # Attempt to isolate JSON
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                json_blob = content[start : end + 1]
            else:
                json_blob = content

            # First attempt: strict JSON
            data = json.loads(json_blob)
            commands = data.get("commands", [])

            if isinstance(commands, list):
                return [c for c in commands if isinstance(c, str) and c.strip()]

        except Exception:
            pass  # fall through to heuristic extraction

        # 🔁 Fallback: heuristic extraction (Ollama-safe)
        commands = []
        for line in content.splitlines():
            line = line.strip()

            # crude but safe: common install commands
            if line.startswith(("sudo ", "apt ", "apt-get ")):
                commands.append(line)

        if commands:
            return commands

        raise ValueError("Failed to parse LLM response: no valid commands found")

    def _validate_commands(self, commands: list[str]) -> list[str]:
        dangerous_patterns = [
            "rm -rf /",
            "dd if=",
            "mkfs.",
            "> /dev/sda",
            "fork bomb",
            ":(){ :|:& };:",
        ]

        validated = []
        for cmd in commands:
            cmd_lower = cmd.lower()
            if any(pattern in cmd_lower for pattern in dangerous_patterns):
                continue
            validated.append(cmd)

        return validated

    def parse(self, user_input: str, validate: bool = True) -> list[str]:
        """Parse natural language input into shell commands.

        Args:
            user_input: Natural language description of desired action
            validate: If True, validate commands for dangerous patterns

        Returns:
            List of shell commands to execute

        Raises:
            ValueError: If input is empty
            RuntimeError: If offline mode is enabled and no cached response exists
        """
        if not user_input or not user_input.strip():
            raise ValueError("User input cannot be empty")

        cache_system_prompt = (
            self._get_system_prompt() + f"\n\n[cortex-cache-validate={bool(validate)}]"
        )

        if self.cache is not None:
            cached = self.cache.get_commands(
                prompt=user_input,
                provider=self.provider.value,
                model=self.model,
                system_prompt=cache_system_prompt,
            )
            if cached is not None:
                return cached

        if self.offline:
            raise RuntimeError("Offline mode: no cached response available for this request")

        if self.provider == APIProvider.OPENAI:
            commands = self._call_openai(user_input)
        elif self.provider == APIProvider.CLAUDE:
            commands = self._call_claude(user_input)
        elif self.provider == APIProvider.OLLAMA:
            commands = self._call_ollama(user_input)
        elif self.provider == APIProvider.FAKE:
            commands = self._call_fake(user_input)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

        if validate:
            commands = self._validate_commands(commands)

        if self.cache is not None and commands:
            try:
                self.cache.put_commands(
                    prompt=user_input,
                    provider=self.provider.value,
                    model=self.model,
                    system_prompt=cache_system_prompt,
                    commands=commands,
                )
            except (OSError, sqlite3.Error):
                # Silently fail cache writes - not critical for operation
                pass

        return commands

    def parse_with_context(
        self, user_input: str, system_info: dict[str, Any] | None = None, validate: bool = True
    ) -> list[str]:
        context = ""
        if system_info:
            context = f"\n\nSystem context: {json.dumps(system_info)}"

        enriched_input = user_input + context
        return self.parse(enriched_input, validate=validate)

    def _estimate_confidence(self, user_input: str, domain: str) -> float:
        """
        Estimate confidence score without hardcoding meaning.
        Uses simple linguistic signals.
        """
        score = 0.0
        text = user_input.lower()

        # Signal 1: length (more detail → more confidence)
        if len(text.split()) >= 3:
            score += 0.3
        else:
            score += 0.1

        # Signal 2: install intent words
        install_words = {"install", "setup", "set up", "configure"}
        if any(word in text for word in install_words):
            score += 0.3

        # Signal 3: vague words reduce confidence
        vague_words = {"something", "stuff", "things", "etc"}
        if any(word in text for word in vague_words):
            score -= 0.2

        # Signal 4: unknown domain penalty
        if domain == "unknown":
            score -= 0.1

        # Clamp to [0.0, 1.0]
        # Ensure some minimal confidence for valid text
        score = max(score, 0.2)

        return round(min(1.0, score), 2)

    def extract_intent(self, user_input: str) -> dict:
        if not user_input or not user_input.strip():
            raise ValueError("User input cannot be empty")

        if self.provider == APIProvider.OPENAI:
            return self._extract_intent_openai(user_input)
        elif self.provider == APIProvider.CLAUDE:
            raise NotImplementedError("Intent extraction not yet implemented for Claude")
        elif self.provider == APIProvider.OLLAMA:
            return self._extract_intent_ollama(user_input)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
