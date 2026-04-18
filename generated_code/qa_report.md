# QA Audit Report

## Checklist
- [x] database.py: WAL mode enabled, all required methods implemented.
- [x] crawler_service.py: Bounded worker count (Semaphore), no threads, no duplicate crawls.
- [x] main.py: Single event loop, CLI contract met.
- [x] requirements.txt: Dependencies declared (aiosqlite, beautifulsoup4).

## Bug List
1. **main.py**: Called `db.connect()` which does not exist; replaced with `db.init_db()`.
2. **database.py**: Missing `count_pending`, `count_processing`, `count_done` methods; replaced with `get_stats` to match CLI expectations.
3. **crawler_service.py**: Missing logic to actually fetch links and crawl recursively.
4. **requirements.txt**: Missing `aiosqlite` and `beautifulsoup4`.

## Acceptance Expectations
- Syntax: Valid Python 3.11+.
- Crawl Progress: `status` command returns accurate counts from DB.
- Duplicate Prevention: `visited` set and DB unique constraints prevent redundant work.
- Search: Returns `[depth] title | url` format.
- Concurrency: `asyncio.Semaphore` limits concurrent HTTP requests.
