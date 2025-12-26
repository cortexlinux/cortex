#!/usr/bin/env python3
"""
Ollama Provider for Cortex Linux
Enables local LLM support for privacy-first, offline package management.

Features:
- Auto-detect Ollama installation
- Smart model selection (prefers code-focused models)
- Streaming responses
- Zero data sent to cloud
- Fully offline capable

Author: Cortex Linux Team
License: Apache 2.0
"""

import json
import logging
import os
import shutil
import subprocess
import time
from collections.abc import Generator
from typing import Any

import requests

logger = logging.getLogger(__name__)


class OllamaProvider:
    """
    Provider for local LLM inference using Ollama.

    Ollama enables running large language models locally without API keys.
    This provides privacy, offline capability, and zero cloud costs.
    """

    # Preferred models in order of preference (code-focused models first)
    PREFERRED_MODELS = [
        "deepseek-coder-v2:16b",  # Excellent for code and system tasks
        "codellama:13b",  # Meta's code-specialized model
        "deepseek-coder:6.7b",  # Good balance of speed and quality
        "llama3:8b",  # General purpose, very capable
        "mistral:7b",  # Fast and efficient
        "phi3:mini",  # Lightweight, good for quick tasks
    ]

    # Fallback models if preferred ones aren't available
    FALLBACK_MODELS = [
        "llama3:8b",
        "mistral:7b",
        "phi3:mini",
    ]

    DEFAULT_OLLAMA_URL = "http://localhost:11434"

    def __init__(
        self,
        base_url: str | None = None,
        timeout: int = 300,
        auto_pull: bool = True,
    ):
        """
        Initialize Ollama provider.

        Args:
            base_url: Ollama API URL (defaults to localhost:11434)
            timeout: Request timeout in seconds
            auto_pull: Automatically pull models if not available
        """
        self.base_url = base_url or os.getenv("OLLAMA_HOST", self.DEFAULT_OLLAMA_URL)
        self.timeout = timeout
        self.auto_pull = auto_pull
        self._available_models: list[str] | None = None
        self._selected_model: str | None = None

    @staticmethod
    def is_installed() -> bool:
        """
        Check if Ollama is installed on the system.

        Returns:
            True if Ollama is available, False otherwise
        """
        return shutil.which("ollama") is not None

    @staticmethod
    def install_ollama() -> bool:
        """
        Install Ollama on the system.

        Returns:
            True if installation succeeded, False otherwise
        """
        if OllamaProvider.is_installed():
            logger.info("✅ Ollama already installed")
            return True

        logger.info("📦 Installing Ollama...")
        try:
            # Official Ollama installation script
            result = subprocess.run(
                ["curl", "-fsSL", "https://ollama.com/install.sh"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                logger.error(f"Failed to download Ollama installer: {result.stderr}")
                return False

            # Execute installation script
            install_result = subprocess.run(
                ["sh", "-c", result.stdout],
                capture_output=True,
                text=True,
                timeout=300,
            )

            if install_result.returncode == 0:
                logger.info("✅ Ollama installed successfully")
                # Start Ollama service
                subprocess.run(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                time.sleep(2)  # Give service time to start
                return True
            else:
                logger.error(f"Ollama installation failed: {install_result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Error installing Ollama: {e}")
            return False

    def is_running(self) -> bool:
        """
        Check if Ollama service is running.

        Returns:
            True if service is accessible, False otherwise
        """
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def start_service(self) -> bool:
        """
        Start Ollama service if not running.

        Returns:
            True if service started successfully, False otherwise
        """
        if self.is_running():
            return True

        if not self.is_installed():
            logger.warning("Ollama not installed, attempting installation...")
            if not self.install_ollama():
                return False

        logger.info("🚀 Starting Ollama service...")
        try:
            # Start Ollama in background
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            # Wait for service to be ready
            for i in range(10):
                time.sleep(1)
                if self.is_running():
                    logger.info("✅ Ollama service started")
                    return True

            logger.error("Ollama service failed to start")
            return False

        except Exception as e:
            logger.error(f"Error starting Ollama service: {e}")
            return False

    def get_available_models(self) -> list[str]:
        """
        Get list of models available locally.

        Returns:
            List of model names
        """
        if self._available_models is not None:
            return self._available_models

        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            response.raise_for_status()

            data = response.json()
            self._available_models = [model["name"] for model in data.get("models", [])]
            return self._available_models

        except Exception as e:
            logger.error(f"Error fetching available models: {e}")
            return []

    def select_best_model(self) -> str | None:
        """
        Select the best available model for Cortex tasks.

        Prefers code-focused models, falls back to general models.

        Returns:
            Model name or None if no models available
        """
        if self._selected_model:
            return self._selected_model

        available = self.get_available_models()

        if not available:
            logger.warning("No models available locally")
            return None

        # Try preferred models first
        for model in self.PREFERRED_MODELS:
            if model in available:
                self._selected_model = model
                logger.info(f"✅ Selected model: {model}")
                return model

        # Fall back to any available model
        if available:
            self._selected_model = available[0]
            logger.info(f"⚠️  Using fallback model: {available[0]}")
            return available[0]

        return None

    def pull_model(self, model_name: str) -> bool:
        """
        Pull a model from Ollama registry.

        Args:
            model_name: Name of model to pull

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"📥 Pulling model: {model_name}")

        try:
            response = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model_name},
                stream=True,
                timeout=self.timeout,
            )
            response.raise_for_status()

            # Show progress
            for line in response.iter_lines():
                if line:
                    data = json.loads(line)
                    if "status" in data:
                        logger.info(f"  {data['status']}")

            logger.info(f"✅ Model {model_name} pulled successfully")
            self._available_models = None  # Clear cache
            return True

        except Exception as e:
            logger.error(f"Error pulling model {model_name}: {e}")
            return False

    def ensure_model_available(self) -> str | None:
        """
        Ensure a suitable model is available, pulling one if necessary.

        Returns:
            Model name or None if setup failed
        """
        model = self.select_best_model()

        if model:
            return model

        if not self.auto_pull:
            logger.error("No models available and auto-pull disabled")
            return None

        # Try to pull a preferred model
        for model_name in self.FALLBACK_MODELS:
            logger.info(f"Attempting to pull fallback model: {model_name}")
            if self.pull_model(model_name):
                self._selected_model = model_name
                return model_name

        logger.error("Failed to set up any model")
        return None

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> dict[str, Any] | Generator[dict[str, Any], None, None]:
        """
        Generate completion using local Ollama model.

        Args:
            messages: Chat messages in OpenAI format
            model: Specific model to use (auto-selected if None)
            temperature: Sampling temperature
            max_tokens: Maximum response length
            stream: Enable streaming responses

        Returns:
            Response dict or generator if streaming
        """
        # Ensure service is running
        if not self.is_running():
            if not self.start_service():
                raise RuntimeError("Failed to start Ollama service")

        # Select model
        if model is None:
            model = self.ensure_model_available()
            if model is None:
                raise RuntimeError("No model available")

        # Convert messages to Ollama format
        prompt = self._messages_to_prompt(messages)

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "temperature": temperature,
                    "options": {
                        "num_predict": max_tokens,
                    },
                    "stream": stream,
                },
                stream=stream,
                timeout=self.timeout,
            )
            response.raise_for_status()

            if stream:
                return self._stream_response(response)
            else:
                return response.json()

        except Exception as e:
            logger.error(f"Error during completion: {e}")
            raise

    def _messages_to_prompt(self, messages: list[dict[str, str]]) -> str:
        """
        Convert OpenAI-style messages to a single prompt.

        Args:
            messages: List of message dicts with 'role' and 'content'

        Returns:
            Formatted prompt string
        """
        prompt_parts = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                prompt_parts.append(f"System: {content}\n")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}\n")
            else:  # user
                prompt_parts.append(f"User: {content}\n")

        prompt_parts.append("Assistant: ")
        return "\n".join(prompt_parts)

    def _stream_response(
        self, response: requests.Response
    ) -> Generator[dict[str, Any], None, None]:
        """
        Stream response chunks.

        Args:
            response: Streaming response from Ollama

        Yields:
            Response chunk dicts
        """
        for line in response.iter_lines():
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse streaming response: {line}")
                    continue

    def get_model_info(self, model_name: str) -> dict[str, Any] | None:
        """
        Get information about a specific model.

        Args:
            model_name: Name of the model

        Returns:
            Model info dict or None if not found
        """
        try:
            response = requests.post(
                f"{self.base_url}/api/show", json={"name": model_name}, timeout=10
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Error fetching model info: {e}")
            return None
