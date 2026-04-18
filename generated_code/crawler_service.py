import asyncio
from html.parser import HTMLParser
from typing import Set
from urllib.parse import urldefrag, urljoin, urlparse

import aiohttp


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


class MiniParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.title_parts: list[str] = []
        self.body_parts: list[str] = []
        self.links: set[str] = set()
        self._ignore_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style"}:
            self._ignore_depth += 1
            return

        if tag == "title":
            self._in_title = True

        if tag == "a":
            href = None
            for attr, value in attrs:
                if attr == "href":
                    href = value
                    break
            if href:
                full_url = urljoin(self.base_url, href)
                full_url, _ = urldefrag(full_url)
                parsed = urlparse(full_url)
                if parsed.scheme in {"http", "https"}:
                    self.links.add(full_url)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._ignore_depth > 0:
            self._ignore_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split()).strip()
        if not text or self._ignore_depth:
            return
        if self._in_title:
            self.title_parts.append(text)
        else:
            self.body_parts.append(text)

    def title(self) -> str:
        return " ".join(self.title_parts).strip()

    def body(self) -> str:
        return " ".join(self.body_parts).strip()


class CrawlerService:
    def __init__(self, db, worker_count: int = 10) -> None:
        self.db = db
        self.worker_count = worker_count
        self.db_lock = asyncio.Lock()
        self.memory_queue: asyncio.Queue[tuple[str, int]] = asyncio.Queue(maxsize=100)
        self._background_tasks: Set[asyncio.Task] = set()
        self._running = False

    async def _worker(self, session: aiohttp.ClientSession) -> None:
        while self._running:
            try:
                url, depth = await self.memory_queue.get()
            except asyncio.CancelledError:
                break

            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    content_type = resp.headers.get("Content-Type", "").lower()
                    if "text/html" in content_type:
                        html = await resp.text(errors="ignore")
                        parser = MiniParser(url)
                        parser.feed(html)
                        await self.db.save_page(
                            url,
                            parser.title(),
                            parser.body(),
                            url,
                            depth,
                            self.db_lock,
                        )
                        if depth > 0:
                            await self.db.add_to_queue(
                                list(parser.links),
                                depth - 1,
                                self.db_lock,
                            )
            except Exception:
                pass
            finally:
                await self.db.mark_done(url, self.db_lock)
                self.memory_queue.task_done()

    async def _run_index_job(self, max_depth: int) -> None:
        connector = aiohttp.TCPConnector(limit=self.worker_count)
        async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
            workers = [
                asyncio.create_task(self._worker(session))
                for _ in range(self.worker_count)
            ]
            try:
                while self._running:
                    if self.memory_queue.qsize() >= self.memory_queue.maxsize:
                        await asyncio.sleep(0.2)
                        continue

                    pending = await self.db.get_pending(10)
                    if not pending:
                        await asyncio.sleep(0.2)
                        continue

                    for url, depth in pending:
                        await self.db.mark_processing(url, self.db_lock)
                        await self.memory_queue.put((url, depth))
                    await asyncio.sleep(0)
            finally:
                for worker in workers:
                    worker.cancel()
                await asyncio.gather(*workers, return_exceptions=True)

    async def _engine(self, seed_url: str | None, max_depth: int) -> None:
        self._running = True
        if seed_url:
            await self.db.force_pending(seed_url, max_depth, self.db_lock)
        try:
            await self._run_index_job(max_depth)
        finally:
            self._running = False

    def start_in_background(self, seed_url: str, max_depth: int) -> None:
        task = asyncio.create_task(self._engine(seed_url, max_depth))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def resume_in_background(self, max_depth: int) -> None:
        task = asyncio.create_task(self._engine(None, max_depth))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def stop(self) -> None:
        self._running = False
        for task in list(self._background_tasks):
            task.cancel()
