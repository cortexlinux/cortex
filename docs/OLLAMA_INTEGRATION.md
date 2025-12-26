# Ollama Integration - Local LLM Support

## Overview

Cortex Linux now supports **local LLM inference** via Ollama, enabling privacy-first, offline-capable package management without requiring cloud API keys.

## Key Features

✅ **Privacy-First**: All processing happens locally, zero data sent to cloud  
✅ **Offline Capable**: Works completely offline once models are downloaded  
✅ **Zero Cost**: No API keys or subscriptions required  
✅ **Auto-Setup**: Automatically installed and configured during `pip install`  
✅ **Smart Fallback**: Falls back to Claude/OpenAI if local models unavailable  
✅ **Code-Optimized**: Prefers code-focused models for system tasks  
✅ **Streaming Support**: Real-time response streaming  

## Quick Start

### 1. Install Cortex with Ollama

```bash
# Clone repository
git clone https://github.com/cortexlinux/cortex.git
cd cortex

# Install (automatically sets up Ollama)
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

During installation, Cortex will:
- Install Ollama (if not already present)
- Start the Ollama service
- Pull a lightweight default model (`phi3:mini`)

### 2. Use Cortex Without API Keys

```bash
# Install packages using local LLM
cortex install nginx

# No ANTHROPIC_API_KEY or OPENAI_API_KEY needed!
```

### 3. Check Ollama Status

```bash
# Verify Ollama is running
ollama list

# See available models
ollama ps
```

## How It Works

### Architecture

```
User Request
    ↓
LLM Router (cortex/llm_router.py)
    ↓
Provider Selection:
    1. Ollama (Local) - Priority 1
    2. Claude (Cloud) - Fallback 1
    3. Kimi K2 (Cloud) - Fallback 2
    ↓
Response to User
```

### Model Selection

Cortex automatically selects the best available model:

**Preferred Models** (code-optimized):
1. `deepseek-coder-v2:16b` - Best for code and system tasks
2. `codellama:13b` - Meta's code-specialized model
3. `deepseek-coder:6.7b` - Good balance of speed/quality
4. `llama3:8b` - General purpose, very capable
5. `mistral:7b` - Fast and efficient
6. `phi3:mini` - Lightweight (default)

### Privacy Guarantees

- **100% Local**: Models run on your machine
- **No Telemetry**: Ollama doesn't send usage data
- **No Internet Required**: Works offline after model download
- **No API Keys**: No credentials to manage or expose

## Configuration

### Environment Variables

```bash
# Ollama settings
export OLLAMA_HOST=http://localhost:11434  # Default
export CORTEX_SKIP_OLLAMA_SETUP=1          # Skip auto-setup

# Cloud fallbacks (optional)
export ANTHROPIC_API_KEY=your-claude-key
export OPENAI_API_KEY=your-openai-key
```

### Configuration File

Create `~/.cortex/config.yaml`:

```yaml
llm:
  prefer_local: true  # Prefer Ollama over cloud
  
  ollama:
    enabled: true
    base_url: http://localhost:11434
    preferred_models:
      - deepseek-coder-v2:16b
      - llama3:8b
    auto_pull: true
  
  claude:
    enabled: false  # Optional fallback
  
  kimi_k2:
    enabled: false  # Optional fallback
```

## Manual Setup

### Install Ollama Manually

```bash
# Official installation script
curl -fsSL https://ollama.com/install.sh | sh

# Start service
ollama serve &

# Pull a model
ollama pull phi3:mini
```

### Run Setup Script

```bash
# Run post-install setup manually
python scripts/setup_ollama.py
```

## Model Management

### List Available Models

```bash
ollama list
```

### Pull Recommended Models

```bash
# Lightweight (1.9GB)
ollama pull phi3:mini

# Balanced (4.7GB)
ollama pull llama3:8b

# Code-optimized (9GB)
ollama pull codellama:13b

# Best for code (10GB+)
ollama pull deepseek-coder-v2:16b
```

### Remove Models

```bash
ollama rm model-name
```

## Performance

### Speed Comparison

| Model | Size | Speed (tokens/sec) | Quality |
|-------|------|-------------------|---------|
| phi3:mini | 1.9GB | ~50-100 | Good |
| llama3:8b | 4.7GB | ~30-60 | Very Good |
| codellama:13b | 9GB | ~20-40 | Excellent |
| deepseek-coder-v2:16b | 10GB+ | ~15-30 | Outstanding |

*Speed varies by hardware*

### Hardware Requirements

**Minimum**:
- 8GB RAM
- 4 CPU cores
- 5GB disk space

**Recommended**:
- 16GB+ RAM
- 8+ CPU cores
- GPU with 8GB+ VRAM (optional, speeds up inference)

**Optimal**:
- 32GB+ RAM
- Modern multi-core CPU
- NVIDIA GPU with 12GB+ VRAM

## Troubleshooting

### Ollama Not Starting

```bash
# Check if service is running
systemctl status ollama

# Start manually
ollama serve &

# Check logs
journalctl -u ollama -f
```

### Models Not Downloading

```bash
# Check disk space
df -h

# Check network
curl -I https://ollama.com

# Pull specific version
ollama pull llama3:8b-q4_0
```

### Slow Responses

```bash
# Use smaller model
ollama pull phi3:mini

# Check system resources
htop

# Enable GPU acceleration (if available)
# Ollama auto-detects CUDA/ROCm
```

### Fallback to Cloud

```bash
# Set API keys for fallback
export ANTHROPIC_API_KEY=your-key

# Or disable Ollama temporarily
export OLLAMA_HOST=http://invalid
```

## API Reference

### OllamaProvider Class

```python
from cortex.providers.ollama_provider import OllamaProvider

# Initialize
ollama = OllamaProvider(
    base_url="http://localhost:11434",
    timeout=300,
    auto_pull=True
)

# Check installation
if ollama.is_installed():
    print("✅ Ollama available")

# Ensure service running
ollama.start_service()

# Get available models
models = ollama.get_available_models()

# Generate completion
response = ollama.complete(
    messages=[
        {"role": "user", "content": "Explain nginx configuration"}
    ],
    temperature=0.7,
    max_tokens=2048
)
```

### LLM Router Integration

```python
from cortex.llm_router import LLMRouter, LLMProvider, TaskType

# Initialize router (auto-detects Ollama)
router = LLMRouter(prefer_local=True)

# Complete with auto-routing
response = router.complete(
    messages=[{"role": "user", "content": "Install nginx"}],
    task_type=TaskType.SYSTEM_OPERATION
)

# Force Ollama
response = router.complete(
    messages=[...],
    force_provider=LLMProvider.OLLAMA
)
```

## Comparison: Local vs Cloud

| Feature | Ollama (Local) | Claude | Kimi K2 |
|---------|---------------|--------|---------|
| **Privacy** | 100% local | Cloud | Cloud |
| **Cost** | Free | $3-15/1M tokens | $1-5/1M tokens |
| **Speed** | Depends on hardware | Fast | Fast |
| **Offline** | ✅ Yes | ❌ No | ❌ No |
| **Setup** | Auto | API key | API key |
| **Quality** | Good-Excellent | Excellent | Excellent |

## Best Practices

### When to Use Ollama

✅ Privacy-sensitive operations  
✅ Offline environments  
✅ Development/testing  
✅ Cost-sensitive workloads  
✅ Repeated similar tasks  

### When to Use Cloud

✅ Maximum quality needed  
✅ Complex reasoning tasks  
✅ Limited local resources  
✅ Infrequent usage  

### Hybrid Approach

```python
# Use Ollama for common tasks
router = LLMRouter(prefer_local=True)

# Explicit cloud for complex tasks
response = router.complete(
    messages=[...],
    force_provider=LLMProvider.CLAUDE,
    task_type=TaskType.ERROR_DEBUGGING
)
```

## Security Considerations

### Data Privacy

- **Local Processing**: All LLM inference happens locally
- **No Logging**: Ollama doesn't log prompts or responses
- **No Network**: Zero network calls during inference

### System Security

- **Sandboxed**: Ollama runs in user space
- **No Root**: Doesn't require elevated privileges
- **Isolated**: Models stored in `~/.ollama`

### API Key Safety

- **Optional**: API keys only needed for cloud fallback
- **Encrypted**: Stored securely in system keyring
- **Never Logged**: Keys never written to logs

## Contributing

### Adding New Models

1. Test model compatibility:
```bash
ollama pull your-model:tag
cortex install test-package --dry-run
```

2. Update preferred models in [ollama_provider.py](../cortex/providers/ollama_provider.py)

3. Document in this guide

### Reporting Issues

Include in bug reports:
- `ollama --version`
- `cortex --version`
- Model being used
- Hardware specs
- Error logs

## Resources

- [Ollama GitHub](https://github.com/ollama/ollama)
- [Ollama Models Library](https://ollama.com/library)
- [Cortex Discord](https://discord.gg/uCqHvxjU83)
- [DeepSeek Coder](https://github.com/deepseek-ai/DeepSeek-Coder)

## FAQ

**Q: Do I need a GPU?**  
A: No, but it significantly speeds up inference. CPU-only works fine.

**Q: Which model should I use?**  
A: Start with `phi3:mini` (small), upgrade to `llama3:8b` (balanced), or `deepseek-coder-v2:16b` (best).

**Q: Can I use multiple models?**  
A: Yes, Cortex auto-selects based on availability and task type.

**Q: Is it really private?**  
A: Yes - 100% local processing, no telemetry, no internet required after setup.

**Q: How do I update models?**  
A: `ollama pull model-name` downloads the latest version.

**Q: Can I disable Ollama?**  
A: Set `CORTEX_SKIP_OLLAMA_SETUP=1` or remove API keys to force cloud usage.

## License

Ollama integration is part of Cortex Linux, licensed under Apache 2.0.
