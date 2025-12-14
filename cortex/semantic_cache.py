import json
import os
import sqlite3
import hashlib
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class CacheStats:
    hits: int
    misses: int

    @property
    def total(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.hits / self.total


class SemanticCache:
    def __init__(
        self,
        db_path: str = "/var/lib/cortex/cache.db",
        max_entries: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
    ):
        self.db_path = db_path
        self.max_entries = max_entries if max_entries is not None else int(os.environ.get("CORTEX_CACHE_MAX_ENTRIES", "500"))
        self.similarity_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else float(os.environ.get("CORTEX_CACHE_SIMILARITY_THRESHOLD", "0.86"))
        )
        self._ensure_db_directory()
        self._init_database()

    def _ensure_db_directory(self) -> None:
        db_dir = Path(self.db_path).parent
        try:
            db_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            user_dir = Path.home() / ".cortex"
            user_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = str(user_dir / "cache.db")

    def _init_database(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_cache_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    system_hash TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    prompt_hash TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    commands_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_accessed TEXT NOT NULL,
                    hit_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_llm_cache_unique
                ON llm_cache_entries(provider, model, system_hash, prompt_hash)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_llm_cache_lru
                ON llm_cache_entries(last_accessed)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS llm_cache_stats (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    hits INTEGER NOT NULL DEFAULT 0,
                    misses INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            cur.execute("INSERT OR IGNORE INTO llm_cache_stats(id, hits, misses) VALUES (1, 0, 0)")
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _utcnow_iso() -> str:
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _system_hash(self, system_prompt: str) -> str:
        return self._hash_text(system_prompt)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        buf: List[str] = []
        current: List[str] = []
        for ch in text.lower():
            if ch.isalnum() or ch in ("-", "_", "."):
                current.append(ch)
            else:
                if current:
                    buf.append("".join(current))
                    current = []
        if current:
            buf.append("".join(current))
        return buf

    @classmethod
    def _embed(cls, text: str, dims: int = 128) -> List[float]:
        vec = [0.0] * dims
        tokens = cls._tokenize(text)
        if not tokens:
            return vec

        for token in tokens:
            h = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(h, "big", signed=False)
            idx = value % dims
            sign = -1.0 if (value >> 63) & 1 else 1.0
            vec[idx] += sign

        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    @staticmethod
    def _pack_embedding(vec: List[float]) -> bytes:
        return json.dumps(vec, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _unpack_embedding(blob: bytes) -> List[float]:
        return json.loads(blob.decode("utf-8"))

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = 0.0
        for i in range(len(a)):
            dot += a[i] * b[i]
        return dot

    def _record_hit(self, conn: sqlite3.Connection) -> None:
        conn.execute("UPDATE llm_cache_stats SET hits = hits + 1 WHERE id = 1")

    def _record_miss(self, conn: sqlite3.Connection) -> None:
        conn.execute("UPDATE llm_cache_stats SET misses = misses + 1 WHERE id = 1")

    def get_commands(
        self,
        prompt: str,
        provider: str,
        model: str,
        system_prompt: str,
        candidate_limit: int = 200,
    ) -> Optional[List[str]]:
        system_hash = self._system_hash(system_prompt)
        prompt_hash = self._hash_text(prompt)
        now = self._utcnow_iso()

        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, commands_json
                FROM llm_cache_entries
                WHERE provider = ? AND model = ? AND system_hash = ? AND prompt_hash = ?
                LIMIT 1
                """,
                (provider, model, system_hash, prompt_hash),
            )
            row = cur.fetchone()
            if row is not None:
                entry_id, commands_json = row
                cur.execute(
                    """
                    UPDATE llm_cache_entries
                    SET last_accessed = ?, hit_count = hit_count + 1
                    WHERE id = ?
                    """,
                    (now, entry_id),
                )
                self._record_hit(conn)
                conn.commit()
                return json.loads(commands_json)

            query_vec = self._embed(prompt)

            cur.execute(
                """
                SELECT id, embedding, commands_json
                FROM llm_cache_entries
                WHERE provider = ? AND model = ? AND system_hash = ?
                ORDER BY last_accessed DESC
                LIMIT ?
                """,
                (provider, model, system_hash, candidate_limit),
            )

            best: Optional[Tuple[int, float, str]] = None
            for entry_id, embedding_blob, commands_json in cur.fetchall():
                vec = self._unpack_embedding(embedding_blob)
                sim = self._cosine(query_vec, vec)
                if best is None or sim > best[1]:
                    best = (entry_id, sim, commands_json)

            if best is not None and best[1] >= self.similarity_threshold:
                cur.execute(
                    """
                    UPDATE llm_cache_entries
                    SET last_accessed = ?, hit_count = hit_count + 1
                    WHERE id = ?
                    """,
                    (now, best[0]),
                )
                self._record_hit(conn)
                conn.commit()
                return json.loads(best[2])

            self._record_miss(conn)
            conn.commit()
            return None
        finally:
            conn.close()

    def put_commands(
        self,
        prompt: str,
        provider: str,
        model: str,
        system_prompt: str,
        commands: List[str],
    ) -> None:
        system_hash = self._system_hash(system_prompt)
        prompt_hash = self._hash_text(prompt)
        now = self._utcnow_iso()
        vec = self._embed(prompt)
        embedding_blob = self._pack_embedding(vec)

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO llm_cache_entries(
                    provider, model, system_hash, prompt, prompt_hash, embedding, commands_json,
                    created_at, last_accessed, hit_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((
                    SELECT hit_count FROM llm_cache_entries
                    WHERE provider = ? AND model = ? AND system_hash = ? AND prompt_hash = ?
                ), 0))
                """,
                (
                    provider,
                    model,
                    system_hash,
                    prompt,
                    prompt_hash,
                    embedding_blob,
                    json.dumps(commands, separators=(",", ":")),
                    now,
                    now,
                    provider,
                    model,
                    system_hash,
                    prompt_hash,
                ),
            )
            self._evict_if_needed(conn)
            conn.commit()
        finally:
            conn.close()

    def _evict_if_needed(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(1) FROM llm_cache_entries")
        count = int(cur.fetchone()[0])
        if count <= self.max_entries:
            return

        to_delete = count - self.max_entries
        cur.execute(
            """
            DELETE FROM llm_cache_entries
            WHERE id IN (
                SELECT id FROM llm_cache_entries
                ORDER BY last_accessed ASC
                LIMIT ?
            )
            """,
            (to_delete,),
        )

    def stats(self) -> CacheStats:
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT hits, misses FROM llm_cache_stats WHERE id = 1")
            row = cur.fetchone()
            if row is None:
                return CacheStats(hits=0, misses=0)
            return CacheStats(hits=int(row[0]), misses=int(row[1]))
        finally:
            conn.close()
