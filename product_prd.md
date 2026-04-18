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

### 3.4. AI Orchestrator Layer (Development Environment)
The project includes a self-modifying, interactive AI Builder environment.
*   **`manager.py` (The Interactive Orchestrator):** A command-line tool that acts as the "Head Engineer". It accepts natural language queries from the developer, analyzes the intent using an LLM, and decides exactly which files or modules need updates. It then formulates customized task directives (prompts) tailored specifically to address the requested issue.
*   **`crew.py` (The Multi-Agent Crew):** Implements a CrewAI structure utilizing a dynamic model fallback chain (via `litellm`). It spins up designated AI agents (Architect, DB Engineer, Crawler Dev, CLI Engineer, QA) who act on the tailored instructions injected by the Manager, executing parallelly to rewrite and test the core Python scripts automatically.

## 4. Multi-Agent Development Guidelines
This project is developed and orchestrated using a CrewAI-based multi-agent workflow augmented by an active Reasoning Manager. Agents must respect their clear boundaries and generated artifacts:
*   **The Head Manager (`manager.py`):** Not a standard agent, but an LLM-powered orchestrator taking user's direct commands, doing semantic analysis, and triggering the correct subset of the agents below with specialized instructions.
*   **Agent 1 (System Architect):** Determines the overall system design, thread boundaries, and concurrency model. Output: `architecture.md`.
*   **Agent 2 (Database Engineer):** Handles `database.py` (Schema, WAL mode config, thread-safe asynchronous operations, and search queries).
*   **Agent 3 (Crawler/Async System Developer):** Handles `crawler_service.py` (Async IO, `aiohttp` web crawling, queue management, back pressure).
*   **Agent 4 (CLI & Integration Engineer):** Handles `main.py` (Interactive CLI, orchestrating the event loops and background worker threads) and `requirements.txt`.
*   **Agent 5 (QA Engineer):** Acts as a compulsory code reviewer to analyze the generated pieces. Produces a detailed quality assurance and bug evaluation report (`qa_report.md`).

All code must be clean, modular, and thoroughly commented.