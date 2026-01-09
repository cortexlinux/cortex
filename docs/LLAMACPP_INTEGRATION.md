# llama.cpp Native Integration Guide

## Overview

Cortex Linux now supports native llama.cpp integration for local LLM inference. This provides significant advantages over the previous Ollama-based approach:

| Feature | Ollama (Legacy) | llama.cpp (Native) |
|---------|-----------------|-------------------|
| Architecture | Go binary + HTTP API | Direct C++ library calls |
| Footprint | ~500MB+ | <50MB binary |
| Startup Time | 2-5 seconds | <100ms (with preload daemon) |
| Memory Overhead | Separate process | Shared memory space |
| Feels Like | Installed application | Native OS component |

## Quick Start

### 1. Build llama.cpp

```bash
# Auto-detect hardware and build (CUDA, ROCm, Metal, or CPU)
./scripts/build_llamacpp.sh

# Or specify backend explicitly
./scripts/build_llamacpp.sh cuda   # NVIDIA GPU
./scripts/build_llamacpp.sh rocm   # AMD GPU
./scripts/build_llamacpp.sh metal  # Apple Silicon
./scripts/build_llamacpp.sh cpu    # CPU only
```

### 2. Download a Model

```bash
# Download recommended model based on your hardware
cortex-model download recommended

# Or choose a specific model
cortex-model list                  # See available models
cortex-model download qwen2.5-7b   # Download specific model
```

### 3. Configure Cortex

```bash
# Set provider to llama.cpp
export CORTEX_PROVIDER=llamacpp

# Or add to .env file
echo 'CORTEX_PROVIDER=llamacpp' >> ~/.cortex/.env
```

### 4. Test It!

```bash
cortex install nginx --dry-run
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Cortex Application                        │
│  ┌─────────────────┐  ┌──────────────────┐                  │
│  │   LLM Router    │  │ Command Interp.  │                  │
│  └────────┬────────┘  └────────┬─────────┘                  │
│           │                    │                             │
│           └────────┬───────────┘                             │
│                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              LlamaCppBackend (Python)                   ││
│  │  ┌──────────────┐  ┌────────────────┐  ┌─────────────┐ ││
│  │  │ Model Loader │  │ Inference API  │  │ KV Cache    │ ││
│  │  └──────────────┘  └────────────────┘  └─────────────┘ ││
│  └────────────────────────┬────────────────────────────────┘│
│                           │ ctypes/FFI                       │
│  ┌────────────────────────▼────────────────────────────────┐│
│  │              libllama.so (C++ Shared Library)           ││
│  │    ┌─────────┐  ┌──────────┐  ┌───────────────────┐    ││
│  │    │ GGUF    │  │ Samplers │  │ Backend Dispatch  │    ││
│  │    │ Parser  │  │          │  │ (CUDA/Metal/CPU)  │    ││
│  │    └─────────┘  └──────────┘  └───────────────────┘    ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

## Preload Daemon

For <100ms startup time, use the preload daemon to keep models warm in memory:

```bash
# Start the daemon
cortex-preload start

# Check status
cortex-preload status

# Stop the daemon
cortex-preload stop
```

The daemon uses Unix domain sockets for minimal IPC latency.

## Available Models

### Small Models (< 4GB) - Fast Startup

| Model | Size | Context | Best For |
|-------|------|---------|----------|
| `qwen2.5-1.5b` | 1.1 GB | 32K | Simple package commands |
| `llama3.2-1b` | 0.8 GB | 8K | Very fast inference |
| `phi3-mini` | 2.2 GB | 4K | Excellent reasoning |

### Medium Models (4-8GB) - Balanced

| Model | Size | Context | Best For |
|-------|------|---------|----------|
| `llama3.2-3b` | 2.0 GB | 8K | Good balance |
| `qwen2.5-7b` | 4.7 GB | 32K | Complex tasks |
| `mistral-7b` | 4.4 GB | 8K | Instruction following |

### Code-Focused Models

| Model | Size | Context | Best For |
|-------|------|---------|----------|
| `codellama-7b` | 4.2 GB | 16K | Code and shell |
| `deepseek-coder-6.7b` | 4.0 GB | 16K | Shell scripting |

## Configuration

### Environment Variables

```bash
# Provider selection
CORTEX_PROVIDER=llamacpp       # Use native llama.cpp

# Model configuration  
LLAMACPP_MODEL=qwen2.5-7b      # Model name

# Advanced options
LLAMACPP_N_CTX=4096            # Context window
LLAMACPP_N_GPU_LAYERS=-1       # GPU layers (-1 = all)
LLAMACPP_N_THREADS=8           # CPU threads
```

### Configuration File

Edit `~/.cortex/config.json`:

```json
{
  "api_provider": "llamacpp",
  "llamacpp_model": "qwen2.5-7b",
  "llamacpp_n_ctx": 4096,
  "llamacpp_n_gpu_layers": -1
}
```

## Migration from Ollama

### Automatic Migration

The existing Ollama configuration is recognized:

```bash
# Old Ollama config still works
CORTEX_PROVIDER=ollama
OLLAMA_MODEL=llama3.2

# New native config (recommended)
CORTEX_PROVIDER=llamacpp
LLAMACPP_MODEL=llama3.2
```

### Model Compatibility

GGUF models work with both Ollama and llama.cpp. You can:

1. **Use existing Ollama models**: Copy from `~/.ollama/models/`
2. **Download fresh**: Use `cortex-model download`

### Why Migrate?

| Metric | Ollama | llama.cpp |
|--------|--------|-----------|
| Cold start | 2-5s | 500ms-2s |
| With preload daemon | N/A | <100ms |
| Memory footprint | +200MB | Shared |
| Network overhead | HTTP localhost | Direct calls |

## Hardware Support

### NVIDIA GPUs (CUDA)

```bash
# Build with CUDA support
./scripts/build_llamacpp.sh cuda

# Check GPU is detected
nvidia-smi
```

Supported architectures:
- Turing (GTX 16xx, RTX 20xx): SM 7.5
- Ampere (RTX 30xx, A100): SM 8.0, 8.6
- Ada Lovelace (RTX 40xx): SM 8.9
- Hopper (H100): SM 9.0

### AMD GPUs (ROCm)

```bash
# Build with ROCm support
./scripts/build_llamacpp.sh rocm

# Check GPU is detected
rocm-smi
```

Supported GPUs:
- Radeon RX 6000 series (gfx1030)
- Radeon RX 7000 series (gfx1100)
- Instinct MI100/MI200

### Apple Silicon (Metal)

```bash
# Build with Metal support
./scripts/build_llamacpp.sh metal
```

Optimal for M1/M2/M3/M4 chips with unified memory.

### CPU Only

```bash
# Build CPU-only with OpenBLAS
./scripts/build_llamacpp.sh cpu
```

Supports AVX, AVX2, and ARM NEON optimizations.

## Troubleshooting

### Model Loading Errors

```bash
# Check if model exists
cortex-model list --downloaded

# Re-download if corrupted
cortex-model download qwen2.5-7b --force
```

### GPU Not Detected

```bash
# Check GPU backend
python3 -c "from llama_cpp import Llama; print('OK')"

# Rebuild with correct backend
./scripts/build_llamacpp.sh cuda  # or rocm, metal
```

### Out of Memory

```bash
# Use smaller model
cortex-model download llama3.2-1b

# Or reduce context
export LLAMACPP_N_CTX=2048
```

### Slow Inference

1. Check GPU layers are set: `LLAMACPP_N_GPU_LAYERS=-1`
2. Use preload daemon: `cortex-preload start`
3. Choose quantized model (Q4_K_M)

## API Reference

### Python Usage

```python
from cortex.llm import (
    ModelManager,
    GenerationConfig,
    quick_complete,
    quick_chat,
)

# Quick completion
result = quick_complete("Explain how to install nginx")

# Full control
manager = ModelManager()
model = manager.load_model("qwen2.5-7b")

config = GenerationConfig(
    max_tokens=512,
    temperature=0.7,
)

result = model.chat([
    {"role": "user", "content": "Install docker"}
], config=config)

print(result.content)
print(f"Tokens/sec: {result.tokens_per_second:.1f}")
```

### CLI Commands

```bash
# Model management
cortex-model list              # List available models
cortex-model download NAME     # Download a model
cortex-model delete NAME       # Remove a model
cortex-model recommend         # Get hardware-specific recommendation

# Preload daemon
cortex-preload start           # Start daemon
cortex-preload stop            # Stop daemon
cortex-preload status          # Check status
cortex-preload reload          # Reload model
```

## Performance Tuning

### Optimal Settings by VRAM

| VRAM | Model | Context | GPU Layers |
|------|-------|---------|------------|
| 4GB | llama3.2-1b | 4096 | All |
| 8GB | qwen2.5-7b | 4096 | All |
| 12GB | qwen2.5-7b | 8192 | All |
| 16GB+ | qwen2.5-14b | 8192 | All |

### CPU-Only Optimization

```bash
# Set thread count (typically CPU cores / 2)
export LLAMACPP_N_THREADS=4

# Enable OpenBLAS
export OPENBLAS_NUM_THREADS=4
```

## References

- [llama.cpp Repository](https://github.com/ggerganov/llama.cpp)
- [GGUF Model Format](https://github.com/ggerganov/ggml/blob/master/docs/gguf.md)
- [llama-cpp-python](https://github.com/abetlen/llama-cpp-python)

