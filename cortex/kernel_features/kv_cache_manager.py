#!/usr/bin/env python3
"""
Cortex KV-Cache Manager

User-space KV-cache management for LLM inference optimization.
Implements POSIX shared memory pools with multiple eviction policies,
prefix hash matching, disk persistence, and thread-safe allocation.

Features:
- POSIX shared memory pools for cross-process cache sharing
- Multiple eviction policies: LRU, LFU, FIFO, priority-based
- Prefix hash matching for efficient cache lookup
- Disk persistence for fast restarts
- Thread-safe allocator with bitmap free list
- Process attachment tracking
"""

import os
import sys
import json
import sqlite3
import time
import struct
import hashlib
import threading
import mmap
import pickle
import tempfile
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Tuple, Any, Set
from enum import Enum
from contextlib import contextmanager
import argparse

# Try to import shared_memory (Python 3.8+)
try:
    from multiprocessing import shared_memory
    HAS_SHM = True
except ImportError:
    HAS_SHM = False

# Constants
CORTEX_DIR = Path.home() / ".cortex"
CORTEX_DB = CORTEX_DIR / "kv_cache.db"
CORTEX_PERSIST_DIR = CORTEX_DIR / "kv_persist"
SHM_PREFIX = "cortex_kv_"

# Memory layout constants
HEADER_SIZE = 4096  # 4KB header
FREE_LIST_SIZE = 4096  # 4KB free list bitmap
BLOCK_SIZE = 4096  # 4KB blocks for allocation
MAGIC_NUMBER = 0x4B564341  # "KVCA" in hex
VERSION = 1

# Header structure offsets
HEADER_MAGIC = 0
HEADER_VERSION = 4
HEADER_SIZE_OFFSET = 8
HEADER_USED = 16
HEADER_FREE = 24
HEADER_BLOCK_COUNT = 32
HEADER_ENTRY_COUNT = 40
HEADER_HITS = 48
HEADER_MISSES = 56
HEADER_CREATED = 64
HEADER_MODIFIED = 72
HEADER_POLICY = 80  # 1 byte
HEADER_ATTACHED = 81  # 4 bytes - process count


class CachePolicy(Enum):
    """Eviction policies for cache management."""
    LRU = "lru"  # Least Recently Used
    LFU = "lfu"  # Least Frequently Used
    FIFO = "fifo"  # First In First Out
    PRIORITY = "priority"  # Priority-based (keep high priority entries)


class CacheTier(Enum):
    """Memory tier for cache storage."""
    CPU = "cpu"  # System RAM
    GPU = "gpu"  # GPU memory (future)
    DISK = "disk"  # Disk-backed (mmap)


@dataclass
class CacheConfig:
    """Configuration for a cache pool."""
    name: str
    size_bytes: int
    policy: str = "lru"
    tier: str = "cpu"
    max_sequences: int = 10000
    block_size: int = BLOCK_SIZE
    persist_path: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'CacheConfig':
        return cls(**d)


@dataclass
class CacheEntry:
    """Represents a single cache entry."""
    sequence_id: int
    prefix_hash: str
    created_at: float
    last_accessed: float
    access_count: int
    token_count: int
    size_bytes: int
    offset: int
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'CacheEntry':
        return cls(**d)


@dataclass
class CacheStats:
    """Statistics for a cache pool."""
    total_bytes: int
    used_bytes: int
    free_bytes: int
    entry_count: int
    hit_count: int
    miss_count: int
    hit_rate: float
    eviction_count: int
    attached_processes: int
    created_at: float
    last_modified: float
    policy: str


class CacheDatabase:
    """SQLite database for cache metadata and persistence."""

    def __init__(self, db_path: Path = CORTEX_DB):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._lock = threading.Lock()

    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS pools (
                    name TEXT PRIMARY KEY,
                    config TEXT NOT NULL,
                    shm_name TEXT,
                    created_at REAL DEFAULT (strftime('%s', 'now')),
                    last_modified REAL DEFAULT (strftime('%s', 'now'))
                );

                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pool_name TEXT NOT NULL,
                    sequence_id INTEGER NOT NULL,
                    prefix_hash TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_accessed REAL NOT NULL,
                    access_count INTEGER DEFAULT 1,
                    token_count INTEGER NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    offset INTEGER NOT NULL,
                    priority INTEGER DEFAULT 0,
                    metadata TEXT,
                    UNIQUE(pool_name, sequence_id),
                    FOREIGN KEY(pool_name) REFERENCES pools(name)
                );

                CREATE TABLE IF NOT EXISTS stats (
                    pool_name TEXT PRIMARY KEY,
                    hits INTEGER DEFAULT 0,
                    misses INTEGER DEFAULT 0,
                    evictions INTEGER DEFAULT 0,
                    FOREIGN KEY(pool_name) REFERENCES pools(name)
                );

                CREATE TABLE IF NOT EXISTS attachments (
                    pool_name TEXT NOT NULL,
                    pid INTEGER NOT NULL,
                    attached_at REAL DEFAULT (strftime('%s', 'now')),
                    PRIMARY KEY(pool_name, pid),
                    FOREIGN KEY(pool_name) REFERENCES pools(name)
                );

                CREATE INDEX IF NOT EXISTS idx_entries_pool ON entries(pool_name);
                CREATE INDEX IF NOT EXISTS idx_entries_prefix ON entries(prefix_hash);
                CREATE INDEX IF NOT EXISTS idx_entries_accessed ON entries(last_accessed);
                CREATE INDEX IF NOT EXISTS idx_entries_count ON entries(access_count);
            """)

    @contextmanager
    def _connection(self):
        """Thread-safe database connection."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def save_pool(self, config: CacheConfig, shm_name: str) -> bool:
        """Save pool configuration."""
        with self._connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO pools (name, config, shm_name, last_modified)
                VALUES (?, ?, ?, ?)
            """, (config.name, json.dumps(config.to_dict()), shm_name, time.time()))
            conn.execute("""
                INSERT OR IGNORE INTO stats (pool_name) VALUES (?)
            """, (config.name,))
        return True

    def get_pool(self, name: str) -> Optional[Tuple[CacheConfig, str]]:
        """Get pool configuration."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT config, shm_name FROM pools WHERE name = ?", (name,)
            ).fetchone()
            if row:
                return CacheConfig.from_dict(json.loads(row['config'])), row['shm_name']
        return None

    def list_pools(self) -> List[CacheConfig]:
        """List all pools."""
        with self._connection() as conn:
            rows = conn.execute("SELECT config FROM pools").fetchall()
            return [CacheConfig.from_dict(json.loads(r['config'])) for r in rows]

    def delete_pool(self, name: str) -> bool:
        """Delete pool and all related data."""
        with self._connection() as conn:
            conn.execute("DELETE FROM entries WHERE pool_name = ?", (name,))
            conn.execute("DELETE FROM stats WHERE pool_name = ?", (name,))
            conn.execute("DELETE FROM attachments WHERE pool_name = ?", (name,))
            conn.execute("DELETE FROM pools WHERE name = ?", (name,))
        return True

    def save_entry(self, pool_name: str, entry: CacheEntry) -> bool:
        """Save cache entry."""
        with self._connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO entries
                (pool_name, sequence_id, prefix_hash, created_at, last_accessed,
                 access_count, token_count, size_bytes, offset, priority, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (pool_name, entry.sequence_id, entry.prefix_hash, entry.created_at,
                  entry.last_accessed, entry.access_count, entry.token_count,
                  entry.size_bytes, entry.offset, entry.priority,
                  json.dumps(entry.metadata)))
        return True

    def get_entry(self, pool_name: str, sequence_id: int) -> Optional[CacheEntry]:
        """Get cache entry by sequence ID."""
        with self._connection() as conn:
            row = conn.execute("""
                SELECT * FROM entries WHERE pool_name = ? AND sequence_id = ?
            """, (pool_name, sequence_id)).fetchone()
            if row:
                return CacheEntry(
                    sequence_id=row['sequence_id'],
                    prefix_hash=row['prefix_hash'],
                    created_at=row['created_at'],
                    last_accessed=row['last_accessed'],
                    access_count=row['access_count'],
                    token_count=row['token_count'],
                    size_bytes=row['size_bytes'],
                    offset=row['offset'],
                    priority=row['priority'],
                    metadata=json.loads(row['metadata'] or '{}')
                )
        return None

    def get_entries_by_prefix(self, pool_name: str, prefix_hash: str) -> List[CacheEntry]:
        """Get entries matching prefix hash."""
        with self._connection() as conn:
            rows = conn.execute("""
                SELECT * FROM entries WHERE pool_name = ? AND prefix_hash = ?
            """, (pool_name, prefix_hash)).fetchall()
            return [CacheEntry(
                sequence_id=r['sequence_id'],
                prefix_hash=r['prefix_hash'],
                created_at=r['created_at'],
                last_accessed=r['last_accessed'],
                access_count=r['access_count'],
                token_count=r['token_count'],
                size_bytes=r['size_bytes'],
                offset=r['offset'],
                priority=r['priority'],
                metadata=json.loads(r['metadata'] or '{}')
            ) for r in rows]

    def list_entries(self, pool_name: str) -> List[CacheEntry]:
        """List all entries in a pool."""
        with self._connection() as conn:
            rows = conn.execute("""
                SELECT * FROM entries WHERE pool_name = ?
            """, (pool_name,)).fetchall()
            return [CacheEntry(
                sequence_id=r['sequence_id'],
                prefix_hash=r['prefix_hash'],
                created_at=r['created_at'],
                last_accessed=r['last_accessed'],
                access_count=r['access_count'],
                token_count=r['token_count'],
                size_bytes=r['size_bytes'],
                offset=r['offset'],
                priority=r['priority'],
                metadata=json.loads(r['metadata'] or '{}')
            ) for r in rows]

    def delete_entry(self, pool_name: str, sequence_id: int) -> bool:
        """Delete cache entry."""
        with self._connection() as conn:
            conn.execute("""
                DELETE FROM entries WHERE pool_name = ? AND sequence_id = ?
            """, (pool_name, sequence_id))
        return True

    def update_access(self, pool_name: str, sequence_id: int) -> bool:
        """Update access time and count for an entry."""
        with self._connection() as conn:
            conn.execute("""
                UPDATE entries SET last_accessed = ?, access_count = access_count + 1
                WHERE pool_name = ? AND sequence_id = ?
            """, (time.time(), pool_name, sequence_id))
        return True

    def get_stats(self, pool_name: str) -> Optional[Dict[str, int]]:
        """Get pool statistics."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM stats WHERE pool_name = ?", (pool_name,)
            ).fetchone()
            if row:
                return {'hits': row['hits'], 'misses': row['misses'],
                        'evictions': row['evictions']}
        return None

    def increment_hits(self, pool_name: str) -> bool:
        """Increment hit counter."""
        with self._connection() as conn:
            conn.execute(
                "UPDATE stats SET hits = hits + 1 WHERE pool_name = ?", (pool_name,)
            )
        return True

    def increment_misses(self, pool_name: str) -> bool:
        """Increment miss counter."""
        with self._connection() as conn:
            conn.execute(
                "UPDATE stats SET misses = misses + 1 WHERE pool_name = ?", (pool_name,)
            )
        return True

    def increment_evictions(self, pool_name: str, count: int = 1) -> bool:
        """Increment eviction counter."""
        with self._connection() as conn:
            conn.execute(
                "UPDATE stats SET evictions = evictions + ? WHERE pool_name = ?",
                (count, pool_name)
            )
        return True

    def add_attachment(self, pool_name: str, pid: int) -> bool:
        """Record process attachment."""
        with self._connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO attachments (pool_name, pid, attached_at)
                VALUES (?, ?, ?)
            """, (pool_name, pid, time.time()))
        return True

    def remove_attachment(self, pool_name: str, pid: int) -> bool:
        """Remove process attachment."""
        with self._connection() as conn:
            conn.execute(
                "DELETE FROM attachments WHERE pool_name = ? AND pid = ?",
                (pool_name, pid)
            )
        return True

    def get_attachments(self, pool_name: str) -> List[int]:
        """Get list of attached PIDs."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT pid FROM attachments WHERE pool_name = ?", (pool_name,)
            ).fetchall()
            return [r['pid'] for r in rows]

    def get_eviction_candidates(self, pool_name: str, policy: str,
                                 count: int) -> List[CacheEntry]:
        """Get entries to evict based on policy."""
        with self._connection() as conn:
            if policy == CachePolicy.LRU.value:
                order = "last_accessed ASC"
            elif policy == CachePolicy.LFU.value:
                order = "access_count ASC"
            elif policy == CachePolicy.FIFO.value:
                order = "created_at ASC"
            elif policy == CachePolicy.PRIORITY.value:
                order = "priority ASC, last_accessed ASC"
            else:
                order = "last_accessed ASC"

            rows = conn.execute(f"""
                SELECT * FROM entries WHERE pool_name = ?
                ORDER BY {order} LIMIT ?
            """, (pool_name, count)).fetchall()

            return [CacheEntry(
                sequence_id=r['sequence_id'],
                prefix_hash=r['prefix_hash'],
                created_at=r['created_at'],
                last_accessed=r['last_accessed'],
                access_count=r['access_count'],
                token_count=r['token_count'],
                size_bytes=r['size_bytes'],
                offset=r['offset'],
                priority=r['priority'],
                metadata=json.loads(r['metadata'] or '{}')
            ) for r in rows]


class BitmapAllocator:
    """Thread-safe bitmap-based block allocator."""

    def __init__(self, block_count: int):
        self.block_count = block_count
        self.bitmap_size = (block_count + 7) // 8
        self.bitmap = bytearray(self.bitmap_size)
        self._lock = threading.Lock()

    def allocate(self, blocks_needed: int) -> Optional[int]:
        """Allocate contiguous blocks, returns start block index."""
        with self._lock:
            consecutive = 0
            start = -1

            for i in range(self.block_count):
                byte_idx = i // 8
                bit_idx = i % 8

                if not (self.bitmap[byte_idx] & (1 << bit_idx)):
                    if consecutive == 0:
                        start = i
                    consecutive += 1
                    if consecutive >= blocks_needed:
                        # Mark blocks as used
                        for j in range(start, start + blocks_needed):
                            byte_j = j // 8
                            bit_j = j % 8
                            self.bitmap[byte_j] |= (1 << bit_j)
                        return start
                else:
                    consecutive = 0
                    start = -1

            return None

    def free(self, start_block: int, block_count: int) -> bool:
        """Free blocks starting at given index."""
        with self._lock:
            for i in range(start_block, start_block + block_count):
                if i < self.block_count:
                    byte_idx = i // 8
                    bit_idx = i % 8
                    self.bitmap[byte_idx] &= ~(1 << bit_idx)
        return True

    def get_free_blocks(self) -> int:
        """Count free blocks."""
        with self._lock:
            free = 0
            for i in range(self.block_count):
                byte_idx = i // 8
                bit_idx = i % 8
                if not (self.bitmap[byte_idx] & (1 << bit_idx)):
                    free += 1
            return free

    def get_used_blocks(self) -> int:
        """Count used blocks."""
        return self.block_count - self.get_free_blocks()

    def to_bytes(self) -> bytes:
        """Serialize bitmap."""
        return bytes(self.bitmap)

    def from_bytes(self, data: bytes):
        """Deserialize bitmap."""
        with self._lock:
            self.bitmap = bytearray(data[:self.bitmap_size])


class SharedMemoryPool:
    """POSIX shared memory pool with header and free list."""

    def __init__(self, name: str, size: int, config: CacheConfig,
                 create: bool = True):
        if not HAS_SHM:
            raise RuntimeError("shared_memory not available (requires Python 3.8+)")

        self.name = f"{SHM_PREFIX}{name}"
        self.config = config
        self.data_size = size
        self.total_size = HEADER_SIZE + FREE_LIST_SIZE + size
        self.block_count = size // config.block_size
        self.allocator = BitmapAllocator(self.block_count)
        self._lock = threading.Lock()
        self.shm = None

        if create:
            self._create()
        else:
            self._attach()

    def _create(self):
        """Create new shared memory pool."""
        # Clean up existing if present
        try:
            old = shared_memory.SharedMemory(name=self.name)
            old.close()
            old.unlink()
        except FileNotFoundError:
            pass

        # Create shared memory
        self.shm = shared_memory.SharedMemory(
            name=self.name, create=True, size=self.total_size
        )

        # Initialize header
        self._write_header(
            magic=MAGIC_NUMBER,
            version=VERSION,
            size=self.data_size,
            used=0,
            free=self.data_size,
            block_count=self.block_count,
            entry_count=0,
            hits=0,
            misses=0,
            created=time.time(),
            modified=time.time(),
            policy=list(CachePolicy).index(CachePolicy(self.config.policy)),
            attached=1
        )

        # Initialize free list
        self._write_free_list()

    def _attach(self):
        """Attach to existing shared memory pool."""
        self.shm = shared_memory.SharedMemory(name=self.name)

        # Read and validate header
        header = self._read_header()
        if header['magic'] != MAGIC_NUMBER:
            raise ValueError(f"Invalid magic number: {header['magic']}")
        if header['version'] != VERSION:
            raise ValueError(f"Version mismatch: {header['version']} != {VERSION}")

        # Load free list
        self._read_free_list()

        # Increment attached count
        self._increment_attached()

    def _write_header(self, **kwargs):
        """Write header to shared memory."""
        buf = self.shm.buf
        struct.pack_into('<I', buf, HEADER_MAGIC, kwargs.get('magic', MAGIC_NUMBER))
        struct.pack_into('<I', buf, HEADER_VERSION, kwargs.get('version', VERSION))
        struct.pack_into('<Q', buf, HEADER_SIZE_OFFSET, kwargs.get('size', 0))
        struct.pack_into('<Q', buf, HEADER_USED, kwargs.get('used', 0))
        struct.pack_into('<Q', buf, HEADER_FREE, kwargs.get('free', 0))
        struct.pack_into('<Q', buf, HEADER_BLOCK_COUNT, kwargs.get('block_count', 0))
        struct.pack_into('<Q', buf, HEADER_ENTRY_COUNT, kwargs.get('entry_count', 0))
        struct.pack_into('<Q', buf, HEADER_HITS, kwargs.get('hits', 0))
        struct.pack_into('<Q', buf, HEADER_MISSES, kwargs.get('misses', 0))
        struct.pack_into('<d', buf, HEADER_CREATED, kwargs.get('created', 0.0))
        struct.pack_into('<d', buf, HEADER_MODIFIED, kwargs.get('modified', 0.0))
        struct.pack_into('<B', buf, HEADER_POLICY, kwargs.get('policy', 0))
        struct.pack_into('<I', buf, HEADER_ATTACHED, kwargs.get('attached', 0))

    def _read_header(self) -> Dict[str, Any]:
        """Read header from shared memory."""
        buf = self.shm.buf
        return {
            'magic': struct.unpack_from('<I', buf, HEADER_MAGIC)[0],
            'version': struct.unpack_from('<I', buf, HEADER_VERSION)[0],
            'size': struct.unpack_from('<Q', buf, HEADER_SIZE_OFFSET)[0],
            'used': struct.unpack_from('<Q', buf, HEADER_USED)[0],
            'free': struct.unpack_from('<Q', buf, HEADER_FREE)[0],
            'block_count': struct.unpack_from('<Q', buf, HEADER_BLOCK_COUNT)[0],
            'entry_count': struct.unpack_from('<Q', buf, HEADER_ENTRY_COUNT)[0],
            'hits': struct.unpack_from('<Q', buf, HEADER_HITS)[0],
            'misses': struct.unpack_from('<Q', buf, HEADER_MISSES)[0],
            'created': struct.unpack_from('<d', buf, HEADER_CREATED)[0],
            'modified': struct.unpack_from('<d', buf, HEADER_MODIFIED)[0],
            'policy': struct.unpack_from('<B', buf, HEADER_POLICY)[0],
            'attached': struct.unpack_from('<I', buf, HEADER_ATTACHED)[0],
        }

    def _update_header_field(self, offset: int, fmt: str, value):
        """Update single header field."""
        with self._lock:
            struct.pack_into(fmt, self.shm.buf, offset, value)
            struct.pack_into('<d', self.shm.buf, HEADER_MODIFIED, time.time())

    def _increment_attached(self):
        """Increment attached process count."""
        with self._lock:
            current = struct.unpack_from('<I', self.shm.buf, HEADER_ATTACHED)[0]
            struct.pack_into('<I', self.shm.buf, HEADER_ATTACHED, current + 1)

    def _decrement_attached(self):
        """Decrement attached process count."""
        with self._lock:
            current = struct.unpack_from('<I', self.shm.buf, HEADER_ATTACHED)[0]
            struct.pack_into('<I', self.shm.buf, HEADER_ATTACHED, max(0, current - 1))

    def _write_free_list(self):
        """Write free list bitmap to shared memory."""
        bitmap_data = self.allocator.to_bytes()
        self.shm.buf[HEADER_SIZE:HEADER_SIZE + len(bitmap_data)] = bitmap_data

    def _read_free_list(self):
        """Read free list bitmap from shared memory."""
        bitmap_data = bytes(self.shm.buf[HEADER_SIZE:HEADER_SIZE + FREE_LIST_SIZE])
        self.allocator.from_bytes(bitmap_data)

    def _data_offset(self, block_index: int) -> int:
        """Get data offset for block index."""
        return HEADER_SIZE + FREE_LIST_SIZE + (block_index * self.config.block_size)

    def allocate(self, size: int) -> Optional[int]:
        """Allocate space and return offset."""
        blocks_needed = (size + self.config.block_size - 1) // self.config.block_size
        block_index = self.allocator.allocate(blocks_needed)

        if block_index is None:
            return None

        # Update header
        used = self.allocator.get_used_blocks() * self.config.block_size
        free = self.data_size - used
        self._update_header_field(HEADER_USED, '<Q', used)
        self._update_header_field(HEADER_FREE, '<Q', free)

        # Sync free list
        self._write_free_list()

        return self._data_offset(block_index)

    def free(self, offset: int, size: int) -> bool:
        """Free allocated space."""
        block_index = (offset - HEADER_SIZE - FREE_LIST_SIZE) // self.config.block_size
        blocks = (size + self.config.block_size - 1) // self.config.block_size

        self.allocator.free(block_index, blocks)

        # Update header
        used = self.allocator.get_used_blocks() * self.config.block_size
        free = self.data_size - used
        self._update_header_field(HEADER_USED, '<Q', used)
        self._update_header_field(HEADER_FREE, '<Q', free)

        # Sync free list
        self._write_free_list()

        return True

    def write(self, offset: int, data: bytes) -> bool:
        """Write data at offset."""
        if offset + len(data) > self.total_size:
            return False
        with self._lock:
            self.shm.buf[offset:offset + len(data)] = data
        return True

    def read(self, offset: int, size: int) -> bytes:
        """Read data from offset."""
        with self._lock:
            return bytes(self.shm.buf[offset:offset + size])

    def get_stats(self) -> CacheStats:
        """Get pool statistics."""
        header = self._read_header()
        hits = header['hits']
        misses = header['misses']
        total = hits + misses

        return CacheStats(
            total_bytes=self.data_size,
            used_bytes=header['used'],
            free_bytes=header['free'],
            entry_count=header['entry_count'],
            hit_count=hits,
            miss_count=misses,
            hit_rate=hits / total if total > 0 else 0.0,
            eviction_count=0,
            attached_processes=header['attached'],
            created_at=header['created'],
            last_modified=header['modified'],
            policy=list(CachePolicy)[header['policy']].value
        )

    def increment_hits(self):
        """Increment hit counter."""
        with self._lock:
            current = struct.unpack_from('<Q', self.shm.buf, HEADER_HITS)[0]
            struct.pack_into('<Q', self.shm.buf, HEADER_HITS, current + 1)

    def increment_misses(self):
        """Increment miss counter."""
        with self._lock:
            current = struct.unpack_from('<Q', self.shm.buf, HEADER_MISSES)[0]
            struct.pack_into('<Q', self.shm.buf, HEADER_MISSES, current + 1)

    def update_entry_count(self, count: int):
        """Update entry count in header."""
        self._update_header_field(HEADER_ENTRY_COUNT, '<Q', count)

    def close(self):
        """Close shared memory (detach)."""
        if self.shm:
            self._decrement_attached()
            self.shm.close()
            self.shm = None

    def destroy(self):
        """Destroy shared memory pool."""
        if self.shm:
            self.shm.close()
            try:
                self.shm.unlink()
            except FileNotFoundError:
                pass
            self.shm = None


class KVCacheManager:
    """Main KV-Cache manager for LLM inference optimization."""

    def __init__(self, db_path: Path = CORTEX_DB):
        self.db = CacheDatabase(db_path)
        self.pools: Dict[str, SharedMemoryPool] = {}
        self._lock = threading.Lock()
        self.persist_dir = CORTEX_PERSIST_DIR
        self.persist_dir.mkdir(parents=True, exist_ok=True)

    def create_pool(self, config: CacheConfig) -> bool:
        """Create a new cache pool."""
        with self._lock:
            if config.name in self.pools:
                print(f"Pool '{config.name}' already exists")
                return False

            try:
                pool = SharedMemoryPool(config.name, config.size_bytes, config, create=True)
                self.pools[config.name] = pool
                self.db.save_pool(config, pool.name)
                self.db.add_attachment(config.name, os.getpid())

                size_gb = config.size_bytes / (1024**3)
                print(f"Created cache pool '{config.name}' ({size_gb:.2f} GB, policy={config.policy})")
                return True
            except Exception as e:
                print(f"Failed to create pool: {e}")
                return False

    def attach_pool(self, name: str) -> bool:
        """Attach to existing cache pool."""
        with self._lock:
            if name in self.pools:
                return True

            pool_data = self.db.get_pool(name)
            if not pool_data:
                print(f"Pool '{name}' not found")
                return False

            config, shm_name = pool_data
            try:
                pool = SharedMemoryPool(name, config.size_bytes, config, create=False)
                self.pools[name] = pool
                self.db.add_attachment(name, os.getpid())
                print(f"Attached to pool '{name}'")
                return True
            except Exception as e:
                print(f"Failed to attach to pool: {e}")
                return False

    def detach_pool(self, name: str) -> bool:
        """Detach from cache pool."""
        with self._lock:
            if name not in self.pools:
                return True

            self.pools[name].close()
            del self.pools[name]
            self.db.remove_attachment(name, os.getpid())
            print(f"Detached from pool '{name}'")
            return True

    def destroy_pool(self, name: str) -> bool:
        """Destroy cache pool completely."""
        with self._lock:
            if name in self.pools:
                self.pools[name].destroy()
                del self.pools[name]
            else:
                # Try to destroy even if not attached
                pool_data = self.db.get_pool(name)
                if pool_data:
                    config, _ = pool_data
                    try:
                        pool = SharedMemoryPool(name, config.size_bytes, config, create=False)
                        pool.destroy()
                    except Exception:
                        pass

            self.db.delete_pool(name)

            # Remove persist file if exists
            persist_path = self.persist_dir / f"{name}.cache"
            if persist_path.exists():
                persist_path.unlink()

            print(f"Destroyed pool '{name}'")
            return True

    def _get_pool(self, name: str) -> Optional[SharedMemoryPool]:
        """Get pool, attaching if necessary."""
        if name not in self.pools:
            if not self.attach_pool(name):
                return None
        return self.pools.get(name)

    def put(self, pool_name: str, sequence_id: int, data: bytes,
            token_count: int, prefix_tokens: Optional[List[int]] = None,
            priority: int = 0, metadata: Optional[Dict] = None) -> bool:
        """Store KV-cache data."""
        pool = self._get_pool(pool_name)
        if not pool:
            return False

        pool_data = self.db.get_pool(pool_name)
        if not pool_data:
            return False
        config, _ = pool_data

        # Check if we need to evict
        entries = self.db.list_entries(pool_name)
        if len(entries) >= config.max_sequences:
            self._evict(pool_name, config.policy, 1)

        # Calculate prefix hash
        prefix_hash = self._compute_prefix_hash(prefix_tokens) if prefix_tokens else ""

        # Allocate space
        offset = pool.allocate(len(data))
        if offset is None:
            # Try eviction
            needed_bytes = len(data)
            entries_to_evict = (needed_bytes // config.block_size) + 1
            self._evict(pool_name, config.policy, entries_to_evict)
            offset = pool.allocate(len(data))
            if offset is None:
                print(f"Failed to allocate {len(data)} bytes")
                return False

        # Write data
        pool.write(offset, data)

        # Create entry
        entry = CacheEntry(
            sequence_id=sequence_id,
            prefix_hash=prefix_hash,
            created_at=time.time(),
            last_accessed=time.time(),
            access_count=1,
            token_count=token_count,
            size_bytes=len(data),
            offset=offset,
            priority=priority,
            metadata=metadata or {}
        )

        self.db.save_entry(pool_name, entry)
        pool.update_entry_count(len(self.db.list_entries(pool_name)))

        return True

    def get(self, pool_name: str, sequence_id: int) -> Optional[bytes]:
        """Retrieve KV-cache data."""
        pool = self._get_pool(pool_name)
        if not pool:
            self.db.increment_misses(pool_name)
            return None

        entry = self.db.get_entry(pool_name, sequence_id)
        if not entry:
            pool.increment_misses()
            self.db.increment_misses(pool_name)
            return None

        # Update access stats
        self.db.update_access(pool_name, sequence_id)
        pool.increment_hits()
        self.db.increment_hits(pool_name)

        # Read data
        return pool.read(entry.offset, entry.size_bytes)

    def get_by_prefix(self, pool_name: str, prefix_tokens: List[int]) -> List[Tuple[CacheEntry, bytes]]:
        """Find cache entries matching prefix."""
        pool = self._get_pool(pool_name)
        if not pool:
            return []

        prefix_hash = self._compute_prefix_hash(prefix_tokens)
        entries = self.db.get_entries_by_prefix(pool_name, prefix_hash)

        results = []
        for entry in entries:
            data = pool.read(entry.offset, entry.size_bytes)
            self.db.update_access(pool_name, entry.sequence_id)
            results.append((entry, data))

        if results:
            pool.increment_hits()
            self.db.increment_hits(pool_name)
        else:
            pool.increment_misses()
            self.db.increment_misses(pool_name)

        return results

    def delete(self, pool_name: str, sequence_id: int) -> bool:
        """Delete cache entry."""
        pool = self._get_pool(pool_name)
        if not pool:
            return False

        entry = self.db.get_entry(pool_name, sequence_id)
        if not entry:
            return False

        pool.free(entry.offset, entry.size_bytes)
        self.db.delete_entry(pool_name, sequence_id)
        pool.update_entry_count(len(self.db.list_entries(pool_name)))

        return True

    def _compute_prefix_hash(self, tokens: List[int]) -> str:
        """Compute hash of prefix tokens for matching."""
        if not tokens:
            return ""
        data = struct.pack(f'<{len(tokens)}I', *tokens)
        return hashlib.sha256(data).hexdigest()[:16]

    def _evict(self, pool_name: str, policy: str, count: int) -> int:
        """Evict entries based on policy."""
        pool = self._get_pool(pool_name)
        if not pool:
            return 0

        candidates = self.db.get_eviction_candidates(pool_name, policy, count)
        evicted = 0

        for entry in candidates:
            pool.free(entry.offset, entry.size_bytes)
            self.db.delete_entry(pool_name, entry.sequence_id)
            evicted += 1

        if evicted > 0:
            self.db.increment_evictions(pool_name, evicted)
            pool.update_entry_count(len(self.db.list_entries(pool_name)))

        return evicted

    def evict(self, pool_name: str, percent: float = 25.0) -> int:
        """Manually evict percentage of entries."""
        pool_data = self.db.get_pool(pool_name)
        if not pool_data:
            print(f"Pool '{pool_name}' not found")
            return 0

        config, _ = pool_data
        entries = self.db.list_entries(pool_name)
        count = max(1, int(len(entries) * percent / 100))

        evicted = self._evict(pool_name, config.policy, count)
        print(f"Evicted {evicted} entries from '{pool_name}'")
        return evicted

    def persist(self, pool_name: str, path: Optional[str] = None) -> bool:
        """Persist cache to disk."""
        pool = self._get_pool(pool_name)
        if not pool:
            return False

        persist_path = Path(path) if path else self.persist_dir / f"{pool_name}.cache"
        persist_path.parent.mkdir(parents=True, exist_ok=True)

        pool_data = self.db.get_pool(pool_name)
        if not pool_data:
            return False
        config, _ = pool_data

        entries = self.db.list_entries(pool_name)

        # Save data
        persist_data = {
            'version': VERSION,
            'config': config.to_dict(),
            'entries': [],
            'timestamp': time.time()
        }

        for entry in entries:
            data = pool.read(entry.offset, entry.size_bytes)
            persist_data['entries'].append({
                'entry': entry.to_dict(),
                'data': data.hex()
            })

        with open(persist_path, 'wb') as f:
            pickle.dump(persist_data, f)

        size_mb = persist_path.stat().st_size / (1024**2)
        print(f"Persisted '{pool_name}' to {persist_path} ({size_mb:.2f} MB)")
        return True

    def restore(self, pool_name: str, path: Optional[str] = None) -> bool:
        """Restore cache from disk."""
        persist_path = Path(path) if path else self.persist_dir / f"{pool_name}.cache"

        if not persist_path.exists():
            print(f"No persist file found: {persist_path}")
            return False

        with open(persist_path, 'rb') as f:
            persist_data = pickle.load(f)

        if persist_data.get('version') != VERSION:
            print(f"Version mismatch in persist file")
            return False

        config = CacheConfig.from_dict(persist_data['config'])

        # Create pool if needed
        if pool_name not in self.pools:
            if not self.create_pool(config):
                return False

        pool = self.pools[pool_name]

        # Restore entries
        restored = 0
        for item in persist_data['entries']:
            entry_dict = item['entry']
            data = bytes.fromhex(item['data'])

            if self.put(pool_name, entry_dict['sequence_id'], data,
                       entry_dict['token_count'],
                       priority=entry_dict.get('priority', 0),
                       metadata=entry_dict.get('metadata', {})):
                restored += 1

        print(f"Restored {restored} entries to '{pool_name}'")
        return True

    def status(self, pool_name: Optional[str] = None) -> None:
        """Display pool status."""
        if pool_name:
            pools = [self.db.get_pool(pool_name)]
            if pools[0] is None:
                print(f"Pool '{pool_name}' not found")
                return
            pools = [(pools[0][0], pools[0][1])]
        else:
            pools = [(cfg, "") for cfg in self.db.list_pools()]

        if not pools:
            print("No cache pools found")
            return

        print(f"\n{'POOL':<20} {'SIZE':<12} {'USED':<12} {'ENTRIES':<10} {'HIT RATE':<10} {'POLICY':<10}")
        print("-" * 80)

        for item in pools:
            if item[0] is None:
                continue
            cfg = item[0]

            # Try to get live stats
            try:
                pool = self._get_pool(cfg.name)
                if pool:
                    stats = pool.get_stats()
                    used_pct = (stats.used_bytes / stats.total_bytes * 100) if stats.total_bytes > 0 else 0
                    print(f"{cfg.name:<20} {cfg.size_bytes/1e9:.1f}G{'':<7} "
                          f"{used_pct:.1f}%{'':<7} {stats.entry_count:<10} "
                          f"{stats.hit_rate*100:.1f}%{'':<5} {stats.policy:<10}")
                else:
                    db_stats = self.db.get_stats(cfg.name)
                    hits = db_stats.get('hits', 0) if db_stats else 0
                    misses = db_stats.get('misses', 0) if db_stats else 0
                    total = hits + misses
                    hit_rate = hits / total * 100 if total > 0 else 0
                    entries = len(self.db.list_entries(cfg.name))
                    print(f"{cfg.name:<20} {cfg.size_bytes/1e9:.1f}G{'':<7} "
                          f"N/A{'':<9} {entries:<10} {hit_rate:.1f}%{'':<5} {cfg.policy:<10}")
            except Exception:
                print(f"{cfg.name:<20} {cfg.size_bytes/1e9:.1f}G{'':<7} "
                      f"ERROR{'':<7} N/A{'':<9} N/A{'':<9} {cfg.policy:<10}")

    def list_entries(self, pool_name: str) -> None:
        """List entries in a pool."""
        entries = self.db.list_entries(pool_name)

        if not entries:
            print(f"No entries in pool '{pool_name}'")
            return

        print(f"\n{'SEQ ID':<12} {'TOKENS':<10} {'SIZE':<12} {'ACCESSES':<10} {'PRIORITY':<10} {'LAST ACCESS':<20}")
        print("-" * 80)

        for entry in entries[:50]:  # Limit display
            last_access = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry.last_accessed))
            print(f"{entry.sequence_id:<12} {entry.token_count:<10} "
                  f"{entry.size_bytes/1024:.1f}KB{'':<6} {entry.access_count:<10} "
                  f"{entry.priority:<10} {last_access:<20}")

        if len(entries) > 50:
            print(f"\n... and {len(entries) - 50} more entries")

    def health(self, pool_name: str) -> bool:
        """Check pool health."""
        pool_data = self.db.get_pool(pool_name)
        if not pool_data:
            print(f"Pool '{pool_name}' not found")
            return False

        config, shm_name = pool_data

        try:
            pool = self._get_pool(pool_name)
            if not pool:
                print(f"UNHEALTHY: Cannot attach to pool")
                return False

            stats = pool.get_stats()

            print(f"\nHealth check for '{pool_name}':")
            print(f"  Status: HEALTHY")
            print(f"  Shared Memory: {shm_name}")
            print(f"  Total Size: {stats.total_bytes / 1e9:.2f} GB")
            print(f"  Used: {stats.used_bytes / 1e9:.2f} GB ({stats.used_bytes / stats.total_bytes * 100:.1f}%)")
            print(f"  Free: {stats.free_bytes / 1e9:.2f} GB")
            print(f"  Entries: {stats.entry_count}")
            print(f"  Hit Rate: {stats.hit_rate * 100:.1f}%")
            print(f"  Attached Processes: {stats.attached_processes}")
            print(f"  Policy: {stats.policy}")

            return True
        except Exception as e:
            print(f"UNHEALTHY: {e}")
            return False

    def cleanup(self) -> None:
        """Clean up stale attachments and pools."""
        for pool_name in list(self.pools.keys()):
            self.detach_pool(pool_name)


def parse_size(size_str: str) -> int:
    """Parse size string like '16G', '512M', '1024K'."""
    size_str = size_str.strip().upper()
    multipliers = {'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4}

    if size_str[-1] in multipliers:
        return int(float(size_str[:-1]) * multipliers[size_str[-1]])
    return int(size_str)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog='cortex-cache',
        description='Cortex KV-Cache Manager - User-space cache management for LLM inference'
    )
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Create command
    create_parser = subparsers.add_parser('create', help='Create a new cache pool')
    create_parser.add_argument('name', help='Pool name')
    create_parser.add_argument('--size', required=True, help='Pool size (e.g., 16G, 512M)')
    create_parser.add_argument('--policy', choices=['lru', 'lfu', 'fifo', 'priority'],
                               default='lru', help='Eviction policy')
    create_parser.add_argument('--tier', choices=['cpu', 'gpu', 'disk'],
                               default='cpu', help='Memory tier')
    create_parser.add_argument('--max-sequences', type=int, default=10000,
                               help='Maximum number of cached sequences')

    # Destroy command
    destroy_parser = subparsers.add_parser('destroy', help='Destroy a cache pool')
    destroy_parser.add_argument('name', help='Pool name')

    # Attach command
    attach_parser = subparsers.add_parser('attach', help='Attach to existing pool')
    attach_parser.add_argument('name', help='Pool name')

    # Detach command
    detach_parser = subparsers.add_parser('detach', help='Detach from pool')
    detach_parser.add_argument('name', help='Pool name')

    # Status command
    status_parser = subparsers.add_parser('status', help='Show pool status')
    status_parser.add_argument('name', nargs='?', help='Pool name (optional)')

    # List command (alias for status)
    list_parser = subparsers.add_parser('list', help='List all pools')

    # Entries command
    entries_parser = subparsers.add_parser('entries', help='List entries in pool')
    entries_parser.add_argument('name', help='Pool name')

    # Evict command
    evict_parser = subparsers.add_parser('evict', help='Evict entries from pool')
    evict_parser.add_argument('name', help='Pool name')
    evict_parser.add_argument('--percent', type=float, default=25.0,
                              help='Percentage of entries to evict')

    # Persist command
    persist_parser = subparsers.add_parser('persist', help='Persist pool to disk')
    persist_parser.add_argument('name', help='Pool name')
    persist_parser.add_argument('--path', help='Custom persist path')

    # Restore command
    restore_parser = subparsers.add_parser('restore', help='Restore pool from disk')
    restore_parser.add_argument('name', help='Pool name')
    restore_parser.add_argument('--path', help='Custom persist path')

    # Health command
    health_parser = subparsers.add_parser('health', help='Check pool health')
    health_parser.add_argument('name', help='Pool name')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    manager = KVCacheManager()

    try:
        if args.command == 'create':
            config = CacheConfig(
                name=args.name,
                size_bytes=parse_size(args.size),
                policy=args.policy,
                tier=args.tier,
                max_sequences=args.max_sequences
            )
            manager.create_pool(config)

        elif args.command == 'destroy':
            manager.destroy_pool(args.name)

        elif args.command == 'attach':
            manager.attach_pool(args.name)

        elif args.command == 'detach':
            manager.detach_pool(args.name)

        elif args.command == 'status':
            manager.status(args.name)

        elif args.command == 'list':
            manager.status()

        elif args.command == 'entries':
            manager.list_entries(args.name)

        elif args.command == 'evict':
            manager.evict(args.name, args.percent)

        elif args.command == 'persist':
            manager.persist(args.name, args.path)

        elif args.command == 'restore':
            manager.restore(args.name, args.path)

        elif args.command == 'health':
            manager.health(args.name)

    finally:
        manager.cleanup()


if __name__ == '__main__':
    main()
