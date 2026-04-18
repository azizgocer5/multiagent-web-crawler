# Multi-Agent Web Crawler System

## Overview
The "Mini Google" Multi-Agent Web Crawler is an autonomous, high-performance web crawling and indexing system. It is built using a hybrid concurrency model combining Python's `asyncio` for scalable non-blocking I/O and threading to ensure a responsive Command Line Interface (CLI) while crawling heavy networking tasks in the background.

## Architecture: Producer-Worker Pattern
The core of the system relies on the **Producer-Worker pattern** designed under a Multi-Agent philosophy where loosely coupled components work together:

1. **Producer Agent (`_run_index_job`)**: Continuously monitors the database for `pending` URLs. When capacity allows, it retrieves these URLs and places them into an in-memory active processing queue (`asyncio.Queue`).
2. **Worker Agents (`_worker`)**: A pool of multiple concurrent autonomous workers (default: 30) that eagerly pull URLs from the memory queue, making asynchronous HTTP requests (`aiohttp`), parsing HTML to extract the text and hyperlinks, saving the crawled pages to the database, and feeding discovered links back into the queue.

## System Components

### 1. The Command Line Interface (`main.py`)
Provides an interactive shell to manage the crawling system dynamically. 
- It operates on the main thread's event loop.
- Interprets user commands and triggers background crawling actions without blocking the prompt.

### 2. Crawler Service (`crawler_service.py`)
The engine of the crawler containing the agents. 
- **`MiniParser`**: A lightweight, custom subclass of `HTMLParser` that efficiently processes raw HTML. It specifically targets text content while cleanly filtering out `<script>`, `<style>`, and `<head>` tags. It also identifies embedded `<a>` tags to extract onward hyperlinks.
- **`CrawlerService`**: Orchestrates the workers. Contains the session context for networking and coordinates state updates (e.g., `pending` -> `processing` -> `done`).

### 3. Database Layer (`database.py`)
A robust SQLite backend using Write-Ahead Logging (WAL).
- **WAL Mode**: Executing `PRAGMA journal_mode=WAL` allows simultaneous processes/threads to safely read and write without encountering "Database Locked" errors, which is crucial for our highly concurrent multi-agent design.
- Handles the persistent state of the URL Queue as well as the indexing of Page content (URL, title, and body).
- Includes searching capabilities with rudimentary text scoring mechanisms.

## Concurrency & Threading Model
The architecture employs a thoughtful separation of concerns using Thread Boundaries:

- **Main Thread (CLI)**: Responsible purely for listening to standard input and fetching immediate status or search query results requested by the user.
- **Background Thread**: When `crawl` or `resume` is triggered, the worker system is spawned inside `.start_in_background()`. A brand new `asyncio` event loop is initialized in this isolated `threading.Thread`. 
- **Asyncio Event Loop**: Within the crawler's background thread, 30 asynchronous workers and 1 producer operate continuously overlapping I/O wait times efficiently without GIL bottlenecks.

## Data Flow
1. **Seed**: The user inputs a seed URL via the CLI.
2. **Registration**: The initial URL is recorded in the `queue` table as `pending`.
3. **Distribution**: The Producer fetches the `pending` URL, marks it as `processing`, and pushes it to the asyncio memory queue.
4. **Execution**: A free Worker pops the URL from the queue, fetches the web page contents. 
5. **Extraction**: The Worker extracts visible text and new outgoing links.
6. **Persistence**: Extracted text content is saved to the `pages` SQLite table.
7. **Expansion**: New valid outgoing links are added back to the `queue` table as `pending`. 
8. **Completion**: The initial URL state is updated to `done` in the database.

## Usage Guide (CLI Commands)

Start the program using: `python main.py`

Once inside the interactive prompt `> `, the following commands can be executed:
- `crawl <url> <depth>`: Initiates a completely new crawl job starting from the given URL up to the specified max depth. *Example: `crawl https://wikipedia.org 2`*
- `search <query>`: Performs a text-based search locally across all currently crawled pages. Shows titles, origin URLs, and relevance scores. *Example: `search machine learning`*
- `status`: Provides a real-time aggregate count of the crawler's queue state (how many are Pending, Processing, and Done).
- `resume`: Recovers an aborted crawling session. Automatically flips previously `processing` tasks back to `pending` and spins up the background workers to continue where they left off.
- `exit`: Terminates the CLI application gracefully.
