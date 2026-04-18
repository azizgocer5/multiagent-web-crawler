# Architecture Design: Mini Search Engine

## 1. Single-Event-Loop Lifecycle
- The application starts in `main.py` using `asyncio.run()`.
- All components (`Database`, `CrawlerService`) are initialized within the scope of the main loop.
- No background threads are spawned. All concurrency is managed via `asyncio.Task` and `asyncio.Queue`.
- Graceful shutdown is handled by cancelling pending tasks and awaiting the `Database` connection closure.

## 2. Public APIs

### database.py
- `Database(db_path: str)`: Initializes the object.
- `async def setup()`: Establishes connection, enables WAL mode, and creates schema.
- `async def insert_page(url: str, content: str)`: Writes to SQLite using a shared `asyncio.Lock`.
- `async def search(query: str) -> list[dict]`: Performs a `LIKE` query on the content column.
- `async def is_crawled(url: str) -> bool`: Checks if the URL exists in the index.
- `async def get_stats() -> dict`: Returns count of indexed pages.
- `async def close()`: Closes the connection.

### crawler_service.py
- `CrawlerService(db: Database, max_workers: int)`: Initializes the service.
- `async def crawl(start_url: str)`: Entry point to start the crawl process.
- `async def _worker()`: Internal loop consuming from `asyncio.Queue`.
- `async def _fetch(url: str)`: Uses `aiohttp.ClientSession` to retrieve content.

### main.py
- `async def main()`: Orchestrates the CLI loop and service initialization.
- `async def run_cli()`: Handles user input (search/crawl commands) without blocking the crawler.

## 3. Crawl State Transitions
1. Pending: URL added to `asyncio.Queue`.
2. Processing: Worker pops URL, checks `Database.is_crawled()`. If false, fetches content.
3. Done: Content written to `Database` via `insert_page()`, URL marked as indexed.

## 4. Duplicate Prevention & Back-pressure
- Duplicate Prevention: Before adding to the queue, the crawler checks `Database.is_crawled()`. A `set` of "in-flight" URLs is maintained in memory to prevent duplicate processing of URLs currently being fetched.
- Back-pressure: The `asyncio.Queue` is initialized with a `maxsize`. `put()` operations are awaited, ensuring the producer slows down if workers cannot keep up.

## 5. Concurrent Search and Crawl
- Search operations are non-blocking read-only queries.
- Since `Database` uses WAL (Write-Ahead Logging) mode, SQLite allows multiple readers to operate simultaneously while a single writer (protected by `asyncio.Lock`) performs inserts.
- The `main.py` CLI loop uses `asyncio.create_task` to ensure the user can trigger a search while the `CrawlerService` background tasks are active.
