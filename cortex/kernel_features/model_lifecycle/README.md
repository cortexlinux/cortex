# Model Lifecycle Manager

**Bounty:** cortexlinux/cortex#220  
**Author:** Yair Siegel  
**Value:** $150

## Overview

Systemd-based LLM service management for Cortex Linux. Manage LLM models as first-class system services - "systemctl for AI models".

## Features

- **Multi-Backend Support**: vLLM, llama.cpp, Ollama, TGI
- **SQLite Registry**: Persistent model configuration storage
- **Systemd Integration**: Full service lifecycle management
- **Resource Limits**: CPU, memory, GPU configuration via cgroups
- **Health Monitoring**: HTTP endpoint health checks
- **Security Hardening**: NoNewPrivileges, ProtectSystem, PrivateTmp
- **Auto-Start**: Enable models to start on boot

## Usage

```bash
# Register a model
cortex model register llama-70b --path meta-llama/Llama-2-70b-hf --backend vllm --gpus 0,1

# Start the model
cortex model start llama-70b

# Check status
cortex model status llama-70b

# Enable auto-start
cortex model enable llama-70b

# View logs
cortex model logs llama-70b

# Stop and unregister
cortex model stop llama-70b
cortex model unregister llama-70b
```

## Supported Backends

| Backend | Command | Use Case |
|---------|---------|----------|
| vllm | `python -m vllm.entrypoints.openai.api_server` | High-throughput GPU serving |
| llamacpp | `llama-server` | CPU/GPU hybrid inference |
| ollama | `ollama serve` | Easy model management |
| tgi | `text-generation-launcher` | HuggingFace TGI |

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌────────────────┐
│  CLI Interface  │────▶│  Model Registry  │────▶│  SQLite DB     │
└─────────────────┘     └──────────────────┘     └────────────────┘
        │                                                
        ▼                                                
┌─────────────────┐     ┌──────────────────┐     ┌────────────────┐
│ Service         │────▶│  Systemd         │────▶│ Model Process  │
│ Generator       │     │  Unit Files      │     │ (vLLM, etc)    │
└─────────────────┘     └──────────────────┘     └────────────────┘
        │                                                
        ▼                                                
┌─────────────────┐                                      
│ Health Monitor  │◀──── HTTP Health Checks              
└─────────────────┘                                      
```

## Tests

36 unit tests covering:
- Backend configurations
- Model configuration dataclass
- SQLite registry operations
- Systemd service generation
- Service control (mocked)
- Health monitoring
- End-to-end workflows

```bash
python -m pytest test_model_lifecycle.py -v
```

## Generated Service Example

```ini
[Unit]
Description=Cortex LLM Model: llama-70b
After=network.target

[Service]
Type=simple
Environment="CUDA_VISIBLE_DEVICES=0,1,2,3"
ExecStart=python -m vllm.entrypoints.openai.api_server --model meta-llama/Llama-2-70b-hf --port 8000

# Resource limits
CPUQuota=1600%
MemoryMax=128G

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```
