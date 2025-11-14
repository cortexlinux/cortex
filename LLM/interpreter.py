"""Natural language to shell command interpreter backed by multiple LLMs."""

import os
import json
from typing import List, Optional, Dict, Any
from enum import Enum


class APIProvider(Enum):
    """Supported large-language-model providers for command generation."""

    CLAUDE = "claude"
    OPENAI = "openai"
    KIMI = "kimi"
    FAKE = "fake"


class CommandInterpreter:
    """Translate natural language intents into shell commands via LLMs."""

    def __init__(
        self,
        api_key: str,
        provider: str = "openai",
        model: Optional[str] = None
    ):
        self.api_key = api_key
        self.provider = APIProvider(provider.lower())
        
        if model:
            self.model = model
        else:
            self.model = self._default_model()
        
        self._initialize_client()
    
    def _initialize_client(self):
        """Instantiate the SDK client for the selected provider."""
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
        elif self.provider == APIProvider.KIMI:
            try:
                import requests  # type: ignore
            except ImportError as exc:
                raise ImportError("Requests package not installed. Run: pip install requests") from exc

            self.client = requests
            self._kimi_base_url = os.environ.get("KIMI_API_BASE_URL", "https://api.moonshot.cn")
        elif self.provider == APIProvider.FAKE:
            # Fake provider is used for deterministic offline or integration tests.
            self.client = None
    
    def _get_system_prompt(self) -> str:
        """Return the base instructions shared across all provider calls."""
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
    
    def _call_openai(self, user_input: str) -> List[str]:
        """Call the OpenAI Chat Completions API and parse the response."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": user_input}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content.strip()
            return self._parse_commands(content)
        except Exception as e:
            raise RuntimeError(f"OpenAI API call failed: {str(e)}")
    
    def _call_claude(self, user_input: str) -> List[str]:
        """Call the Anthropic Messages API and parse the response."""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0.3,
                system=self._get_system_prompt(),
                messages=[
                    {"role": "user", "content": user_input}
                ]
            )
            
            content = response.content[0].text.strip()
            return self._parse_commands(content)
        except Exception as e:
            raise RuntimeError(f"Claude API call failed: {str(e)}")

    def _call_kimi(self, user_input: str) -> List[str]:
        """Call the Kimi K2 HTTP API and parse the response body."""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._get_system_prompt()},
                {"role": "user", "content": user_input},
            ],
            "temperature": 0.3,
            "max_tokens": 1000,
        }

        try:
            response = self.client.post(
                f"{self._kimi_base_url.rstrip('/')}/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                raise RuntimeError("Kimi API returned no choices")
            content = choices[0].get("message", {}).get("content", "").strip()
            if not content:
                raise RuntimeError("Kimi API returned empty content")
            return self._parse_commands(content)
        except Exception as exc:
            raise RuntimeError(f"Kimi API call failed: {str(exc)}") from exc

    def _call_fake(self, user_input: str) -> List[str]:
        """Return predetermined commands without hitting a real provider."""

        payload = os.environ.get("CORTEX_FAKE_COMMANDS")
        if payload:
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ValueError("CORTEX_FAKE_COMMANDS must contain valid JSON") from exc
            if not isinstance(data, dict) or "commands" not in data:
                raise ValueError("CORTEX_FAKE_COMMANDS must define a 'commands' list")
            return self._parse_commands(payload)

        safe_defaults = {
            "docker": [
                "echo Updating package cache",
                "echo Installing docker packages",
                "echo Enabling docker service",
            ],
            "python": [
                "echo Installing Python",
                "echo Setting up virtual environment",
                "echo Installing pip packages",
            ],
        }

        for key, commands in safe_defaults.items():
            if key in user_input.lower():
                return commands

        return ["echo Preparing environment", "echo Completed simulation"]
    
    def _parse_commands(self, content: str) -> List[str]:
        """Parse the JSON payload returned by an LLM into command strings."""
        try:
            if content.startswith("```json"):
                content = content.split("```json")[1].split("```")[0].strip()
            elif content.startswith("```"):
                content = content.split("```")[1].split("```")[0].strip()
            
            data = json.loads(content)
            commands = data.get("commands", [])
            
            if not isinstance(commands, list):
                raise ValueError("Commands must be a list")
            
            return [cmd for cmd in commands if cmd and isinstance(cmd, str)]
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(f"Failed to parse LLM response: {str(e)}")
    
    def _validate_commands(self, commands: List[str]) -> List[str]:
        """Filter the provided commands to remove obviously dangerous patterns."""
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
    
    def parse(self, user_input: str, validate: bool = True) -> List[str]:
        """Parse the user's request into a list of shell commands."""
        if not user_input or not user_input.strip():
            raise ValueError("User input cannot be empty")
        
        if self.provider == APIProvider.OPENAI:
            commands = self._call_openai(user_input)
        elif self.provider == APIProvider.CLAUDE:
            commands = self._call_claude(user_input)
        elif self.provider == APIProvider.KIMI:
            commands = self._call_kimi(user_input)
        elif self.provider == APIProvider.FAKE:
            commands = self._call_fake(user_input)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
        
        if validate:
            commands = self._validate_commands(commands)
        
        return commands
    
    def parse_with_context(
        self,
        user_input: str,
        system_info: Optional[Dict[str, Any]] = None,
        validate: bool = True
    ) -> List[str]:
        """Parse a request while appending structured system context."""
        context = ""
        if system_info:
            context = f"\n\nSystem context: {json.dumps(system_info)}"
        
        enriched_input = user_input + context
        return self.parse(enriched_input, validate=validate)

    def _default_model(self) -> str:
        """Return the default model identifier for the active provider."""

        if self.provider == APIProvider.OPENAI:
            return "gpt-4"
        if self.provider == APIProvider.CLAUDE:
            return "claude-3-5-sonnet-20241022"
        if self.provider == APIProvider.KIMI:
            return os.environ.get("KIMI_DEFAULT_MODEL", "kimi-k2")
        return "fake-local-model"
