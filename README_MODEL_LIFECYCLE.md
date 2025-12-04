# Cortex Model Lifecycle Manager

Systemd-based service management for LLM models. Brings "systemctl for AI models" to Cortex Linux.

## Quick Start

```bash
# Register a model
cortex-model register llama-70b --path meta-llama/Llama-2-70b-hf --backend vllm --gpus 0,1

# Start the model
cortex-model start llama-70b

# Check status
cortex-model status

# Enable auto-start on boot
cortex-model enable llama-70b

# View logs
cortex-model logs llama-70b -f
```

## Features

- **Systemd Service Generation**: Creates proper systemd user services for any LLM backend
- **Multi-Backend Support**: vLLM, llama.cpp, Ollama, Text Generation Inference (TGI)
- **Health Check Monitoring**: HTTP endpoint checks with automatic restart on failure
- **Resource Limits**: CPU, memory, I/O, and task limits via systemd cgroups
- **Security Hardening**: NoNewPrivileges, ProtectSystem, namespace isolation
- **SQLite Persistence**: Configuration and event logging
- **Boot Auto-Start**: Enable models to start automatically on system boot

## Supported Backends

| Backend | Command | Health Endpoint |
|---------|---------|-----------------||
| vLLM | `python -m vllm.entrypoints.openai.api_server` | `/health` |
| llama.cpp | `llama-server` | `/health` |
| Ollama | `ollama serve` | `/api/tags` |
| TGI | `text-generation-launcher` | `/health` |

## Commands

### Register a Model

```bash
cortex-model register <name> --path <model-path> [options]

Options:
  --backend        Backend: vllm, llamacpp, ollama, tgi (default: vllm)
  --port           Service port (default: 8000)
  --host           Service host (default: 127.0.0.1)
  --gpus           Comma-separated GPU IDs (default: 0)
  --memory         Memory limit (default: 32G)
  --cpu            CPU cores limit (default: 4.0)
  --max-model-len  Maximum sequence length (default: 4096)
  --tensor-parallel  Tensor parallel size (default: 1)
  --quantization   Quantization method: awq, gptq
  --extra-args     Extra backend arguments
  --no-health-check  Disable health monitoring
```

### Lifecycle Commands

```bash
cortex-model start <name>      # Start a model service
cortex-model stop <name>       # Stop a model service
cortex-model restart <name>    # Restart a model service
cortex-model enable <name>     # Enable auto-start on boot
cortex-model disable <name>    # Disable auto-start
cortex-model unregister <name> # Remove model completely
```

### Status and Monitoring

```bash
cortex-model status            # List all models with state
cortex-model status <name>     # Show specific model status
cortex-model list              # Alias for status
cortex-model logs <name>       # View systemd journal logs
cortex-model logs <name> -f    # Follow logs in real-time
cortex-model events            # Show all model events
cortex-model events <name>     # Show events for specific model
cortex-model health <name>     # Check health endpoint
```

## Usage Examples

### vLLM with Multiple GPUs

```bash
cortex-model register llama-70b \
  --path meta-llama/Llama-2-70b-hf \
  --backend vllm \
  --gpus 0,1,2,3 \
  --tensor-parallel 4 \
  --memory 128G \
  --max-model-len 8192

cortex-model start llama-70b
cortex-model enable llama-70b
```

### Quantized Model with AWQ

```bash
cortex-model register llama-awq \
  --path TheBloke/Llama-2-70B-AWQ \
  --backend vllm \
  --quantization awq \
  --gpus 0

cortex-model start llama-awq
```

### Local GGUF Model with llama.cpp

```bash
cortex-model register local-gguf \
  --path /models/llama-7b.Q4_K_M.gguf \
  --backend llamacpp \
  --port 8080

cortex-model start local-gguf
```

### TGI for Production

```bash
cortex-model register tgi-prod \
  --path bigscience/bloom-7b1 \
  --backend tgi \
  --gpus 0,1 \
  --tensor-parallel 2 \
  --host 0.0.0.0 \
  --port 8000

cortex-model start tgi-prod
cortex-model enable tgi-prod
```

## Configuration

### Resource Limits

Models are configured with systemd resource limits:

| Setting | Default | Description |
|---------|---------|-------------|
| MemoryMax | 32G | Hard memory limit |
| MemoryHigh | 28G | Soft memory limit (triggers reclaim) |
| CPUQuota | 400% | CPU cores (100% = 1 core) |
| CPUWeight | 100 | CPU scheduling weight (1-10000) |
| IOWeight | 100 | I/O scheduling weight (1-10000) |
| TasksMax | 512 | Maximum processes/threads |

### Security Hardening

Default security settings (can be customized):

| Setting | Default | Description |
|---------|---------|-------------|
| NoNewPrivileges | true | Prevent privilege escalation |
| ProtectSystem | strict | Read-only /usr and /boot |
| ProtectHome | read-only | Read-only home directory |
| PrivateTmp | true | Private /tmp namespace |
| PrivateDevices | false | False to allow GPU access |
| RestrictRealtime | true | Prevent realtime scheduling |
| ProtectKernelTunables | true | Protect sysctl |
| ProtectKernelModules | true | Prevent module loading |

### Health Checks

Health monitoring configuration:

| Setting | Default | Description |
|---------|---------|-------------|
| enabled | true | Enable health monitoring |
| endpoint | /health | HTTP endpoint to check |
| interval_seconds | 30 | Check interval |
| timeout_seconds | 10 | Request timeout |
| max_failures | 3 | Failures before restart |
| startup_delay_seconds | 60 | Wait before first check |

## Architecture

```
ModelLifecycleManager
|-- ModelDatabase (SQLite)
|   |-- models table (configuration)
|   +-- events table (audit log)
|-- ServiceGenerator (systemd units)
|   |-- Backend templates (vLLM, TGI, etc.)
|   |-- Resource limits
|   +-- Security hardening
+-- HealthChecker (monitoring)
    |-- HTTP endpoint checks
    +-- Auto-restart logic

Configuration:
|-- ~/.cortex/models.db              # SQLite database
|-- ~/.config/systemd/user/          # Service files
|   +-- cortex-<model>.service
+-- ~/.cortex/logs/                  # Local logs
```

## Service File Example

Generated service file for a vLLM model:

```ini
[Unit]
Description=Cortex Model: llama-70b
Documentation=https://github.com/cortexlinux/cortex
After=network.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=python -m vllm.entrypoints.openai.api_server --model meta-llama/Llama-2-70b-hf --host 127.0.0.1 --port 8000 --gpu-memory-utilization 0.9 --max-model-len 4096 --tensor-parallel-size 4
Environment=CUDA_VISIBLE_DEVICES=0,1,2,3
Environment=HIP_VISIBLE_DEVICES=0,1,2,3
Environment=TOKENIZERS_PARALLELISM=false

# Resource Limits
CPUQuota=400%
CPUWeight=100
MemoryMax=128G
MemoryHigh=120G
IOWeight=100
TasksMax=512

# Security Hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=true
RestrictRealtime=true
RestrictSUIDSGID=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true

# Restart Policy
Restart=on-failure
RestartSec=10
StartLimitIntervalSec=300
StartLimitBurst=5

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=cortex-llama-70b

[Install]
WantedBy=default.target
```

## Testing

```bash
# Run all tests
pytest tests/test_model_lifecycle.py -v

# Run specific test class
pytest tests/test_model_lifecycle.py::TestModelConfig -v

# Run with coverage
pytest tests/test_model_lifecycle.py --cov=cortex.kernel_features.model_lifecycle
```

## Requirements

- Python 3.8+
- systemd with user services enabled
- One of: vLLM, llama.cpp, Ollama, or TGI installed

### Enabling User Services

```bash
# Enable lingering for user services to run without login
loginctl enable-linger $USER

# Verify systemd user instance
systemctl --user status
```

## Files

- `cortex/kernel_features/model_lifecycle.py` - Main implementation (~1000 lines)
- `tests/test_model_lifecycle.py` - Unit tests (~650 lines, 50+ tests)
- `README_MODEL_LIFECYCLE.md` - This documentation

## Related Issues

- [#220 Model Lifecycle Manager - Systemd-Based LLM Service Management](https://github.com/cortexlinux/cortex/issues/220)
