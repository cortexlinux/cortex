#!/usr/bin/env python3
"""
Comprehensive tests for Cortex KV-Cache Manager.

Tests cover:
- Configuration dataclasses
- Database operations
- Bitmap allocator
- Shared memory pools
- Cache manager operations
- Eviction policies
- Persistence/restore
- Multi-process attachment
"""

import os
import sys
import time
import json
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, PropertyMock

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from cortex.kernel_features.kv_cache_manager import (
    CachePolicy,
    CacheTier,
    CacheConfig,
    CacheEntry,
    CacheStats,
    CacheDatabase,
    BitmapAllocator,
    SharedMemoryPool,
    KVCacheManager,
    parse_size,
    CORTEX_DB,
    CORTEX_PERSIST_DIR,
    SHM_PREFIX,
    HEADER_SIZE,
    FREE_LIST_SIZE,
    BLOCK_SIZE,
    MAGIC_NUMBER,
    VERSION,
)


class TestCachePolicy(unittest.TestCase):
    """Tests for CachePolicy enum."""

    def test_policies_exist(self):
        """Test all expected policies exist."""
        self.assertEqual(CachePolicy.LRU.value, "lru")
        self.assertEqual(CachePolicy.LFU.value, "lfu")
        self.assertEqual(CachePolicy.FIFO.value, "fifo")
        self.assertEqual(CachePolicy.PRIORITY.value, "priority")

    def test_policy_count(self):
        """Test correct number of policies."""
        self.assertEqual(len(CachePolicy), 4)


class TestCacheTier(unittest.TestCase):
    """Tests for CacheTier enum."""

    def test_tiers_exist(self):
        """Test all expected tiers exist."""
        self.assertEqual(CacheTier.CPU.value, "cpu")
        self.assertEqual(CacheTier.GPU.value, "gpu")
        self.assertEqual(CacheTier.DISK.value, "disk")


class TestCacheConfig(unittest.TestCase):
    """Tests for CacheConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = CacheConfig(name="test", size_bytes=1024*1024)
        self.assertEqual(config.name, "test")
        self.assertEqual(config.size_bytes, 1024*1024)
        self.assertEqual(config.policy, "lru")
        self.assertEqual(config.tier, "cpu")
        self.assertEqual(config.max_sequences, 10000)
        self.assertEqual(config.block_size, BLOCK_SIZE)
        self.assertIsNone(config.persist_path)

    def test_custom_config(self):
        """Test custom configuration."""
        config = CacheConfig(
            name="custom",
            size_bytes=16*1024*1024*1024,
            policy="lfu",
            tier="gpu",
            max_sequences=5000,
            block_size=8192,
            persist_path="/tmp/cache.dat"
        )
        self.assertEqual(config.name, "custom")
        self.assertEqual(config.policy, "lfu")
        self.assertEqual(config.tier, "gpu")
        self.assertEqual(config.max_sequences, 5000)
        self.assertEqual(config.block_size, 8192)
        self.assertEqual(config.persist_path, "/tmp/cache.dat")

    def test_to_dict(self):
        """Test serialization to dict."""
        config = CacheConfig(name="test", size_bytes=1024)
        d = config.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d['name'], "test")
        self.assertEqual(d['size_bytes'], 1024)

    def test_from_dict(self):
        """Test deserialization from dict."""
        d = {
            'name': 'restored',
            'size_bytes': 2048,
            'policy': 'fifo',
            'tier': 'cpu',
            'max_sequences': 100,
            'block_size': 4096,
            'persist_path': None
        }
        config = CacheConfig.from_dict(d)
        self.assertEqual(config.name, 'restored')
        self.assertEqual(config.size_bytes, 2048)
        self.assertEqual(config.policy, 'fifo')


class TestCacheEntry(unittest.TestCase):
    """Tests for CacheEntry dataclass."""

    def test_default_entry(self):
        """Test default entry values."""
        entry = CacheEntry(
            sequence_id=1,
            prefix_hash="abc123",
            created_at=1000.0,
            last_accessed=1000.0,
            access_count=1,
            token_count=100,
            size_bytes=4096,
            offset=8192
        )
        self.assertEqual(entry.sequence_id, 1)
        self.assertEqual(entry.prefix_hash, "abc123")
        self.assertEqual(entry.priority, 0)
        self.assertEqual(entry.metadata, {})

    def test_entry_with_metadata(self):
        """Test entry with metadata."""
        entry = CacheEntry(
            sequence_id=2,
            prefix_hash="def456",
            created_at=2000.0,
            last_accessed=2000.0,
            access_count=5,
            token_count=200,
            size_bytes=8192,
            offset=16384,
            priority=10,
            metadata={'model': 'llama', 'layer': 32}
        )
        self.assertEqual(entry.priority, 10)
        self.assertEqual(entry.metadata['model'], 'llama')

    def test_entry_serialization(self):
        """Test entry to/from dict."""
        entry = CacheEntry(
            sequence_id=1,
            prefix_hash="test",
            created_at=1.0,
            last_accessed=2.0,
            access_count=3,
            token_count=100,
            size_bytes=1024,
            offset=2048
        )
        d = entry.to_dict()
        restored = CacheEntry.from_dict(d)
        self.assertEqual(entry.sequence_id, restored.sequence_id)
        self.assertEqual(entry.prefix_hash, restored.prefix_hash)


class TestCacheStats(unittest.TestCase):
    """Tests for CacheStats dataclass."""

    def test_stats_creation(self):
        """Test stats creation."""
        stats = CacheStats(
            total_bytes=1024*1024,
            used_bytes=512*1024,
            free_bytes=512*1024,
            entry_count=10,
            hit_count=80,
            miss_count=20,
            hit_rate=0.8,
            eviction_count=5,
            attached_processes=2,
            created_at=1000.0,
            last_modified=2000.0,
            policy="lru"
        )
        self.assertEqual(stats.total_bytes, 1024*1024)
        self.assertEqual(stats.hit_rate, 0.8)
        self.assertEqual(stats.attached_processes, 2)


class TestBitmapAllocator(unittest.TestCase):
    """Tests for BitmapAllocator class."""

    def test_allocate_single_block(self):
        """Test allocating a single block."""
        allocator = BitmapAllocator(100)
        result = allocator.allocate(1)
        self.assertEqual(result, 0)
        self.assertEqual(allocator.get_used_blocks(), 1)
        self.assertEqual(allocator.get_free_blocks(), 99)

    def test_allocate_multiple_blocks(self):
        """Test allocating multiple contiguous blocks."""
        allocator = BitmapAllocator(100)
        result = allocator.allocate(10)
        self.assertEqual(result, 0)
        self.assertEqual(allocator.get_used_blocks(), 10)

    def test_allocate_sequential(self):
        """Test sequential allocations."""
        allocator = BitmapAllocator(100)
        first = allocator.allocate(5)
        second = allocator.allocate(5)
        self.assertEqual(first, 0)
        self.assertEqual(second, 5)
        self.assertEqual(allocator.get_used_blocks(), 10)

    def test_free_blocks(self):
        """Test freeing blocks."""
        allocator = BitmapAllocator(100)
        allocator.allocate(10)
        allocator.free(0, 5)
        self.assertEqual(allocator.get_used_blocks(), 5)
        self.assertEqual(allocator.get_free_blocks(), 95)

    def test_allocate_after_free(self):
        """Test allocation reuses freed space."""
        allocator = BitmapAllocator(100)
        allocator.allocate(10)
        allocator.free(0, 5)
        result = allocator.allocate(3)
        self.assertEqual(result, 0)

    def test_allocate_fails_when_full(self):
        """Test allocation fails when no space."""
        allocator = BitmapAllocator(10)
        allocator.allocate(10)
        result = allocator.allocate(1)
        self.assertIsNone(result)

    def test_allocate_fails_fragmented(self):
        """Test allocation fails with fragmentation."""
        allocator = BitmapAllocator(5)
        # Allocate all 5 blocks
        for _ in range(5):
            allocator.allocate(1)
        # Free alternating blocks: 0, 2, 4 (leaving 1, 3 allocated)
        allocator.free(0, 1)
        allocator.free(2, 1)
        allocator.free(4, 1)
        # Can't allocate 2 contiguous (only single free blocks available)
        result = allocator.allocate(2)
        self.assertIsNone(result)

    def test_bitmap_serialization(self):
        """Test bitmap to/from bytes."""
        allocator = BitmapAllocator(100)
        allocator.allocate(25)
        data = allocator.to_bytes()

        allocator2 = BitmapAllocator(100)
        allocator2.from_bytes(data)
        self.assertEqual(allocator2.get_used_blocks(), 25)

    def test_thread_safety(self):
        """Test thread-safe allocation."""
        allocator = BitmapAllocator(1000)
        results = []

        def allocate_blocks():
            for _ in range(10):
                result = allocator.allocate(1)
                if result is not None:
                    results.append(result)

        threads = [threading.Thread(target=allocate_blocks) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have 100 unique allocations
        self.assertEqual(len(results), 100)
        self.assertEqual(len(set(results)), 100)


class TestCacheDatabase(unittest.TestCase):
    """Tests for CacheDatabase class."""

    def setUp(self):
        """Set up test database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_cache.db"
        self.db = CacheDatabase(self.db_path)

    def tearDown(self):
        """Clean up test database."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_get_pool(self):
        """Test saving and retrieving pool."""
        config = CacheConfig(name="test-pool", size_bytes=1024*1024)
        self.db.save_pool(config, "shm_test")

        result = self.db.get_pool("test-pool")
        self.assertIsNotNone(result)
        retrieved_config, shm_name = result
        self.assertEqual(retrieved_config.name, "test-pool")
        self.assertEqual(shm_name, "shm_test")

    def test_get_nonexistent_pool(self):
        """Test getting non-existent pool."""
        result = self.db.get_pool("nonexistent")
        self.assertIsNone(result)

    def test_list_pools(self):
        """Test listing all pools."""
        configs = [
            CacheConfig(name="pool1", size_bytes=1024),
            CacheConfig(name="pool2", size_bytes=2048),
            CacheConfig(name="pool3", size_bytes=4096),
        ]
        for cfg in configs:
            self.db.save_pool(cfg, f"shm_{cfg.name}")

        pools = self.db.list_pools()
        self.assertEqual(len(pools), 3)
        names = {p.name for p in pools}
        self.assertEqual(names, {"pool1", "pool2", "pool3"})

    def test_delete_pool(self):
        """Test deleting pool."""
        config = CacheConfig(name="to-delete", size_bytes=1024)
        self.db.save_pool(config, "shm_delete")

        self.db.delete_pool("to-delete")
        result = self.db.get_pool("to-delete")
        self.assertIsNone(result)

    def test_save_and_get_entry(self):
        """Test saving and retrieving entry."""
        config = CacheConfig(name="entry-pool", size_bytes=1024)
        self.db.save_pool(config, "shm_entry")

        entry = CacheEntry(
            sequence_id=42,
            prefix_hash="hash123",
            created_at=time.time(),
            last_accessed=time.time(),
            access_count=1,
            token_count=100,
            size_bytes=512,
            offset=1024
        )
        self.db.save_entry("entry-pool", entry)

        retrieved = self.db.get_entry("entry-pool", 42)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.sequence_id, 42)
        self.assertEqual(retrieved.prefix_hash, "hash123")

    def test_get_entries_by_prefix(self):
        """Test getting entries by prefix hash."""
        config = CacheConfig(name="prefix-pool", size_bytes=1024)
        self.db.save_pool(config, "shm_prefix")

        # Save entries with same prefix
        for i in range(5):
            entry = CacheEntry(
                sequence_id=i,
                prefix_hash="common_prefix",
                created_at=time.time(),
                last_accessed=time.time(),
                access_count=1,
                token_count=100,
                size_bytes=512,
                offset=1024 * i
            )
            self.db.save_entry("prefix-pool", entry)

        # Save entry with different prefix
        entry = CacheEntry(
            sequence_id=99,
            prefix_hash="different",
            created_at=time.time(),
            last_accessed=time.time(),
            access_count=1,
            token_count=100,
            size_bytes=512,
            offset=99999
        )
        self.db.save_entry("prefix-pool", entry)

        results = self.db.get_entries_by_prefix("prefix-pool", "common_prefix")
        self.assertEqual(len(results), 5)

    def test_list_entries(self):
        """Test listing all entries."""
        config = CacheConfig(name="list-pool", size_bytes=1024)
        self.db.save_pool(config, "shm_list")

        for i in range(10):
            entry = CacheEntry(
                sequence_id=i,
                prefix_hash=f"hash{i}",
                created_at=time.time(),
                last_accessed=time.time(),
                access_count=1,
                token_count=100,
                size_bytes=512,
                offset=1024 * i
            )
            self.db.save_entry("list-pool", entry)

        entries = self.db.list_entries("list-pool")
        self.assertEqual(len(entries), 10)

    def test_delete_entry(self):
        """Test deleting entry."""
        config = CacheConfig(name="del-pool", size_bytes=1024)
        self.db.save_pool(config, "shm_del")

        entry = CacheEntry(
            sequence_id=1,
            prefix_hash="hash",
            created_at=time.time(),
            last_accessed=time.time(),
            access_count=1,
            token_count=100,
            size_bytes=512,
            offset=1024
        )
        self.db.save_entry("del-pool", entry)
        self.db.delete_entry("del-pool", 1)

        retrieved = self.db.get_entry("del-pool", 1)
        self.assertIsNone(retrieved)

    def test_update_access(self):
        """Test updating access time and count."""
        config = CacheConfig(name="access-pool", size_bytes=1024)
        self.db.save_pool(config, "shm_access")

        entry = CacheEntry(
            sequence_id=1,
            prefix_hash="hash",
            created_at=time.time(),
            last_accessed=time.time(),
            access_count=1,
            token_count=100,
            size_bytes=512,
            offset=1024
        )
        self.db.save_entry("access-pool", entry)

        time.sleep(0.1)
        self.db.update_access("access-pool", 1)

        retrieved = self.db.get_entry("access-pool", 1)
        self.assertEqual(retrieved.access_count, 2)
        self.assertGreater(retrieved.last_accessed, entry.last_accessed)

    def test_stats_operations(self):
        """Test stats increment operations."""
        config = CacheConfig(name="stats-pool", size_bytes=1024)
        self.db.save_pool(config, "shm_stats")

        self.db.increment_hits("stats-pool")
        self.db.increment_hits("stats-pool")
        self.db.increment_misses("stats-pool")
        self.db.increment_evictions("stats-pool", 3)

        stats = self.db.get_stats("stats-pool")
        self.assertEqual(stats['hits'], 2)
        self.assertEqual(stats['misses'], 1)
        self.assertEqual(stats['evictions'], 3)

    def test_attachment_operations(self):
        """Test process attachment tracking."""
        config = CacheConfig(name="attach-pool", size_bytes=1024)
        self.db.save_pool(config, "shm_attach")

        self.db.add_attachment("attach-pool", 1234)
        self.db.add_attachment("attach-pool", 5678)

        pids = self.db.get_attachments("attach-pool")
        self.assertEqual(set(pids), {1234, 5678})

        self.db.remove_attachment("attach-pool", 1234)
        pids = self.db.get_attachments("attach-pool")
        self.assertEqual(pids, [5678])

    def test_eviction_candidates_lru(self):
        """Test getting LRU eviction candidates."""
        config = CacheConfig(name="lru-pool", size_bytes=1024)
        self.db.save_pool(config, "shm_lru")

        base_time = time.time()
        for i in range(10):
            entry = CacheEntry(
                sequence_id=i,
                prefix_hash="hash",
                created_at=base_time,
                last_accessed=base_time + i,  # Later = more recent
                access_count=1,
                token_count=100,
                size_bytes=512,
                offset=1024 * i
            )
            self.db.save_entry("lru-pool", entry)

        # Should get oldest accessed first
        candidates = self.db.get_eviction_candidates("lru-pool", "lru", 3)
        self.assertEqual(len(candidates), 3)
        self.assertEqual(candidates[0].sequence_id, 0)
        self.assertEqual(candidates[1].sequence_id, 1)
        self.assertEqual(candidates[2].sequence_id, 2)

    def test_eviction_candidates_lfu(self):
        """Test getting LFU eviction candidates."""
        config = CacheConfig(name="lfu-pool", size_bytes=1024)
        self.db.save_pool(config, "shm_lfu")

        base_time = time.time()
        for i in range(10):
            entry = CacheEntry(
                sequence_id=i,
                prefix_hash="hash",
                created_at=base_time,
                last_accessed=base_time,
                access_count=i + 1,  # Higher = more accessed
                token_count=100,
                size_bytes=512,
                offset=1024 * i
            )
            self.db.save_entry("lfu-pool", entry)

        # Should get least accessed first
        candidates = self.db.get_eviction_candidates("lfu-pool", "lfu", 3)
        self.assertEqual(len(candidates), 3)
        self.assertEqual(candidates[0].sequence_id, 0)
        self.assertEqual(candidates[0].access_count, 1)

    def test_eviction_candidates_fifo(self):
        """Test getting FIFO eviction candidates."""
        config = CacheConfig(name="fifo-pool", size_bytes=1024)
        self.db.save_pool(config, "shm_fifo")

        base_time = time.time()
        for i in range(10):
            entry = CacheEntry(
                sequence_id=i,
                prefix_hash="hash",
                created_at=base_time + i,  # Later = newer
                last_accessed=base_time + 100,
                access_count=1,
                token_count=100,
                size_bytes=512,
                offset=1024 * i
            )
            self.db.save_entry("fifo-pool", entry)

        # Should get oldest created first
        candidates = self.db.get_eviction_candidates("fifo-pool", "fifo", 3)
        self.assertEqual(len(candidates), 3)
        self.assertEqual(candidates[0].sequence_id, 0)

    def test_eviction_candidates_priority(self):
        """Test getting priority-based eviction candidates."""
        config = CacheConfig(name="priority-pool", size_bytes=1024)
        self.db.save_pool(config, "shm_priority")

        base_time = time.time()
        for i in range(10):
            entry = CacheEntry(
                sequence_id=i,
                prefix_hash="hash",
                created_at=base_time,
                last_accessed=base_time,
                access_count=1,
                token_count=100,
                size_bytes=512,
                offset=1024 * i,
                priority=i  # Higher = more important
            )
            self.db.save_entry("priority-pool", entry)

        # Should get lowest priority first
        candidates = self.db.get_eviction_candidates("priority-pool", "priority", 3)
        self.assertEqual(len(candidates), 3)
        self.assertEqual(candidates[0].priority, 0)


class TestSharedMemoryPool(unittest.TestCase):
    """Tests for SharedMemoryPool class."""

    def setUp(self):
        """Set up test pool."""
        self.pool_name = f"test_{os.getpid()}_{time.time()}"
        self.config = CacheConfig(name=self.pool_name, size_bytes=1024*1024)  # 1MB
        self.pool = None

    def tearDown(self):
        """Clean up test pool."""
        if self.pool:
            try:
                self.pool.destroy()
            except Exception:
                pass

    def test_create_pool(self):
        """Test creating shared memory pool."""
        self.pool = SharedMemoryPool(self.pool_name, self.config.size_bytes,
                                     self.config, create=True)
        self.assertIsNotNone(self.pool.shm)
        self.assertEqual(self.pool.name, f"{SHM_PREFIX}{self.pool_name}")

    def test_pool_header(self):
        """Test pool header initialization."""
        self.pool = SharedMemoryPool(self.pool_name, self.config.size_bytes,
                                     self.config, create=True)
        header = self.pool._read_header()
        self.assertEqual(header['magic'], MAGIC_NUMBER)
        self.assertEqual(header['version'], VERSION)
        self.assertEqual(header['size'], self.config.size_bytes)

    def test_allocate_and_write(self):
        """Test allocating space and writing data."""
        self.pool = SharedMemoryPool(self.pool_name, self.config.size_bytes,
                                     self.config, create=True)

        data = b"Hello, KV-Cache!"
        offset = self.pool.allocate(len(data))
        self.assertIsNotNone(offset)

        self.pool.write(offset, data)
        read_data = self.pool.read(offset, len(data))
        self.assertEqual(read_data, data)

    def test_free_space(self):
        """Test freeing allocated space."""
        self.pool = SharedMemoryPool(self.pool_name, self.config.size_bytes,
                                     self.config, create=True)

        initial_stats = self.pool.get_stats()

        offset = self.pool.allocate(4096)
        self.pool.free(offset, 4096)

        final_stats = self.pool.get_stats()
        self.assertEqual(initial_stats.free_bytes, final_stats.free_bytes)

    def test_stats(self):
        """Test getting pool statistics."""
        self.pool = SharedMemoryPool(self.pool_name, self.config.size_bytes,
                                     self.config, create=True)

        stats = self.pool.get_stats()
        self.assertEqual(stats.total_bytes, self.config.size_bytes)
        self.assertEqual(stats.used_bytes, 0)
        self.assertEqual(stats.free_bytes, self.config.size_bytes)
        self.assertEqual(stats.attached_processes, 1)

    def test_hit_miss_counters(self):
        """Test hit/miss counter operations."""
        self.pool = SharedMemoryPool(self.pool_name, self.config.size_bytes,
                                     self.config, create=True)

        self.pool.increment_hits()
        self.pool.increment_hits()
        self.pool.increment_misses()

        stats = self.pool.get_stats()
        self.assertEqual(stats.hit_count, 2)
        self.assertEqual(stats.miss_count, 1)
        self.assertAlmostEqual(stats.hit_rate, 2/3, places=2)


class TestKVCacheManager(unittest.TestCase):
    """Tests for KVCacheManager class."""

    def setUp(self):
        """Set up test manager."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_manager.db"
        self.manager = KVCacheManager(self.db_path)
        self.pool_name = f"test_{os.getpid()}_{time.time()}"

    def tearDown(self):
        """Clean up test manager."""
        try:
            self.manager.destroy_pool(self.pool_name)
        except Exception:
            pass
        self.manager.cleanup()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_pool(self):
        """Test creating cache pool."""
        config = CacheConfig(name=self.pool_name, size_bytes=1024*1024)
        result = self.manager.create_pool(config)
        self.assertTrue(result)
        self.assertIn(self.pool_name, self.manager.pools)

    def test_create_duplicate_pool(self):
        """Test creating duplicate pool fails."""
        config = CacheConfig(name=self.pool_name, size_bytes=1024*1024)
        self.manager.create_pool(config)
        result = self.manager.create_pool(config)
        self.assertFalse(result)

    def test_destroy_pool(self):
        """Test destroying cache pool."""
        config = CacheConfig(name=self.pool_name, size_bytes=1024*1024)
        self.manager.create_pool(config)

        result = self.manager.destroy_pool(self.pool_name)
        self.assertTrue(result)
        self.assertNotIn(self.pool_name, self.manager.pools)

    def test_put_and_get(self):
        """Test storing and retrieving data."""
        config = CacheConfig(name=self.pool_name, size_bytes=1024*1024)
        self.manager.create_pool(config)

        data = b"Test KV-cache data"
        result = self.manager.put(self.pool_name, 1, data, 100)
        self.assertTrue(result)

        retrieved = self.manager.get(self.pool_name, 1)
        self.assertEqual(retrieved, data)

    def test_get_nonexistent(self):
        """Test getting non-existent entry."""
        config = CacheConfig(name=self.pool_name, size_bytes=1024*1024)
        self.manager.create_pool(config)

        result = self.manager.get(self.pool_name, 999)
        self.assertIsNone(result)

    def test_delete_entry(self):
        """Test deleting entry."""
        config = CacheConfig(name=self.pool_name, size_bytes=1024*1024)
        self.manager.create_pool(config)

        self.manager.put(self.pool_name, 1, b"data", 100)
        result = self.manager.delete(self.pool_name, 1)
        self.assertTrue(result)

        retrieved = self.manager.get(self.pool_name, 1)
        self.assertIsNone(retrieved)

    def test_put_with_prefix(self):
        """Test storing with prefix tokens."""
        config = CacheConfig(name=self.pool_name, size_bytes=1024*1024)
        self.manager.create_pool(config)

        prefix_tokens = [1, 2, 3, 4, 5]
        data = b"Prefixed data"

        result = self.manager.put(self.pool_name, 1, data, 100,
                                  prefix_tokens=prefix_tokens)
        self.assertTrue(result)

        # Find by prefix
        results = self.manager.get_by_prefix(self.pool_name, prefix_tokens)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][1], data)

    def test_eviction(self):
        """Test manual eviction."""
        config = CacheConfig(name=self.pool_name, size_bytes=1024*1024,
                            max_sequences=10)
        self.manager.create_pool(config)

        # Add entries
        for i in range(10):
            self.manager.put(self.pool_name, i, f"data{i}".encode(), 100)

        # Evict 50%
        evicted = self.manager.evict(self.pool_name, 50.0)
        self.assertEqual(evicted, 5)

        # Check remaining
        entries = self.manager.db.list_entries(self.pool_name)
        self.assertEqual(len(entries), 5)

    def test_auto_eviction(self):
        """Test automatic eviction when max_sequences reached."""
        config = CacheConfig(name=self.pool_name, size_bytes=1024*1024,
                            max_sequences=5)
        self.manager.create_pool(config)

        # Add more than max
        for i in range(10):
            self.manager.put(self.pool_name, i, f"data{i}".encode(), 100)
            time.sleep(0.01)  # Ensure different timestamps

        # Should have evicted to stay under limit
        entries = self.manager.db.list_entries(self.pool_name)
        self.assertLessEqual(len(entries), 5)

    def test_persist_and_restore(self):
        """Test persisting and restoring cache."""
        config = CacheConfig(name=self.pool_name, size_bytes=1024*1024)
        self.manager.create_pool(config)

        # Add data
        test_data = [
            (1, b"First entry", 100),
            (2, b"Second entry", 200),
            (3, b"Third entry", 300),
        ]
        for seq_id, data, tokens in test_data:
            self.manager.put(self.pool_name, seq_id, data, tokens)

        # Persist
        persist_path = Path(self.temp_dir) / "test.cache"
        result = self.manager.persist(self.pool_name, str(persist_path))
        self.assertTrue(result)
        self.assertTrue(persist_path.exists())

        # Destroy and recreate
        self.manager.destroy_pool(self.pool_name)

        # Restore
        result = self.manager.restore(self.pool_name, str(persist_path))
        self.assertTrue(result)

        # Verify data
        for seq_id, data, _ in test_data:
            retrieved = self.manager.get(self.pool_name, seq_id)
            self.assertEqual(retrieved, data)

    def test_status_output(self):
        """Test status method doesn't crash."""
        config = CacheConfig(name=self.pool_name, size_bytes=1024*1024)
        self.manager.create_pool(config)

        # Should not raise
        self.manager.status(self.pool_name)
        self.manager.status()

    def test_health_check(self):
        """Test health check method."""
        config = CacheConfig(name=self.pool_name, size_bytes=1024*1024)
        self.manager.create_pool(config)

        result = self.manager.health(self.pool_name)
        self.assertTrue(result)

    def test_health_check_nonexistent(self):
        """Test health check on non-existent pool."""
        result = self.manager.health("nonexistent")
        self.assertFalse(result)


class TestParseSize(unittest.TestCase):
    """Tests for parse_size function."""

    def test_parse_bytes(self):
        """Test parsing raw bytes."""
        self.assertEqual(parse_size("1024"), 1024)

    def test_parse_kilobytes(self):
        """Test parsing kilobytes."""
        self.assertEqual(parse_size("1K"), 1024)
        self.assertEqual(parse_size("1k"), 1024)

    def test_parse_megabytes(self):
        """Test parsing megabytes."""
        self.assertEqual(parse_size("1M"), 1024*1024)
        self.assertEqual(parse_size("512M"), 512*1024*1024)

    def test_parse_gigabytes(self):
        """Test parsing gigabytes."""
        self.assertEqual(parse_size("1G"), 1024**3)
        self.assertEqual(parse_size("16G"), 16*1024**3)

    def test_parse_terabytes(self):
        """Test parsing terabytes."""
        self.assertEqual(parse_size("1T"), 1024**4)

    def test_parse_decimal(self):
        """Test parsing decimal values."""
        self.assertEqual(parse_size("1.5G"), int(1.5 * 1024**3))
        self.assertEqual(parse_size("0.5M"), int(0.5 * 1024**2))


class TestPrefixHash(unittest.TestCase):
    """Tests for prefix hash computation."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test_hash.db"
        self.manager = KVCacheManager(self.db_path)

    def tearDown(self):
        self.manager.cleanup()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_same_prefix_same_hash(self):
        """Test same prefix produces same hash."""
        tokens = [1, 2, 3, 4, 5]
        hash1 = self.manager._compute_prefix_hash(tokens)
        hash2 = self.manager._compute_prefix_hash(tokens)
        self.assertEqual(hash1, hash2)

    def test_different_prefix_different_hash(self):
        """Test different prefix produces different hash."""
        hash1 = self.manager._compute_prefix_hash([1, 2, 3])
        hash2 = self.manager._compute_prefix_hash([1, 2, 4])
        self.assertNotEqual(hash1, hash2)

    def test_empty_prefix(self):
        """Test empty prefix returns empty string."""
        result = self.manager._compute_prefix_hash([])
        self.assertEqual(result, "")

    def test_hash_length(self):
        """Test hash is correct length."""
        hash1 = self.manager._compute_prefix_hash([1, 2, 3])
        self.assertEqual(len(hash1), 16)


class TestMultiProcess(unittest.TestCase):
    """Tests for multi-process cache sharing."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.pool_name = f"multi_{os.getpid()}_{time.time()}"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_attach_to_existing_pool(self):
        """Test attaching to existing pool."""
        db_path = Path(self.temp_dir) / "multi.db"

        # Create pool with first manager
        manager1 = KVCacheManager(db_path)
        config = CacheConfig(name=self.pool_name, size_bytes=1024*1024)
        manager1.create_pool(config)
        manager1.put(self.pool_name, 1, b"shared data", 100)

        # Attach with second manager
        manager2 = KVCacheManager(db_path)
        result = manager2.attach_pool(self.pool_name)
        self.assertTrue(result)

        # Read data from second manager
        data = manager2.get(self.pool_name, 1)
        self.assertEqual(data, b"shared data")

        # Cleanup
        manager2.cleanup()
        manager1.destroy_pool(self.pool_name)
        manager1.cleanup()

    def test_detach_from_pool(self):
        """Test detaching from pool."""
        db_path = Path(self.temp_dir) / "detach.db"

        manager = KVCacheManager(db_path)
        config = CacheConfig(name=self.pool_name, size_bytes=1024*1024)
        manager.create_pool(config)

        result = manager.detach_pool(self.pool_name)
        self.assertTrue(result)
        self.assertNotIn(self.pool_name, manager.pools)

        # Cleanup (destroy even though detached)
        manager.destroy_pool(self.pool_name)
        manager.cleanup()


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and error handling."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "edge.db"
        self.manager = KVCacheManager(self.db_path)
        self.pool_name = f"edge_{os.getpid()}"

    def tearDown(self):
        try:
            self.manager.destroy_pool(self.pool_name)
        except Exception:
            pass
        self.manager.cleanup()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_put_to_nonexistent_pool(self):
        """Test putting to non-existent pool."""
        result = self.manager.put("nonexistent", 1, b"data", 100)
        self.assertFalse(result)

    def test_get_from_nonexistent_pool(self):
        """Test getting from non-existent pool."""
        result = self.manager.get("nonexistent", 1)
        self.assertIsNone(result)

    def test_delete_from_nonexistent_pool(self):
        """Test deleting from non-existent pool."""
        result = self.manager.delete("nonexistent", 1)
        self.assertFalse(result)

    def test_large_data(self):
        """Test storing large data."""
        config = CacheConfig(name=self.pool_name, size_bytes=10*1024*1024)  # 10MB
        self.manager.create_pool(config)

        # Store 1MB of data
        large_data = b"x" * (1024 * 1024)
        result = self.manager.put(self.pool_name, 1, large_data, 10000)
        self.assertTrue(result)

        retrieved = self.manager.get(self.pool_name, 1)
        self.assertEqual(retrieved, large_data)

    def test_many_entries(self):
        """Test storing many entries."""
        config = CacheConfig(name=self.pool_name, size_bytes=10*1024*1024,
                            max_sequences=1000)
        self.manager.create_pool(config)

        # Store 100 entries
        for i in range(100):
            data = f"entry_{i}".encode()
            self.manager.put(self.pool_name, i, data, 10)

        # Verify some entries
        self.assertEqual(self.manager.get(self.pool_name, 0), b"entry_0")
        self.assertEqual(self.manager.get(self.pool_name, 99), b"entry_99")

    def test_restore_nonexistent_file(self):
        """Test restoring from non-existent file."""
        result = self.manager.restore(self.pool_name, "/nonexistent/path.cache")
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
