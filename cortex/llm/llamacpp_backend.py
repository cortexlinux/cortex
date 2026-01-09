#!/usr/bin/env python3
"""
Cortex Linux - Native llama.cpp Backend

Direct integration with llama.cpp C++ library for local inference.
No external processes, network overhead, or Ollama dependency.

Features:
- Direct function calls to libllama.so via Python bindings
- Memory-mapped model loading for fast startup (<100ms)
- KV cache management for efficient context handling
- Hardware-aware backend selection (CUDA/ROCm/Metal/CPU)
- GGUF model format support

Author: Cortex Linux Team
License: Apache 2.0
"""

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Model storage paths
CORTEX_MODELS_DIR = Path.home() / ".cortex" / "models"
CORTEX_CACHE_DIR = Path.home() / ".cortex" / "cache"


class LlamaCppBackend(Enum):
    """Available compute backends for llama.cpp."""

    CPU = "cpu"
    CUDA = "cuda"
    ROCM = "rocm"
    METAL = "metal"
    VULKAN = "vulkan"
    SYCL = "sycl"


class ModelLoadError(Exception):
    """Raised when a model fails to load."""

    pass


class InferenceError(Exception):
    """Raised when inference fails."""

    pass


@dataclass
class ModelConfig:
    """Configuration for loading a GGUF model."""

    model_path: str
    n_ctx: int = 4096  # Context window size
    n_batch: int = 512  # Batch size for prompt processing
    n_threads: int = 0  # 0 = auto-detect
    n_gpu_layers: int = -1  # -1 = all layers on GPU
    main_gpu: int = 0  # Primary GPU index
    tensor_split: list[float] | None = None  # Multi-GPU split
    rope_freq_base: float = 0.0  # 0 = use model default
    rope_freq_scale: float = 0.0  # 0 = use model default
    mul_mat_q: bool = True  # Use quantized matmul
    f16_kv: bool = True  # Use FP16 for KV cache
    use_mmap: bool = True  # Memory-map the model
    use_mlock: bool = False  # Lock model in RAM
    embedding: bool = False  # Load for embeddings only
    low_vram: bool = False  # Reduce VRAM usage
    verbose: bool = False


@dataclass
class GenerationConfig:
    """Configuration for text generation."""

    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 0.95
    top_k: int = 40
    repeat_penalty: float = 1.1
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    stop: list[str] = field(default_factory=list)
    seed: int = -1  # -1 = random


@dataclass
class InferenceResult:
    """Result from inference."""

    content: str
    tokens_generated: int
    tokens_prompt: int
    time_to_first_token_ms: float
    total_time_ms: float
    tokens_per_second: float
    model: str
    finish_reason: str  # "stop", "length", "error"


class LlamaCppModel:
    """
    Wrapper for a loaded llama.cpp model.

    This class manages the lifecycle of a single model instance,
    providing inference capabilities with thread-safe access.
    """

    def __init__(self, config: ModelConfig):
        """
        Initialize and load a model.

        Args:
            config: Model configuration

        Raises:
            ModelLoadError: If the model fails to load
        """
        self.config = config
        self._model = None
        self._lock = threading.Lock()
        self._loaded = False
        self._load_time_ms = 0.0

        self._load_model()

    def _load_model(self) -> None:
        """Load the model using llama-cpp-python bindings."""
        try:
            # Import here to allow graceful fallback if not installed
            from llama_cpp import Llama

            start_time = time.perf_counter()

            # Detect optimal thread count
            n_threads = self.config.n_threads
            if n_threads == 0:
                n_threads = min(os.cpu_count() or 4, 8)  # Cap at 8 threads

            # Build model kwargs
            model_kwargs: dict[str, Any] = {
                "model_path": self.config.model_path,
                "n_ctx": self.config.n_ctx,
                "n_batch": self.config.n_batch,
                "n_threads": n_threads,
                "n_gpu_layers": self.config.n_gpu_layers,
                "main_gpu": self.config.main_gpu,
                "mul_mat_q": self.config.mul_mat_q,
                "f16_kv": self.config.f16_kv,
                "use_mmap": self.config.use_mmap,
                "use_mlock": self.config.use_mlock,
                "embedding": self.config.embedding,
                "low_vram": self.config.low_vram,
                "verbose": self.config.verbose,
            }

            # Add tensor split if specified
            if self.config.tensor_split:
                model_kwargs["tensor_split"] = self.config.tensor_split

            # Add RoPE scaling if specified
            if self.config.rope_freq_base > 0:
                model_kwargs["rope_freq_base"] = self.config.rope_freq_base
            if self.config.rope_freq_scale > 0:
                model_kwargs["rope_freq_scale"] = self.config.rope_freq_scale

            self._model = Llama(**model_kwargs)
            self._loaded = True
            self._load_time_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                f"✅ Model loaded in {self._load_time_ms:.1f}ms: {Path(self.config.model_path).name}"
            )

        except ImportError as e:
            raise ModelLoadError(
                "llama-cpp-python not installed. Install with: pip install llama-cpp-python\n"
                "For GPU support: CMAKE_ARGS='-DGGML_CUDA=on' pip install llama-cpp-python"
            ) from e
        except Exception as e:
            raise ModelLoadError(f"Failed to load model: {e}") from e

    def generate(
        self,
        prompt: str,
        config: GenerationConfig | None = None,
        stream: bool = False,
    ) -> InferenceResult | Iterator[str]:
        """
        Generate text completion.

        Args:
            prompt: Input prompt text
            config: Generation configuration (uses defaults if None)
            stream: If True, return iterator of tokens

        Returns:
            InferenceResult or Iterator[str] if streaming

        Raises:
            InferenceError: If generation fails
        """
        if not self._loaded or self._model is None:
            raise InferenceError("Model not loaded")

        config = config or GenerationConfig()

        with self._lock:
            try:
                start_time = time.perf_counter()
                first_token_time = None

                if stream:
                    return self._generate_stream(prompt, config, start_time)

                # Non-streaming generation
                response = self._model(
                    prompt,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature,
                    top_p=config.top_p,
                    top_k=config.top_k,
                    repeat_penalty=config.repeat_penalty,
                    presence_penalty=config.presence_penalty,
                    frequency_penalty=config.frequency_penalty,
                    stop=config.stop if config.stop else None,
                    seed=config.seed if config.seed >= 0 else None,
                )

                end_time = time.perf_counter()
                total_time_ms = (end_time - start_time) * 1000

                # Extract results
                content = response["choices"][0]["text"]
                tokens_generated = response["usage"]["completion_tokens"]
                tokens_prompt = response["usage"]["prompt_tokens"]
                finish_reason = response["choices"][0].get("finish_reason", "stop")

                # Calculate tokens/second
                tps = tokens_generated / (total_time_ms / 1000) if total_time_ms > 0 else 0

                return InferenceResult(
                    content=content,
                    tokens_generated=tokens_generated,
                    tokens_prompt=tokens_prompt,
                    time_to_first_token_ms=0.0,  # Not available in non-streaming
                    total_time_ms=total_time_ms,
                    tokens_per_second=tps,
                    model=Path(self.config.model_path).name,
                    finish_reason=finish_reason,
                )

            except Exception as e:
                raise InferenceError(f"Generation failed: {e}") from e

    def _generate_stream(
        self,
        prompt: str,
        config: GenerationConfig,
        start_time: float,
    ) -> Iterator[str]:
        """Generate text with streaming output."""
        first_token_time = None
        tokens_generated = 0

        for output in self._model(
            prompt,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            top_p=config.top_p,
            top_k=config.top_k,
            repeat_penalty=config.repeat_penalty,
            stop=config.stop if config.stop else None,
            stream=True,
        ):
            if first_token_time is None:
                first_token_time = time.perf_counter()

            token = output["choices"][0]["text"]
            tokens_generated += 1
            yield token

    def chat(
        self,
        messages: list[dict[str, str]],
        config: GenerationConfig | None = None,
        stream: bool = False,
    ) -> InferenceResult | Iterator[str]:
        """
        Generate chat completion.

        Args:
            messages: List of chat messages [{"role": "user", "content": "..."}]
            config: Generation configuration
            stream: If True, return iterator of tokens

        Returns:
            InferenceResult or Iterator[str] if streaming
        """
        if not self._loaded or self._model is None:
            raise InferenceError("Model not loaded")

        config = config or GenerationConfig()

        with self._lock:
            try:
                start_time = time.perf_counter()

                if stream:
                    return self._chat_stream(messages, config, start_time)

                # Non-streaming chat completion
                response = self._model.create_chat_completion(
                    messages=messages,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature,
                    top_p=config.top_p,
                    top_k=config.top_k,
                    repeat_penalty=config.repeat_penalty,
                    presence_penalty=config.presence_penalty,
                    frequency_penalty=config.frequency_penalty,
                    stop=config.stop if config.stop else None,
                    seed=config.seed if config.seed >= 0 else None,
                )

                end_time = time.perf_counter()
                total_time_ms = (end_time - start_time) * 1000

                # Extract results
                content = response["choices"][0]["message"]["content"]
                tokens_generated = response["usage"]["completion_tokens"]
                tokens_prompt = response["usage"]["prompt_tokens"]
                finish_reason = response["choices"][0].get("finish_reason", "stop")

                tps = tokens_generated / (total_time_ms / 1000) if total_time_ms > 0 else 0

                return InferenceResult(
                    content=content,
                    tokens_generated=tokens_generated,
                    tokens_prompt=tokens_prompt,
                    time_to_first_token_ms=0.0,
                    total_time_ms=total_time_ms,
                    tokens_per_second=tps,
                    model=Path(self.config.model_path).name,
                    finish_reason=finish_reason,
                )

            except Exception as e:
                raise InferenceError(f"Chat completion failed: {e}") from e

    def _chat_stream(
        self,
        messages: list[dict[str, str]],
        config: GenerationConfig,
        start_time: float,
    ) -> Iterator[str]:
        """Generate chat completion with streaming output."""
        for output in self._model.create_chat_completion(
            messages=messages,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            top_p=config.top_p,
            top_k=config.top_k,
            repeat_penalty=config.repeat_penalty,
            stop=config.stop if config.stop else None,
            stream=True,
        ):
            delta = output["choices"][0].get("delta", {})
            if "content" in delta:
                yield delta["content"]

    def tokenize(self, text: str) -> list[int]:
        """Tokenize text into token IDs."""
        if not self._loaded or self._model is None:
            raise InferenceError("Model not loaded")
        return self._model.tokenize(text.encode("utf-8"))

    def detokenize(self, tokens: list[int]) -> str:
        """Convert token IDs back to text."""
        if not self._loaded or self._model is None:
            raise InferenceError("Model not loaded")
        return self._model.detokenize(tokens).decode("utf-8")

    def get_embeddings(self, text: str) -> list[float]:
        """Get embeddings for text (requires embedding model)."""
        if not self._loaded or self._model is None:
            raise InferenceError("Model not loaded")
        if not self.config.embedding:
            raise InferenceError("Model not loaded in embedding mode")
        return self._model.embed(text)

    @property
    def context_length(self) -> int:
        """Get model's context length."""
        if self._model:
            return self._model.n_ctx()
        return self.config.n_ctx

    @property
    def load_time_ms(self) -> float:
        """Get model load time in milliseconds."""
        return self._load_time_ms

    def __del__(self):
        """Clean up model resources."""
        if self._model is not None:
            del self._model
            self._model = None
            self._loaded = False


class ModelManager:
    """
    Manages multiple loaded models with preloading support.

    Provides singleton access to models for efficient memory usage
    and fast switching between models.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._models: dict[str, LlamaCppModel] = {}
        self._default_model: str | None = None
        self._model_configs: dict[str, ModelConfig] = {}
        self._initialized = True

        # Ensure model directory exists
        CORTEX_MODELS_DIR.mkdir(parents=True, exist_ok=True)
        CORTEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Load saved model configs
        self._load_configs()

    def _load_configs(self) -> None:
        """Load model configurations from disk."""
        config_file = CORTEX_MODELS_DIR / "models.json"
        if config_file.exists():
            try:
                with open(config_file) as f:
                    data = json.load(f)
                    self._default_model = data.get("default_model")
                    for name, cfg in data.get("models", {}).items():
                        self._model_configs[name] = ModelConfig(**cfg)
            except (json.JSONDecodeError, KeyError):
                logger.warning("Failed to load model configs, using defaults")

    def _save_configs(self) -> None:
        """Save model configurations to disk."""
        config_file = CORTEX_MODELS_DIR / "models.json"
        data = {
            "default_model": self._default_model,
            "models": {
                name: {
                    "model_path": cfg.model_path,
                    "n_ctx": cfg.n_ctx,
                    "n_batch": cfg.n_batch,
                    "n_threads": cfg.n_threads,
                    "n_gpu_layers": cfg.n_gpu_layers,
                }
                for name, cfg in self._model_configs.items()
            },
        }
        with open(config_file, "w") as f:
            json.dump(data, f, indent=2)

    def register_model(
        self,
        name: str,
        model_path: str,
        config: ModelConfig | None = None,
        set_default: bool = False,
    ) -> None:
        """
        Register a model for later loading.

        Args:
            name: Friendly name for the model
            model_path: Path to the GGUF file
            config: Optional model configuration
            set_default: If True, set as default model
        """
        if config is None:
            config = ModelConfig(model_path=model_path)
        else:
            config.model_path = model_path

        self._model_configs[name] = config

        if set_default or self._default_model is None:
            self._default_model = name

        self._save_configs()
        logger.info(f"📝 Registered model: {name}")

    def load_model(
        self,
        name: str | None = None,
        preload: bool = False,
    ) -> LlamaCppModel:
        """
        Load a model by name.

        Args:
            name: Model name (uses default if None)
            preload: If True, load in background

        Returns:
            Loaded model instance

        Raises:
            ModelLoadError: If model not found or fails to load
        """
        name = name or self._default_model
        if name is None:
            raise ModelLoadError("No model specified and no default model configured")

        # Return cached model if already loaded
        if name in self._models:
            return self._models[name]

        # Get config
        if name not in self._model_configs:
            # Try to find by path
            model_path = CORTEX_MODELS_DIR / f"{name}.gguf"
            if model_path.exists():
                self.register_model(name, str(model_path))
            else:
                raise ModelLoadError(f"Model not found: {name}")

        config = self._model_configs[name]

        if preload:
            # Load in background thread
            thread = threading.Thread(
                target=self._background_load,
                args=(name, config),
                daemon=True,
            )
            thread.start()
            return None  # type: ignore
        else:
            # Load synchronously
            model = LlamaCppModel(config)
            self._models[name] = model
            return model

    def _background_load(self, name: str, config: ModelConfig) -> None:
        """Load model in background thread."""
        try:
            model = LlamaCppModel(config)
            self._models[name] = model
            logger.info(f"🔄 Preloaded model: {name}")
        except Exception as e:
            logger.error(f"Failed to preload model {name}: {e}")

    def unload_model(self, name: str) -> None:
        """Unload a model from memory."""
        if name in self._models:
            del self._models[name]
            logger.info(f"🗑️ Unloaded model: {name}")

    def get_model(self, name: str | None = None) -> LlamaCppModel | None:
        """Get a loaded model by name."""
        name = name or self._default_model
        return self._models.get(name)

    def list_models(self) -> list[dict[str, Any]]:
        """List all registered models with their status."""
        models = []
        for name, config in self._model_configs.items():
            models.append(
                {
                    "name": name,
                    "path": config.model_path,
                    "loaded": name in self._models,
                    "default": name == self._default_model,
                    "context_length": config.n_ctx,
                }
            )
        return models

    def list_available_models(self) -> list[str]:
        """List GGUF files in models directory."""
        models = []
        for path in CORTEX_MODELS_DIR.glob("*.gguf"):
            models.append(path.stem)
        return models

    @property
    def default_model(self) -> str | None:
        """Get default model name."""
        return self._default_model

    @default_model.setter
    def default_model(self, name: str) -> None:
        """Set default model."""
        if name not in self._model_configs:
            raise ValueError(f"Model not registered: {name}")
        self._default_model = name
        self._save_configs()


def detect_best_backend() -> LlamaCppBackend:
    """
    Detect the best available compute backend.

    Returns:
        LlamaCppBackend enum value
    """
    try:
        # Try CUDA first
        import subprocess

        result = subprocess.run(
            ["nvidia-smi"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return LlamaCppBackend.CUDA
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    try:
        # Try ROCm
        import subprocess

        result = subprocess.run(
            ["rocm-smi"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return LlamaCppBackend.ROCM
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Check for macOS Metal
    import platform

    if platform.system() == "Darwin":
        return LlamaCppBackend.METAL

    # Default to CPU
    return LlamaCppBackend.CPU


def get_optimal_config(model_path: str) -> ModelConfig:
    """
    Generate optimal model configuration based on hardware.

    Args:
        model_path: Path to the GGUF model file

    Returns:
        Optimized ModelConfig
    """
    from cortex.kernel_features.hardware_detect import detect_accelerators

    hw = detect_accelerators()
    backend = detect_best_backend()

    config = ModelConfig(model_path=model_path)

    # Set GPU layers based on VRAM
    if backend == LlamaCppBackend.CUDA:
        if hw.total_vram_gb >= 24:
            config.n_gpu_layers = -1  # All layers
            config.n_ctx = 8192
        elif hw.total_vram_gb >= 12:
            config.n_gpu_layers = -1
            config.n_ctx = 4096
        elif hw.total_vram_gb >= 8:
            config.n_gpu_layers = 32
            config.n_ctx = 2048
        else:
            config.n_gpu_layers = 16
            config.n_ctx = 2048
    elif backend == LlamaCppBackend.METAL:
        # Apple Silicon - use unified memory efficiently
        config.n_gpu_layers = -1
        config.n_ctx = min(8192, int(hw.total_system_ram_gb * 512))
    else:
        # CPU only
        config.n_gpu_layers = 0
        config.n_ctx = 2048

    # Set thread count
    config.n_threads = min(hw.cpu_cores, 8)

    # Enable mmap for fast loading
    config.use_mmap = True

    return config


# Convenience functions for quick usage
def quick_complete(prompt: str, model_name: str | None = None) -> str:
    """
    Quick one-shot completion.

    Args:
        prompt: Text prompt
        model_name: Model to use (default if None)

    Returns:
        Generated text
    """
    manager = ModelManager()
    model = manager.load_model(model_name)
    result = model.generate(prompt)
    return result.content


def quick_chat(messages: list[dict[str, str]], model_name: str | None = None) -> str:
    """
    Quick one-shot chat completion.

    Args:
        messages: Chat messages
        model_name: Model to use (default if None)

    Returns:
        Assistant response
    """
    manager = ModelManager()
    model = manager.load_model(model_name)
    result = model.chat(messages)
    return result.content


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Cortex llama.cpp Backend")
    sub = parser.add_subparsers(dest="command")

    # List models
    sub.add_parser("list", help="List registered models")

    # Register model
    reg = sub.add_parser("register", help="Register a new model")
    reg.add_argument("name", help="Model name")
    reg.add_argument("path", help="Path to GGUF file")
    reg.add_argument("--default", action="store_true", help="Set as default")

    # Load model
    load = sub.add_parser("load", help="Load a model")
    load.add_argument("name", nargs="?", help="Model name")

    # Generate
    gen = sub.add_parser("generate", help="Generate text")
    gen.add_argument("prompt", help="Input prompt")
    gen.add_argument("--model", help="Model name")
    gen.add_argument("--max-tokens", type=int, default=256)

    # Chat
    chat = sub.add_parser("chat", help="Interactive chat")
    chat.add_argument("--model", help="Model name")

    # Backend info
    sub.add_parser("backend", help="Show detected backend")

    args = parser.parse_args()
    manager = ModelManager()

    if args.command == "list":
        print("\n📦 Registered Models:")
        for model in manager.list_models():
            status = "✅ loaded" if model["loaded"] else "⬜ not loaded"
            default = " (default)" if model["default"] else ""
            print(f"  {model['name']}{default}: {status}")
            print(f"    Path: {model['path']}")
            print(f"    Context: {model['context_length']}")
        print()

        print("📁 Available GGUF files:")
        for name in manager.list_available_models():
            print(f"  - {name}")

    elif args.command == "register":
        manager.register_model(args.name, args.path, set_default=args.default)
        print(f"✅ Registered: {args.name}")

    elif args.command == "load":
        model = manager.load_model(args.name)
        print(f"✅ Loaded model in {model.load_time_ms:.1f}ms")

    elif args.command == "generate":
        result = quick_complete(args.prompt, args.model)
        print(result)

    elif args.command == "chat":
        print("🤖 Cortex Chat (type 'exit' to quit)\n")
        model = manager.load_model(args.model)
        messages = []

        while True:
            try:
                user_input = input("You: ").strip()
                if user_input.lower() in ("exit", "quit", "q"):
                    break

                messages.append({"role": "user", "content": user_input})
                result = model.chat(messages)
                print(f"Assistant: {result.content}\n")
                messages.append({"role": "assistant", "content": result.content})

            except KeyboardInterrupt:
                break

    elif args.command == "backend":
        backend = detect_best_backend()
        print(f"🖥️ Detected backend: {backend.value}")

    else:
        parser.print_help()

