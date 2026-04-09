import sqlite3
import asyncio
from concurrent.futures import ThreadPoolExecutor

class SearchEngine:
    def __init__(self, db_path="crawler.db"):
        self.db_path = db_path
        self.executor = ThreadPoolExecutor(max_workers=3)

    def _execute_search(self, query):
        """
        Synchronous search logic executed in a thread pool.
        Matches keywords against title and body.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Simple rank-based SQL: 
        # Title matches get higher priority.
        # We search for any part of the term using %term%.
        sql = """
        SELECT url, origin_url, depth, title,
               ( (title LIKE ?) * 10 + (body LIKE ?) * 1 ) as rank
        FROM Pages 
        WHERE title LIKE ? OR body LIKE ?
        ORDER BY rank DESC
        LIMIT 20
        """
        
        search_term = f"%{query}%"
        cursor.execute(sql, (search_term, search_term, search_term, search_term))
        results = cursor.fetchall()
        
        conn.close()
        return [dict(row) for row in results]

    async def search(self, query):
        """
        Async wrapper to provide non-blocking search execution.
        """
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(self.executor, self._execute_search, query)
        return results

# Usage Example:
# engine = SearchEngine()
# results = await engine.search("python")