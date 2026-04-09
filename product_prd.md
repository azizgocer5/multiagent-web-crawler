# Product Requirements Document (PRD)
**Project:** Mini Google Search Engine (Multi-Agent AI Implementation)

## 1. Objective
Build a concurrent web crawler (indexer) and a search engine that runs locally. The system must be capable of searching through indexed data while the crawler is actively fetching new pages. The project must be built using language-native features (e.g., Python's `asyncio` or `threading`, `sqlite3`) rather than heavy third-party frameworks.

## 2. Tech Stack Requirements
* **Language:** Python 3.10+ (Recommended for native async/concurrency features)
* **Database:** SQLite (Local DB). *Must be configured for concurrent reads and writes (e.g., WAL mode).*
* **Libraries:** Native libraries preferred (e.g., `asyncio`, `urllib` or `aiohttp`, `sqlite3`). No Celery, Redis, or Elasticsearch.
* **Environment:** Localhost only.

## 3. Core Components & Requirements

### 3.1. Indexer (Web Crawler)
**Method Signature:** `index(origin: str, k: int)`
*   **Behavior:** Starts from `origin` URL and crawls discovered links up to depth `k`.
*   **No Duplicate Crawling:** Must ensure the same URL is never crawled twice (needs a robust "visited" tracker).
*   **Back Pressure & Rate Limiting:** 
    *   Must not overwhelm the system or target websites.
    *   Implement a bounded queue (maximum queue depth).
    *   Implement a worker limit (e.g., max 10 concurrent requests).
*   **Resumability (Bonus):** Should be able to save the queue state to the database so if the system crashes, it can resume from where it left off.

### 3.2. Search Engine
**Method Signature:** `search(query: str) -> list[tuple]`
*   **Behavior:** Searches the database for the given query string.
*   **Output:** Returns a list of triples: `(relevant_url, origin_url, depth)`.
*   **Concurrency Constraint:** Must be able to execute and return results *while* the `index()` method is running in the background. (Non-blocking reads).
*   **Relevancy:** Simple keyword matching in the page title or body is sufficient for this scope.

### 3.3. User Interface (CLI)
A simple Command Line Interface (or basic web UI) to interact with the system.
*   **Features Needed:**
    1. Start a crawl (`index <url> <depth>`).
    2. Search for a keyword (`search <keyword>`).
    3. View System State (`status`): Show indexing progress, current queue depth, active workers, and back pressure status.

## 4. Multi-Agent Development Guidelines
This project is developed using a multi-agent workflow. Agents must respect boundaries:
*   **Agent 1 (DB Architect):** Only handles `database.py` (Schema, WAL mode config, basic CRUD).
*   **Agent 2 (Crawler Expert):** Only handles `indexer.py` (Async crawling, queue management, back pressure).
*   **Agent 3 (Search Specialist):** Only handles `search.py` (Query logic, data retrieval).
*   **Agent 4 (CLI/Integration Master):** Only handles `main.py` (CLI interface, threading/asyncio event loop management, connecting modules).
*   **Agent 5 (QA/Test Manager):** Acts as a high-authority manager responsible for comprehensive quality assurance. Develops and executes testing infrastructure (`test_*.py`), runs necessary tests to verify system behavior against PRD bounds, and has the authority to rewind the development process or rollback changes if the standards are not met. Furthermore, can directly communicate with any specific agent whose subsystem fails testing and mandate them to fix the isolated issues.

All code must be clean, modular, and thoroughly commented.