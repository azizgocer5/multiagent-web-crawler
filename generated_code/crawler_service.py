import asyncio
import logging
import threading
import aiohttp
from html.parser import HTMLParser
from urllib.parse import urljoin
from database import Database

# Logging yapılandırması
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("crawler.log"), logging.StreamHandler()]
)

class MiniParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.links = set()
        self.text = []
        self.title = ""
        self._skip = False
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'head'):
            self._skip = True
        if tag == 'title':
            self._in_title = True
        if tag == 'a':
            for attr, value in attrs:
                if attr == 'href':
                    full_url = urljoin(self.base_url, value)
                    if full_url.startswith(('http://', 'https://')):
                        self.links.add(full_url)

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'head'):
            self._skip = False
        if tag == 'title':
            self._in_title = False

    def handle_data(self, data):
        if not self._skip:
            self.text.append(data.strip())
            if self._in_title:
                self.title += data.strip()

    def get_links(self):
        return list(self.links)

class CrawlerService:
    def __init__(self, db: Database, worker_count=30):
        self.db = db
        self.worker_count = worker_count
        self.memory_queue = asyncio.Queue(maxsize=100)
        self.db_lock = asyncio.Lock()
        self._running = False

    async def _worker(self, session, max_depth):
        while self._running:
            try:
                url, depth = await self.memory_queue.get()
                
                if depth > max_depth:
                    self.db.mark_done(url)
                    self.memory_queue.task_done()
                    continue

                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if 'text/html' not in response.headers.get('Content-Type', ''):
                        self.db.mark_done(url)
                        self.memory_queue.task_done()
                        continue

                    html = await response.text()
                    parser = MiniParser(url)
                    parser.feed(html)
                    
                    async with self.db_lock:
                        self.db.save_page(url, parser.title, " ".join(parser.text))
                        if depth < max_depth:
                            self.db.add_to_queue(parser.get_links(), depth + 1)
                        self.db.mark_done(url)
                
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logging.warning(f"Network error for {url}: {e}")
                self.db.mark_done(url)
            except Exception as e:
                logging.error(f"Unexpected error processing {url}: {e}")
                self.db.mark_done(url)
            finally:
                self.memory_queue.task_done()

    async def _run_index_job(self, max_depth):
        while self._running:
            if self.memory_queue.qsize() >= 100:
                await asyncio.sleep(0.5)
                continue

            pending = self.db.get_pending(limit=10)
            if not pending:
                await asyncio.sleep(0.5)
                continue

            for url, depth in pending:
                if depth <= max_depth:
                    self.db.mark_processing(url)
                    await self.memory_queue.put((url, depth))
            
            await asyncio.sleep(0.1)

    async def start(self, seed_url, max_depth):
        self._running = True
        if seed_url:
            self.db.add_to_queue([seed_url], 0)
        
        try:
            async with aiohttp.ClientSession() as session:
                workers = [asyncio.create_task(self._worker(session, max_depth)) for _ in range(self.worker_count)]
                indexer = asyncio.create_task(self._run_index_job(max_depth))
                await asyncio.gather(*workers, indexer)
        except Exception as e:
            logging.critical(f"Crawler service failed to start/run: {e}")
        finally:
            self._running = False

    def start_in_background(self, seed_url, max_depth):
        threading.Thread(target=lambda: asyncio.run(self.start(seed_url, max_depth)), daemon=True).start()

    def resume_in_background(self, max_depth):
        self._running = True
        threading.Thread(target=lambda: asyncio.run(self.start(None, max_depth)), daemon=True).start()