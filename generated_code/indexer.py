import asyncio
import aiohttp
import logging
from urllib.parse import urljoin
from html.parser import HTMLParser

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()
        self.title = ""
        self.body = []
        self._in_title = False
        self._ignore_tags = {'script', 'style', 'noscript', 'meta', 'head'}
        self._current_tag = None

    def handle_starttag(self, tag, attrs):
        self._current_tag = tag
        if tag == 'a':
            for attr, value in attrs:
                if attr == 'href': self.links.add(value)
        elif tag == 'title': 
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == 'title': self._in_title = False
        self._current_tag = None

    def handle_data(self, data):
        if self._current_tag in self._ignore_tags:
            return
        if self._in_title: 
            self.title += data
        else: 
            self.body.append(data.strip())

class Crawler:
    def __init__(self, db, max_depth=2, max_workers=30):
        self.db = db
        self.max_depth = max_depth
        self.max_workers = max_workers
        self.queue = asyncio.Queue(maxsize=100)
        self.session = None

    async def _worker(self):
        """Worker process to pull from queue and crawl."""
        while True:
            url, depth = await self.queue.get()
            try:
                await self.process_page(url, depth)
            except Exception as e:
                logging.error(f"Error processing {url}: {e}")
            finally:
                self.queue.task_done()

    async def process_page(self, url, depth):
        """Downloads, parses, and persists page data."""
        # 1. Depth Verification: Only process if within allowed limit
        if depth > self.max_depth:
            return

        async with self.session.get(url, timeout=10) as response:
            if response.status != 200:
                return
            
            html = await response.text()
            parser = LinkParser()
            parser.feed(html)
            
            # 2. Logic: Only schedule discovery if we haven't hit the max depth
            discovered_links = []
            if depth < self.max_depth:
                for link in parser.links:
                    full_url = urljoin(url, link)
                    # Add to DB immediately to prevent concurrent duplicate processing
                    if not await self.db.is_visited(full_url):
                        await self.db.mark_as_pending(full_url, depth + 1)
                        discovered_links.append(full_url)
            
            page_data = {
                "url": url,
                "title": parser.title.strip(),
                "body": " ".join(filter(None, parser.body)),
                "depth": depth,
            }
            
            # Persist data
            await self.db.save_page_and_links(page_data, discovered_links)
            # Mark the current URL as fully crawled in DB
            await self.db.mark_as_crawled(url)

    async def run(self, start_url):
        """Main crawler loop with DB state synchronization."""
        async with aiohttp.ClientSession() as self.session:
            # Seed the database
            if not await self.db.is_visited(start_url):
                await self.db.mark_as_pending(start_url, 0)
            
            workers = [asyncio.create_task(self._worker()) for _ in range(self.max_workers)]
            
            while True:
                # Producer logic: fetch batch from DB
                pending = await self.db.get_pending_urls(limit=50)
                
                if not pending:
                    if self.queue.empty():
                        break
                    await asyncio.sleep(1)
                    continue
                
                for url, depth in pending:
                    # Non-blocking put, only if queue isn't full
                    try:
                        await self.queue.put((url, depth))
                    except asyncio.QueueFull:
                        break
                
                await self.queue.join()
            
            # Cleanup
            for w in workers: w.cancel()