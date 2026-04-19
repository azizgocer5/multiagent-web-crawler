import asyncio
import sqlite3
from typing import Dict, List, Optional, Tuple


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self._create_schema()

    def _create_schema(self) -> None:
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS queue (
                    url TEXT PRIMARY KEY,
                    depth INTEGER NOT NULL,
                    state TEXT NOT NULL DEFAULT 'pending'
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pages (
                    url TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    body TEXT NOT NULL DEFAULT '',
                    origin_url TEXT NOT NULL DEFAULT '',
                    depth INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_queue_state ON queue(state)"
            )

    async def force_pending(self, url: str, depth: int, lock: asyncio.Lock) -> None:
        async with lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO queue (url, depth, state) VALUES (?, ?, 'pending')",
                (url, depth),
            )
            self.conn.commit()

    async def add_to_queue(self, urls: List[str], depth: int, lock: asyncio.Lock) -> int:
        if not urls:
            return 0

        async with lock:
            cursor = self.conn.cursor()
            cursor.executemany(
                "INSERT OR IGNORE INTO queue (url, depth, state) VALUES (?, ?, 'pending')",
                [(url, depth) for url in urls],
            )
            self.conn.commit()
            return cursor.rowcount if cursor.rowcount != -1 else 0

    async def get_pending(self, limit: int) -> List[Tuple[str, int]]:
        cursor = self.conn.execute(
            "SELECT url, depth FROM queue WHERE state = 'pending' ORDER BY rowid LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()
        return [(row["url"], row["depth"]) for row in rows]

    async def mark_processing(self, url: str, lock: asyncio.Lock) -> None:
        async with lock:
            self.conn.execute(
                "UPDATE queue SET state = 'processing' WHERE url = ?",
                (url,),
            )
            self.conn.commit()

    async def mark_done(self, url: str, lock: asyncio.Lock) -> None:
        async with lock:
            self.conn.execute("DELETE FROM queue WHERE url = ?", (url,))
            self.conn.commit()

    async def save_page(
        self,
        url: str,
        title: str,
        body: str,
        origin_url: str,
        depth: int,
        lock: asyncio.Lock,
    ) -> None:
        async with lock:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO pages (url, title, body, origin_url, depth)
                VALUES (?, ?, ?, ?, ?)
                """,
                (url, title, body, origin_url, depth),
            )
            self.conn.commit()

    async def resume_processing(self, lock: asyncio.Lock) -> None:
        async with lock:
            self.conn.execute(
                "UPDATE queue SET state = 'pending' WHERE state = 'processing'"
            )
            self.conn.commit()

    async def get_status(self) -> Dict[str, int]:
        queue_counts = {
            row["state"]: row["count"]
            for row in self.conn.execute(
                "SELECT state, COUNT(*) AS count FROM queue GROUP BY state"
            ).fetchall()
        }
        done = self.conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        return {
            "pending": queue_counts.get("pending", 0),
            "processing": queue_counts.get("processing", 0),
            "done": done,
        }

    async def search(self, query: str) -> List[Dict]:
        normalized = query.lower().strip()
        like_query = f"%{normalized}%"
        rows = self.conn.execute(
            """
            SELECT
                url,
                title,
                origin_url,
                depth,
                (CASE WHEN lower(title) LIKE ? THEN 10 ELSE 0 END +
                 CASE WHEN lower(body) LIKE ? THEN 1 ELSE 0 END) AS score
            FROM pages
            WHERE lower(title) LIKE ? OR lower(body) LIKE ?
            ORDER BY score DESC, depth ASC, url ASC
            """,
            (like_query, like_query, like_query, like_query),
        ).fetchall()
        return [dict(row) for row in rows]

    async def get_setting(self, key: str) -> Optional[str]:
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        ).fetchone()
        return row["value"] if row else None

    async def set_setting(self, key: str, value: str, lock: asyncio.Lock) -> None:
        async with lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
            self.conn.commit()

    async def close(self) -> None:
        self.conn.close()
