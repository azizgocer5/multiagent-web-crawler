import aiosqlite
import asyncio
from typing import List, Dict, Any

class Database:
    def __init__(self, db_path: str = "crawler.db"):
        self.db_path = db_path
        self.write_lock = asyncio.Lock()

    async def initialize(self):
        """Creates tables and enables WAL mode for concurrency."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            # Pages Table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    origin_url TEXT,
                    depth INTEGER,
                    title TEXT,
                    body TEXT
                )
            """)
            # Queue Table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    state TEXT DEFAULT 'pending',
                    depth INTEGER
                )
            """)
            await db.commit()

    async def is_visited(self, url: str) -> bool:
        """
        Checks if a URL has been indexed in 'pages' 
        or is currently tracked in 'queue'.
        """
        async with aiosqlite.connect(self.db_path) as db:
            # Check if url exists in either table
            query = """
                SELECT 1 FROM pages WHERE url = ? 
                UNION 
                SELECT 1 FROM queue WHERE url = ? 
                LIMIT 1
            """
            async with db.execute(query, (url, url)) as cursor:
                result = await cursor.fetchone()
                return result is not None

    async def mark_as_pending(self, url: str, depth: int):
        """Adds a new URL to the queue if it hasn't been seen before."""
        async with self.write_lock:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT OR IGNORE INTO queue (url, state, depth)
                    VALUES (?, 'pending', ?)
                """, (url, depth))
                await db.commit()

    # ... [Keep previous methods: get_status_report, get_last_logs, 
    #      save_page_and_links, get_pending_urls, fetch_all_pages] ...

    async def get_status_report(self) -> Dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as db:
            page_count_res = await db.execute("SELECT COUNT(*) FROM pages")
            page_count = await page_count_res.fetchone()
            queue_res = await db.execute("SELECT state, COUNT(*) FROM queue GROUP BY state")
            queue_rows = await queue_res.fetchall()
            return {"total_indexed": page_count[0], "queue_stats": {row[0]: row[1] for row in queue_rows}}

    async def get_last_logs(self, limit: int = 10) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT url, origin_url, title FROM pages ORDER BY id DESC LIMIT ?"
            async with db.execute(query, (limit,)) as cursor:
                return [dict(row) for row in await cursor.fetchall()]

    async def save_page_and_links(self, page_data: Dict[str, Any], links: List[str]):
        async with self.write_lock:
            async with aiosqlite.connect(self.db_path) as db:
                try:
                    await db.execute("""
                        INSERT OR REPLACE INTO pages (url, origin_url, depth, title, body)
                        VALUES (?, ?, ?, ?, ?)
                    """, (page_data['url'], page_data['origin_url'], page_data['depth'], 
                          page_data['title'], page_data['body']))
                    await db.execute("UPDATE queue SET state = 'done' WHERE url = ?", (page_data['url'],))
                    for link in links:
                        await db.execute("INSERT OR IGNORE INTO queue (url, state, depth) VALUES (?, 'pending', ?)", 
                                         (link, page_data['depth'] + 1))
                    await db.commit()
                except Exception as e:
                    await db.rollback()
                    raise e

    async def get_pending_urls(self, limit: int = 10) -> List[Dict]:
        async with self.write_lock:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("SELECT url, depth FROM queue WHERE state = 'pending' LIMIT ?", (limit,))
                rows = await cursor.fetchall()
                urls = [{"url": row[0], "depth": row[1]} for row in rows]
                for item in urls:
                    await db.execute("UPDATE queue SET state = 'processing' WHERE url = ?", (item['url'],))
                await db.commit()
                return urls

    async def fetch_all_pages(self) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM pages") as cursor:
                return [dict(row) for row in await cursor.fetchall()]