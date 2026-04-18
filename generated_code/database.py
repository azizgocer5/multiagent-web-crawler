import sqlite3
import asyncio
from typing import List, Tuple, Dict, Optional

__all__ = ["Database"]

class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Bağlantıyı kur, WAL modunu aç ve tabloları oluştur."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                url TEXT PRIMARY KEY,
                depth INTEGER,
                state TEXT DEFAULT 'pending'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pages (
                url TEXT PRIMARY KEY,
                title TEXT,
                body TEXT,
                origin_url TEXT,
                depth INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()
        conn.close()

    async def add_to_queue(self, urls: List[str], depth: int, lock: asyncio.Lock) -> None:
        async with lock:
            conn = sqlite3.connect(self.db_path)
            data = [(url, depth, 'pending') for url in urls]
            conn.executemany("INSERT OR IGNORE INTO queue (url, depth, state) VALUES (?, ?, ?)", data)
            conn.commit()
            conn.close()

    async def get_pending(self, limit: int) -> List[Tuple]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT url, depth FROM queue WHERE state = 'pending' LIMIT ?", (limit,))
        results = cursor.fetchall()
        conn.close()
        return results

    async def mark_processing(self, url: str, lock: asyncio.Lock) -> None:
        async with lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute("UPDATE queue SET state = 'processing' WHERE url = ?", (url,))
            conn.commit()
            conn.close()

    async def mark_done(self, url: str, lock: asyncio.Lock) -> None:
        async with lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute("UPDATE queue SET state = 'done' WHERE url = ?", (url,))
            conn.commit()
            conn.close()

    async def save_page(self, url: str, title: str, body: str, origin_url: str, depth: int, lock: asyncio.Lock) -> None:
        async with lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute("INSERT OR IGNORE INTO pages (url, title, body, origin_url, depth) VALUES (?, ?, ?, ?, ?)",
                         (url, title, body, origin_url, depth))
            conn.commit()
            conn.close()

    async def resume_processing(self, lock: asyncio.Lock) -> None:
        async with lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute("UPDATE queue SET state = 'pending' WHERE state = 'processing'")
            conn.commit()
            conn.close()

    async def get_status(self) -> Dict[str, int]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT state, COUNT(*) FROM queue GROUP BY state")
        data = dict(cursor.fetchall())
        conn.close()
        return {k: data.get(k, 0) for k in ['pending', 'processing', 'done']}

    async def search(self, query: str) -> List[Tuple]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        query_str = f"%{query}%"
        # Turkish_lower benzeri basit eşleşme ve puanlama
        cursor.execute("""
            SELECT title, body, 
            ((title LIKE ?) * 10 + (body LIKE ?)) as score 
            FROM pages 
            WHERE score > 0 
            ORDER BY score DESC
        """, (query_str, query_str))
        results = cursor.fetchall()
        conn.close()
        return results

    async def get_setting(self, key: str) -> Optional[str]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    async def set_setting(self, key: str, value: str, lock: asyncio.Lock) -> None:
        async with lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
            conn.commit()
            conn.close()

if __name__ == "__main__":
    async def test():
        db = Database("test.db")
        lock = asyncio.Lock()
        await db.add_to_queue(["http://test.com"], 1, lock)
        await db.mark_processing("http://test.com", lock)
        await db.save_page("http://test.com", "Title", "Body", "origin", 1, lock)
        await db.mark_done("http://test.com", lock)
        print("Status:", await db.get_status())
        print("Search:", await db.search("Title"))
        await db.set_setting("test_key", "test_val", lock)
        print("Setting:", await db.get_setting("test_key"))
        await db.resume_processing(lock)
    
    asyncio.run(test())