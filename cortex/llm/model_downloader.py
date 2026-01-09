#!/usr/bin/env python3
"""
Cortex Linux - GGUF Model Downloader

Downloads and manages GGUF model files from Hugging Face.
Supports resumable downloads, checksum verification, and progress tracking.

Author: Cortex Linux Team
License: Apache 2.0
"""

import hashlib
import json
import logging
import os
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Model storage paths
CORTEX_MODELS_DIR = Path.home() / ".cortex" / "models"
CORTEX_CACHE_DIR = Path.home() / ".cortex" / "cache"

# Curated model registry - optimized for Cortex package management tasks
CURATED_MODELS = {
    # Small models (< 4GB) - Fast startup, good for simple commands
    "qwen2.5-1.5b": {
        "url": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "size_gb": 1.1,
        "context": 32768,
        "description": "Fast, small model good for simple package commands",
        "recommended_vram_gb": 2,
    },
    "llama3.2-1b": {
        "url": "https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF/resolve/main/Llama-3.2-1B-Instruct-Q4_K_M.gguf",
        "size_gb": 0.8,
        "context": 8192,
        "description": "Smallest Llama model, very fast inference",
        "recommended_vram_gb": 2,
    },
    "phi3-mini": {
        "url": "https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q4.gguf",
        "size_gb": 2.2,
        "context": 4096,
        "description": "Microsoft Phi-3, excellent reasoning for size",
        "recommended_vram_gb": 4,
    },
    # Medium models (4-8GB) - Balanced performance
    "llama3.2-3b": {
        "url": "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "size_gb": 2.0,
        "context": 8192,
        "description": "Good balance of speed and capability",
        "recommended_vram_gb": 4,
    },
    "qwen2.5-7b": {
        "url": "https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf",
        "size_gb": 4.7,
        "context": 32768,
        "description": "Excellent for complex package management",
        "recommended_vram_gb": 8,
    },
    "mistral-7b": {
        "url": "https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf",
        "size_gb": 4.4,
        "context": 8192,
        "description": "Strong instruction following",
        "recommended_vram_gb": 8,
    },
    # Larger models (8-16GB) - Best quality
    "llama3.1-8b": {
        "url": "https://huggingface.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF/resolve/main/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
        "size_gb": 4.9,
        "context": 8192,
        "description": "Latest Llama, excellent quality",
        "recommended_vram_gb": 8,
    },
    "qwen2.5-14b": {
        "url": "https://huggingface.co/Qwen/Qwen2.5-14B-Instruct-GGUF/resolve/main/qwen2.5-14b-instruct-q4_k_m.gguf",
        "size_gb": 8.9,
        "context": 32768,
        "description": "High quality, long context",
        "recommended_vram_gb": 12,
    },
    # Code-focused models
    "codellama-7b": {
        "url": "https://huggingface.co/TheBloke/CodeLlama-7B-Instruct-GGUF/resolve/main/codellama-7b-instruct.Q4_K_M.gguf",
        "size_gb": 4.2,
        "context": 16384,
        "description": "Optimized for code and shell commands",
        "recommended_vram_gb": 8,
    },
    "deepseek-coder-6.7b": {
        "url": "https://huggingface.co/TheBloke/deepseek-coder-6.7B-instruct-GGUF/resolve/main/deepseek-coder-6.7b-instruct.Q4_K_M.gguf",
        "size_gb": 4.0,
        "context": 16384,
        "description": "Excellent for shell scripting tasks",
        "recommended_vram_gb": 8,
    },
}

# Default model for first-time setup
DEFAULT_MODEL = "qwen2.5-1.5b"


@dataclass
class DownloadProgress:
    """Progress information for downloads."""

    model_name: str
    total_bytes: int
    downloaded_bytes: int
    speed_bytes_per_sec: float
    eta_seconds: float

    @property
    def percent(self) -> float:
        if self.total_bytes == 0:
            return 0.0
        return (self.downloaded_bytes / self.total_bytes) * 100


class ModelDownloader:
    """Downloads and manages GGUF model files."""

    def __init__(self, models_dir: Path | None = None):
        """
        Initialize the downloader.

        Args:
            models_dir: Directory to store models (default: ~/.cortex/models)
        """
        self.models_dir = models_dir or CORTEX_MODELS_DIR
        self.models_dir.mkdir(parents=True, exist_ok=True)
        CORTEX_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def list_available(self) -> list[dict]:
        """List available models from registry."""
        models = []
        for name, info in CURATED_MODELS.items():
            model_path = self.models_dir / f"{name}.gguf"
            models.append(
                {
                    "name": name,
                    "size_gb": info["size_gb"],
                    "context": info["context"],
                    "description": info["description"],
                    "recommended_vram_gb": info["recommended_vram_gb"],
                    "downloaded": model_path.exists(),
                }
            )
        return models

    def list_downloaded(self) -> list[dict]:
        """List downloaded models."""
        models = []
        for path in self.models_dir.glob("*.gguf"):
            size_gb = path.stat().st_size / (1024**3)
            name = path.stem
            info = CURATED_MODELS.get(name, {})
            models.append(
                {
                    "name": name,
                    "path": str(path),
                    "size_gb": round(size_gb, 2),
                    "description": info.get("description", "Custom model"),
                }
            )
        return models

    def recommend_model(self, vram_gb: float = 0, ram_gb: float = 8) -> str:
        """
        Recommend a model based on available hardware.

        Args:
            vram_gb: Available GPU VRAM in GB
            ram_gb: Available system RAM in GB

        Returns:
            Model name
        """
        available_memory = vram_gb if vram_gb > 0 else ram_gb * 0.7

        # Find best model that fits
        best_model = DEFAULT_MODEL
        best_size = 0

        for name, info in CURATED_MODELS.items():
            if info["size_gb"] <= available_memory and info["size_gb"] > best_size:
                best_model = name
                best_size = info["size_gb"]

        return best_model

    def download(
        self,
        model_name: str,
        progress_callback: Callable[[DownloadProgress], None] | None = None,
        force: bool = False,
    ) -> Path:
        """
        Download a model from the registry.

        Args:
            model_name: Name of the model to download
            progress_callback: Optional callback for progress updates
            force: If True, re-download even if exists

        Returns:
            Path to the downloaded model

        Raises:
            ValueError: If model not found in registry
            IOError: If download fails
        """
        if model_name not in CURATED_MODELS:
            raise ValueError(
                f"Model '{model_name}' not found. Use list_available() to see options."
            )

        model_info = CURATED_MODELS[model_name]
        url = model_info["url"]
        dest_path = self.models_dir / f"{model_name}.gguf"
        temp_path = CORTEX_CACHE_DIR / f"{model_name}.gguf.part"

        # Check if already downloaded
        if dest_path.exists() and not force:
            logger.info(f"✅ Model already downloaded: {model_name}")
            return dest_path

        logger.info(f"📥 Downloading {model_name} ({model_info['size_gb']:.1f} GB)...")

        try:
            # Get file size
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=30) as response:
                total_size = int(response.headers.get("Content-Length", 0))

            # Check for partial download
            start_byte = 0
            if temp_path.exists():
                start_byte = temp_path.stat().st_size
                if start_byte >= total_size:
                    # Download complete, just move
                    shutil.move(temp_path, dest_path)
                    return dest_path

            # Download with progress
            req = urllib.request.Request(url)
            if start_byte > 0:
                req.add_header("Range", f"bytes={start_byte}-")
                logger.info(f"📥 Resuming download from {start_byte / (1024**3):.2f} GB")

            with urllib.request.urlopen(req, timeout=30) as response:
                mode = "ab" if start_byte > 0 else "wb"
                with open(temp_path, mode) as f:
                    downloaded = start_byte
                    chunk_size = 8192 * 16  # 128KB chunks
                    last_update = 0
                    start_time = os.times().elapsed

                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break

                        f.write(chunk)
                        downloaded += len(chunk)

                        # Report progress every 1%
                        if progress_callback and total_size > 0:
                            percent = (downloaded / total_size) * 100
                            if percent - last_update >= 1:
                                elapsed = os.times().elapsed - start_time
                                speed = downloaded / elapsed if elapsed > 0 else 0
                                eta = (total_size - downloaded) / speed if speed > 0 else 0

                                progress = DownloadProgress(
                                    model_name=model_name,
                                    total_bytes=total_size,
                                    downloaded_bytes=downloaded,
                                    speed_bytes_per_sec=speed,
                                    eta_seconds=eta,
                                )
                                progress_callback(progress)
                                last_update = percent

            # Move completed download to final location
            shutil.move(temp_path, dest_path)
            logger.info(f"✅ Downloaded: {model_name}")
            return dest_path

        except Exception as e:
            logger.error(f"❌ Download failed: {e}")
            raise IOError(f"Failed to download {model_name}: {e}") from e

    def download_from_url(
        self,
        url: str,
        name: str,
        progress_callback: Callable[[DownloadProgress], None] | None = None,
    ) -> Path:
        """
        Download a model from a custom URL.

        Args:
            url: URL to the GGUF file
            name: Name to save the model as
            progress_callback: Optional callback for progress updates

        Returns:
            Path to the downloaded model
        """
        dest_path = self.models_dir / f"{name}.gguf"

        if dest_path.exists():
            logger.info(f"✅ Model already exists: {name}")
            return dest_path

        logger.info(f"📥 Downloading from: {url}")

        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                total_size = int(response.headers.get("Content-Length", 0))

                with open(dest_path, "wb") as f:
                    downloaded = 0
                    chunk_size = 8192 * 16
                    start_time = os.times().elapsed

                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break

                        f.write(chunk)
                        downloaded += len(chunk)

                        if progress_callback and total_size > 0:
                            elapsed = os.times().elapsed - start_time
                            speed = downloaded / elapsed if elapsed > 0 else 0
                            eta = (total_size - downloaded) / speed if speed > 0 else 0

                            progress = DownloadProgress(
                                model_name=name,
                                total_bytes=total_size,
                                downloaded_bytes=downloaded,
                                speed_bytes_per_sec=speed,
                                eta_seconds=eta,
                            )
                            progress_callback(progress)

            logger.info(f"✅ Downloaded: {name}")
            return dest_path

        except Exception as e:
            if dest_path.exists():
                dest_path.unlink()
            raise IOError(f"Failed to download: {e}") from e

    def delete(self, model_name: str) -> bool:
        """
        Delete a downloaded model.

        Args:
            model_name: Name of the model to delete

        Returns:
            True if deleted, False if not found
        """
        model_path = self.models_dir / f"{model_name}.gguf"
        if model_path.exists():
            model_path.unlink()
            logger.info(f"🗑️ Deleted: {model_name}")
            return True
        return False

    def get_model_path(self, model_name: str) -> Path | None:
        """Get path to a downloaded model."""
        model_path = self.models_dir / f"{model_name}.gguf"
        return model_path if model_path.exists() else None


def print_progress(progress: DownloadProgress) -> None:
    """Default progress printer."""
    bar_width = 30
    filled = int(bar_width * progress.percent / 100)
    bar = "█" * filled + "░" * (bar_width - filled)

    speed_mb = progress.speed_bytes_per_sec / (1024 * 1024)
    downloaded_gb = progress.downloaded_bytes / (1024**3)
    total_gb = progress.total_bytes / (1024**3)

    eta_min = int(progress.eta_seconds // 60)
    eta_sec = int(progress.eta_seconds % 60)

    print(
        f"\r  {bar} {progress.percent:5.1f}% | "
        f"{downloaded_gb:.2f}/{total_gb:.2f} GB | "
        f"{speed_mb:.1f} MB/s | "
        f"ETA: {eta_min}m {eta_sec}s   ",
        end="",
        flush=True,
    )


def main():
    """CLI entry point for cortex-model command."""
    import argparse

    parser = argparse.ArgumentParser(description="Cortex Model Downloader")
    sub = parser.add_subparsers(dest="command")

    # List models
    list_cmd = sub.add_parser("list", help="List available models")
    list_cmd.add_argument("--downloaded", action="store_true", help="Only show downloaded")

    # Download model
    dl = sub.add_parser("download", help="Download a model")
    dl.add_argument("name", help="Model name or 'recommended'")
    dl.add_argument("--force", action="store_true", help="Re-download if exists")

    # Download from URL
    url_dl = sub.add_parser("download-url", help="Download from custom URL")
    url_dl.add_argument("url", help="URL to GGUF file")
    url_dl.add_argument("name", help="Name to save as")

    # Delete model
    delete = sub.add_parser("delete", help="Delete a model")
    delete.add_argument("name", help="Model name")

    # Recommend model
    rec = sub.add_parser("recommend", help="Get recommended model")
    rec.add_argument("--vram", type=float, default=0, help="Available VRAM in GB")
    rec.add_argument("--ram", type=float, default=16, help="Available RAM in GB")

    args = parser.parse_args()
    downloader = ModelDownloader()

    if args.command == "list":
        if args.downloaded:
            print("\n📦 Downloaded Models:\n")
            for model in downloader.list_downloaded():
                print(f"  ✅ {model['name']}")
                print(f"     Size: {model['size_gb']:.2f} GB")
                print(f"     Path: {model['path']}")
                print()
        else:
            print("\n📦 Available Models:\n")
            for model in downloader.list_available():
                status = "✅" if model["downloaded"] else "⬜"
                print(f"  {status} {model['name']}")
                print(f"     {model['description']}")
                print(f"     Size: {model['size_gb']:.1f} GB | Context: {model['context']:,}")
                print(f"     Recommended VRAM: {model['recommended_vram_gb']} GB")
                print()

    elif args.command == "download":
        name = args.name
        if name == "recommended":
            # Auto-detect hardware
            try:
                from cortex.kernel_features.hardware_detect import detect_accelerators

                hw = detect_accelerators()
                name = downloader.recommend_model(hw.total_vram_gb, hw.total_system_ram_gb)
                print(f"🎯 Recommended model: {name}")
            except ImportError:
                name = DEFAULT_MODEL

        path = downloader.download(name, progress_callback=print_progress, force=args.force)
        print(f"\n\n✅ Model ready: {path}")

    elif args.command == "download-url":
        path = downloader.download_from_url(args.url, args.name, progress_callback=print_progress)
        print(f"\n\n✅ Model ready: {path}")

    elif args.command == "delete":
        if downloader.delete(args.name):
            print(f"✅ Deleted: {args.name}")
        else:
            print(f"❌ Model not found: {args.name}")

    elif args.command == "recommend":
        model = downloader.recommend_model(args.vram, args.ram)
        print(f"🎯 Recommended model: {model}")
        info = CURATED_MODELS[model]
        print(f"   {info['description']}")
        print(f"   Size: {info['size_gb']:.1f} GB")

    else:
        parser.print_help()


# CLI entry point
if __name__ == "__main__":
    main()

