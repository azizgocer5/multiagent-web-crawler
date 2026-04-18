import sqlite3
import asyncio
from typing import List, Tuple, Dict, Optional

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.create_function("TRLOWER", 1, lambda s: s.replace('I', 'ı').replace('İ', 'i').lower() if isinstance(s, str) else s)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        
        # Tabloların oluşturulması
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                url TEXT PRIMARY KEY, 
                depth INTEGER, 
                state TEXT DEFAULT 'pending'
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS pages (
                url TEXT PRIMARY KEY, 
                title TEXT, 
                body TEXT, 
                origin_url TEXT, 
                depth INTEGER
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, 
                value TEXT
            )
        """)
        self.conn.commit()

    async def add_to_queue(self, lock: asyncio.Lock, urls: List[str], depth: int):
        async with lock:
            data = [(url, depth, 'pending') for url in urls]
            self.conn.executemany("INSERT OR IGNORE INTO queue (url, depth, state) VALUES (?, ?, ?)", data)
            self.conn.commit()

    async def get_pending(self, limit: int) -> List[Tuple]:
        cursor = self.conn.execute("SELECT url, depth FROM queue WHERE state='pending' LIMIT ?", (limit,))
        return cursor.fetchall()

    async def mark_processing(self, lock: asyncio.Lock, url: str):
        async with lock:
            self.conn.execute("UPDATE queue SET state='processing' WHERE url=?", (url,))
            self.conn.commit()

    async def mark_done(self, lock: asyncio.Lock, url: str):
        async with lock:
            self.conn.execute("UPDATE queue SET state='done' WHERE url=?", (url,))
            self.conn.commit()

    async def save_page(self, lock: asyncio.Lock, url: str, title: str, body: str, origin_url: str, depth: int):
        async with lock:
            self.conn.execute(
                "INSERT OR IGNORE INTO pages (url, title, body, origin_url, depth) VALUES (?, ?, ?, ?, ?)",
                (url, title, body, origin_url, depth)
            )
            self.conn.commit()

    async def resume_processing(self, lock: asyncio.Lock):
        async with lock:
            self.conn.execute("UPDATE queue SET state='pending' WHERE state='processing'")
            self.conn.commit()

    async def get_status(self) -> Dict[str, int]:
        res = {}
        for state in ['pending', 'processing', 'done']:
            cursor = self.conn.execute("SELECT count(*) FROM queue WHERE state=?", (state,))
            res[state] = cursor.fetchone()[0]
        return res

    async def search(self, query: str) -> List[Tuple]:
        # Basit puanlama: title içinde geçiyorsa 10, body içinde geçiyorsa 1 puan
        query_turkish_lowered = query.replace('I', 'ı').replace('İ', 'i').lower()
        q = f"%{query_turkish_lowered}%"
        cursor = self.conn.execute("""
            SELECT url, title, 
            ((CASE WHEN TRLOWER(title) LIKE ? THEN 10 ELSE 0 END) + 
             (CASE WHEN TRLOWER(body) LIKE ? THEN 1 ELSE 0 END)) as score
            FROM pages 
            WHERE TRLOWER(title) LIKE ? OR TRLOWER(body) LIKE ?
            ORDER BY score DESC
        """, (q, q, q, q))
        return cursor.fetchall()

    async def get_setting(self, key: str) -> Optional[str]:
        cursor = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cursor.fetchone()
        return row[0] if row else None

    async def set_setting(self, key: str, value: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
            conn.commit()

if __name__ == "__main__":
    async def test():
        lock = asyncio.Lock()
        db = Database(":memory:")
        
        await db.add_to_queue(lock, ["http://test.com"], 0)
        await db.mark_processing(lock, "http://test.com")
        await db.save_page(lock, "http://test.com", "Test", "Content", "http://start.com", 0)
        await db.mark_done(lock, "http://test.com")
        
        print(await db.get_status())
        print(await db.search("test"))
        
        await db.set_setting(lock, "max_depth", "3")
        print(await db.get_setting("max_depth"))

    asyncio.run(test())