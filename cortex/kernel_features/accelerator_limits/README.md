# Accelerator-Aware Resource Limits

**Bounty:** cortexlinux/cortex#222  
**Author:** Yair Siegel  
**Tests:** 32/32 passing

## Overview

cgroups v2 wrapper with AI workload presets for managing GPU, CPU, and memory resources.

## Features

- **Workload Presets:** inference, training, batch, interactive
- **cgroups v2 Integration:** CPU quota, memory limits, OOM score
- **GPU Management:** CUDA_VISIBLE_DEVICES, TensorFlow/PyTorch memory config
- **Profile Persistence:** JSON storage in ~/.config/cortex/limits
- **User-mode Delegation:** Works without root if cgroups delegation configured

## Usage

```bash
# Create profile from preset
cortex limits create inference-job --preset inference --gpus 2

# Apply to running process
cortex limits apply inference-job --pid 12345

# Export GPU environment variables
eval $(cortex limits env inference-job)

# Check status
cortex limits status inference-job

# List presets
cortex limits presets
```

## Presets

| Preset | CPU | Memory | GPU | OOM Score |
|--------|-----|--------|-----|----------|
| inference | 4 cores | 32 GB | 100% | -500 |
| training | 16 cores | 128 GB | 100% | -800 |
| batch | 8 cores | 64 GB | 80% | 0 |
| interactive | 2 cores | 16 GB | 50% | -200 |

## Testing

```bash
python -m pytest test_accelerator_limits.py -v
```
