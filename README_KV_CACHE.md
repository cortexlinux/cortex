# Cortex KV-Cache Manager

User-space KV-cache management for LLM inference optimization. Provides POSIX shared memory pools with multiple eviction policies, prefix hash matching, and disk persistence.

## Quick Start

```bash
# Create a cache pool
cortex cache create llama-cache --size 16G --policy lru

# Check status
cortex cache status llama-cache

# Persist to disk for fast restarts
cortex cache persist llama-cache

# Restore from disk
cortex cache restore llama-cache

# Evict entries under pressure
cortex cache evict llama-cache --percent 25

# Destroy when done
cortex cache destroy llama-cache
```

## Features

- **POSIX Shared Memory Pools**: Cross-process cache sharing via shared memory
- **Multiple Eviction Policies**: LRU, LFU, FIFO, and priority-based eviction
- **Prefix Hash Matching**: Efficient cache lookup by token prefix
- **Disk Persistence**: Save and restore cache for fast restarts
- **Thread-Safe Allocator**: Bitmap-based block allocation with locking
- **Process Attachment Tracking**: Track which processes use each pool
- **SQLite Metadata**: Persistent configuration and statistics

## Memory Layout

```
┌──────────────────────┐
│ Header (4KB)         │ Magic, version, usage stats, counters
├──────────────────────┤
│ Free List (4KB)      │ Bitmap of allocated blocks
├──────────────────────┤
│ Data Region          │ KV-cache tensor data
│ (configurable size)  │
└──────────────────────┘
```

### Header Fields

| Field | Offset | Size | Description |
|-------|--------|------|-------------|
| Magic | 0 | 4B | Magic number (0x4B564341 = "KVCA") |
| Version | 4 | 4B | Format version |
| Size | 8 | 8B | Data region size |
| Used | 16 | 8B | Used bytes |
| Free | 24 | 8B | Free bytes |
| Block Count | 32 | 8B | Total blocks |
| Entry Count | 40 | 8B | Cached entries |
| Hits | 48 | 8B | Cache hits |
| Misses | 56 | 8B | Cache misses |
| Created | 64 | 8B | Creation timestamp |
| Modified | 72 | 8B | Last modified timestamp |
| Policy | 80 | 1B | Eviction policy |
| Attached | 81 | 4B | Attached process count |

## Commands

### Create Pool

```bash
cortex cache create <name> --size <size> [options]

Options:
  --size         Pool size (required): 16G, 512M, etc.
  --policy       Eviction policy: lru, lfu, fifo, priority (default: lru)
  --tier         Memory tier: cpu, gpu, disk (default: cpu)
  --max-sequences  Maximum cached sequences (default: 10000)
```

### Lifecycle Commands

```bash
cortex cache destroy <name>    # Destroy pool completely
cortex cache attach <name>     # Attach to existing pool
cortex cache detach <name>     # Detach from pool
```

### Status and Monitoring

```bash
cortex cache status            # List all pools with stats
cortex cache status <name>     # Show specific pool status
cortex cache list              # Alias for status
cortex cache entries <name>    # List entries in pool
cortex cache health <name>     # Check pool health
```

### Cache Operations

```bash
cortex cache evict <name> --percent 25   # Evict 25% of entries
cortex cache persist <name>              # Save to disk
cortex cache restore <name>              # Restore from disk
cortex cache persist <name> --path /custom/path.cache
```

## Eviction Policies

| Policy | Description | Best For |
|--------|-------------|----------|
| LRU | Least Recently Used | General purpose, time-sensitive |
| LFU | Least Frequently Used | Frequency-based access patterns |
| FIFO | First In First Out | Simple, predictable eviction |
| Priority | Priority-based | Manual importance ranking |

### LRU (Least Recently Used)

Evicts entries that haven't been accessed recently. Best for workloads where recent data is more likely to be reused.

### LFU (Least Frequently Used)

Evicts entries with the lowest access count. Best for workloads with stable access patterns where frequently used data should be kept.

### FIFO (First In First Out)

Evicts oldest entries first regardless of access. Simple and predictable.

### Priority

Evicts lowest priority entries first, then uses LRU as tiebreaker. Allows manual control over what stays cached.

## Usage Examples

### Basic Cache Pool

```bash
# Create 16GB LRU cache
cortex cache create llama-cache --size 16G --policy lru

# Check status
cortex cache status llama-cache
# Output:
# POOL                 SIZE         USED         ENTRIES    HIT RATE   POLICY
# llama-cache          16.0G        0.0%         0          0.0%       lru

# View health
cortex cache health llama-cache
# Output:
# Health check for 'llama-cache':
#   Status: HEALTHY
#   Shared Memory: cortex_kv_llama-cache
#   Total Size: 16.00 GB
#   ...
```

### Multiple Pools

```bash
# Create separate pools for different models
cortex cache create llama-70b --size 32G --policy lru
cortex cache create mistral-7b --size 8G --policy lfu
cortex cache create codellama --size 16G --policy priority

# List all pools
cortex cache list
```

### Persistence for Fast Restarts

```bash
# Before shutdown, persist cache
cortex cache persist llama-cache

# After restart, restore cache
cortex cache restore llama-cache
# Output: Restored 1523 entries to 'llama-cache'
```

### Memory Pressure Management

```bash
# When running low on memory, evict some entries
cortex cache evict llama-cache --percent 50

# Or use priority policy and evict low-priority entries
cortex cache create high-mem --size 64G --policy priority
# Store high-priority sequences with priority > 0
# Low priority entries evicted first
```

## Python API

```python
from cortex.kernel_features.kv_cache_manager import (
    KVCacheManager,
    CacheConfig,
)

# Create manager
manager = KVCacheManager()

# Create pool
config = CacheConfig(
    name="my-cache",
    size_bytes=16 * 1024**3,  # 16GB
    policy="lru",
    max_sequences=10000
)
manager.create_pool(config)

# Store KV-cache data
sequence_id = 42
kv_data = b"..."  # Your KV-cache tensor bytes
token_count = 128
prefix_tokens = [1, 2, 3, 4, 5]  # Optional prefix for matching

manager.put("my-cache", sequence_id, kv_data, token_count,
            prefix_tokens=prefix_tokens, priority=10)

# Retrieve data
data = manager.get("my-cache", sequence_id)

# Find by prefix
matches = manager.get_by_prefix("my-cache", prefix_tokens)
for entry, data in matches:
    print(f"Sequence {entry.sequence_id}: {len(data)} bytes")

# Persist and restore
manager.persist("my-cache")
manager.restore("my-cache")

# Cleanup
manager.destroy_pool("my-cache")
```

## Architecture

```
KVCacheManager
├── CacheDatabase (SQLite)
│   ├── pools table (configuration)
│   ├── entries table (metadata)
│   ├── stats table (hit/miss/eviction)
│   └── attachments table (process tracking)
├── SharedMemoryPool
│   ├── Header (4KB structured)
│   ├── Free List (4KB bitmap)
│   └── Data Region (configurable)
└── BitmapAllocator
    └── Thread-safe block allocation

Configuration:
├── ~/.cortex/kv_cache.db       # SQLite database
└── ~/.cortex/kv_persist/       # Persistence files
    └── <pool-name>.cache
```

## Configuration

### Default Resource Limits

| Setting | Default | Description |
|---------|---------|-------------|
| Block Size | 4KB | Allocation granularity |
| Header Size | 4KB | Shared memory header |
| Free List Size | 4KB | Bitmap for allocation |
| Max Sequences | 10,000 | Maximum cached entries |

### Database Schema

**pools table:**
- name (TEXT PRIMARY KEY)
- config (TEXT JSON)
- shm_name (TEXT)
- created_at (REAL)
- last_modified (REAL)

**entries table:**
- pool_name (TEXT)
- sequence_id (INTEGER)
- prefix_hash (TEXT)
- created_at, last_accessed (REAL)
- access_count, token_count (INTEGER)
- size_bytes, offset (INTEGER)
- priority (INTEGER)
- metadata (TEXT JSON)

## Testing

```bash
# Run all tests
pytest tests/test_kv_cache.py -v

# Run specific test class
pytest tests/test_kv_cache.py::TestKVCacheManager -v

# Run with coverage
pytest tests/test_kv_cache.py --cov=cortex.kernel_features.kv_cache_manager

# Run specific test
pytest tests/test_kv_cache.py::TestBitmapAllocator::test_thread_safety -v
```

## Requirements

- Python 3.8+ (for multiprocessing.shared_memory)
- SQLite3 (standard library)
- POSIX-compliant system (Linux, macOS)

### Checking Requirements

```bash
# Verify Python version
python3 --version  # Should be 3.8+

# Verify shared_memory support
python3 -c "from multiprocessing import shared_memory; print('OK')"
```

## Troubleshooting

### "shared_memory not available"

Upgrade to Python 3.8 or later. The `multiprocessing.shared_memory` module was added in Python 3.8.

### "Pool not found" after restart

Shared memory doesn't persist across reboots. Use `cortex cache persist` before shutdown and `cortex cache restore` after restart.

### "Failed to allocate" errors

Pool is full. Either:
1. Increase pool size: `cortex cache destroy old && cortex cache create old --size 32G`
2. Trigger eviction: `cortex cache evict pool-name --percent 50`

### Permission errors on shared memory

Check `/dev/shm` permissions:
```bash
ls -la /dev/shm
# Should be writable by your user
```

### Database locked errors

SQLite database is being accessed by multiple processes. The implementation uses locking, but if issues persist, check for zombie processes.

## Files

- `cortex/kernel_features/kv_cache_manager.py` - Main implementation (~1300 lines)
- `tests/test_kv_cache.py` - Unit tests (~680 lines, 50+ tests)
- `README_KV_CACHE.md` - This documentation

## Related Issues

- [#221 KV-Cache Manager - User-Space Cache Management for LLM Inference](https://github.com/cortexlinux/cortex/issues/221)

## Patent Connection

This implements user-space versions of concepts in Cortex's provisional patent for kernel-managed KV-cache memory regions, enabling efficient transformer inference through shared cache pools.
