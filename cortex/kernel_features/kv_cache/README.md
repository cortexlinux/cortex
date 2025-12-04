# KV-Cache Manager

**Bounty:** cortexlinux/cortex#221  
**Author:** Yair Siegel  
**Value:** $175

## Overview

User-space KV-cache management for LLM inference. Manages transformer key-value caches as first-class system resources with POSIX shared memory pools and multiple eviction policies.

## Features

- **Bitmap Block Allocator**: Thread-safe first-fit allocation
- **4 Eviction Policies**: LRU, LFU, FIFO, Priority
- **Prefix-Based Sharing**: Share cache across requests with same prompt prefix
- **Persistence**: Save/restore cache to disk
- **Multi-Pool Management**: Create and manage multiple cache pools
- **Memory Tiers**: CPU, GPU, NVMe support

## Usage

```bash
# Create a cache pool
cortex cache create llama-cache --size 16G --tier cpu --policy lru

# Check status
cortex cache status llama-cache

# Evict 25% of entries
cortex cache evict llama-cache --percent 25

# Persist to disk
cortex cache persist llama-cache --path /tmp/llama-cache.dat

# Restore from disk
cortex cache restore /tmp/llama-cache.dat

# List all pools
cortex cache status

# Delete pool
cortex cache delete llama-cache
```

## Memory Layout

```
┌──────────────────┐
│ Header (4KB)     │ Magic, version, config
├──────────────────┤
│ Bitmap (4KB)     │ Free list (1 bit per block)
├──────────────────┤
│ Data Region      │ KV tensors (4KB blocks)
└──────────────────┘
```

## Eviction Policies

| Policy | Description | Use Case |
|--------|-------------|----------|
| LRU | Least Recently Used | General purpose, access pattern varies |
| LFU | Least Frequently Used | Hot/cold access patterns |
| FIFO | First In First Out | Streaming, time-based expiry |
| Priority | User-defined priority | Critical prompts, VIP users |

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌────────────────┐
│  CLI Interface  │────▶│  Cache Store     │────▶│  KVCachePool   │
└─────────────────┘     └──────────────────┘     └────────────────┘
                                                         │
                                                         ▼
                                    ┌──────────────────────────────┐
                                    │ ┌──────────┐ ┌─────────────┐ │
                                    │ │ Bitmap   │ │ Eviction    │ │
                                    │ │ Allocator│ │ Manager     │ │
                                    │ └──────────┘ └─────────────┘ │
                                    │ ┌──────────────────────────┐ │
                                    │ │ Data Region (mmap)       │ │
                                    │ └──────────────────────────┘ │
                                    └──────────────────────────────┘
```

## Tests

49 unit tests covering:
- Size parsing and formatting utilities
- Cache entry dataclass
- Pool configuration
- Bitmap allocator (allocate, free, serialize)
- Eviction policies (LRU, LFU, FIFO, Priority)
- Pool operations (put, get, delete, evict)
- Prefix-based sharing
- Persistence and restore
- Cache store management
- End-to-end LLM workflows

```bash
python -m pytest test_kv_cache_manager.py -v
```

## Example: LLM Inference Cache

```python
from kv_cache_manager import CachePoolConfig, KVCachePool

# Create pool for LLM inference
config = CachePoolConfig(
    name="llama-cache",
    size_bytes=16 * 1024**3,  # 16GB
    tier="gpu",
    eviction_policy="lru",
)
pool = KVCachePool(config)

# Cache KV tensors per layer
for layer in range(32):
    key = f"batch0_layer{layer}_kv"
    kv_tensor = get_kv_tensor(layer)  # numpy/torch tensor
    pool.put(key, kv_tensor.tobytes(), 
             layer_index=layer, 
             sequence_length=2048)

# Retrieve cached tensors
cached = pool.get("batch0_layer0_kv")

# Share cache for same prompt prefix
pool.find_by_prefix("system_prompt_hash")
```
