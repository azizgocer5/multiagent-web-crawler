import asyncio
from html.parser import HTMLParser
import aiohttp
import sqlite3
from urllib.parse import urljoin, urlparse
import logging
import threading

class MiniParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self._skip = False
        self.body = ''
        self.title = ''
        self.links = set()

    def handle_starttag(self, tag, attrs):
        if tag in ['script', 'style', 'head']:
            self._skip = True
        elif tag == 'a':
            for name, value in attrs:
                if name == 'href':
                    self.links.add(urljoin(self.base_url, value))

    def handle_endtag(self, tag):
        self._skip = False

    def handle_data(self, data):
        if not self._skip:
            if self.title:
                self.title += data
            else:
                self.body += data

    def get_links(self):
        return [link for link in self.links if urlparse(link).scheme in ['http', 'https']]

class CrawlerService:
    def __init__(self, db, worker_count=30):
        self.db = db
        self.worker_count = worker_count
        self.memory_queue = None
        self.db_lock = None
        self._running = False
        self.session = None

    async def _worker(self):
        while self._running:
            url, depth = await self.memory_queue.get()
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with self.session.get(url, timeout=timeout) as response:
                    if response.status == 200 and 'text/html' in response.headers.get('Content-Type', ''):
                        html_content = await response.text()
                        parser = MiniParser(url)
                        parser.feed(html_content)
                        await self.save_page(url, parser.title, parser.body)
                        for link in parser.get_links():
                            await self.add_to_queue(link, depth + 1)
                await self.mark_done(url)
            except Exception as e:
                logging.warning(f'Error crawling {url}: {e}')
                await self.mark_done(url)
            finally:
                self.memory_queue.task_done()

    async def _run_index_job(self, max_depth):
        while self._running:
            if self.memory_queue.qsize() >= 100:
                await asyncio.sleep(0.5)
                continue
            urls = await self.get_pending(limit=10)
            if not urls:
                await asyncio.sleep(0.5)
                continue
            for url, depth in urls:
                await self.mark_processing(url)
                await self.memory_queue.put((url, depth))
            await asyncio.sleep(0.1)

    async def start(self, seed_url, max_depth):
        self._running = True
        self.memory_queue = asyncio.Queue(maxsize=100)
        self.db_lock = asyncio.Lock()
        self.session = aiohttp.ClientSession(headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        if seed_url:
            await self.add_to_queue(seed_url, 0)
        tasks = [asyncio.create_task(self._worker()) for _ in range(30)]
        tasks.append(asyncio.create_task(self._run_index_job(max_depth)))
        await asyncio.gather(*tasks)
        await self.session.close()

    def start_in_background(self, seed_url, max_depth):
        threading.Thread(target=lambda: asyncio.run(self.start(seed_url, max_depth))).start()

    def resume_in_background(self, max_depth):
        threading.Thread(target=lambda: asyncio.run(self.start(None, max_depth))).start()

    async def save_page(self, url, title, body):
        with sqlite3.connect(self.db.db_path) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('INSERT OR IGNORE INTO pages (url, title, body) VALUES (?, ?, ?)', (url, title, body))
            conn.commit()

    async def add_to_queue(self, url, depth):
        await self.memory_queue.put((url, depth))

    async def mark_processing(self, url):
        with sqlite3.connect(self.db.db_path) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('UPDATE queue SET state = ? WHERE url = ?', ('processing', url))
            conn.commit()

    async def mark_done(self, url):
        with sqlite3.connect(self.db.db_path) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('UPDATE queue SET state = ? WHERE url = ?', ('done', url))
            conn.commit()

    async def get_pending(self, limit):
        with sqlite3.connect(self.db.db_path) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            cursor = conn.execute('SELECT url, depth FROM queue WHERE state = ? LIMIT ?', ('pending', limit))
            return cursor.fetchall()