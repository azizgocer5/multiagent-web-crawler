https://github.com/azizgocer5/multiagent-web-crawler
# LangGraph-Based Mini Search Engine

## Project Description

This project aims to enhance the robustness, scalability, and fault tolerance of an existing web crawler and search engine application by migrating it to a LangGraph multi-agent framework. The system is designed to ensure uninterrupted crawling operations and concurrent search capabilities. It combines the power of async Python, SQLite optimization, and LangGraph to deliver an efficient solution.

## Features

-   **Web Crawling**: Crawls web pages up to a specified depth, starting from a given URL.
-   **HTML Parsing**: Extracts titles, body text, and new links from crawled HTML content.
-   **Database Storage**: Persistently stores crawled pages (URL, title, body, origin URL, depth) and the crawling queue in an SQLite database.
-   **Search Functionality**: Performs keyword-based searches on stored pages and ranks results by relevance.
-   **State Management**: Manages the state of the crawling process through LangGraph's state-based architecture, offering the ability to resume interrupted operations.
-   **Backpressure Mechanism**: Prevents system overload by ensuring the crawling queue does not exceed a certain size.
-   **CLI Interface**: Provides an interactive command-line interface with core commands like `crawl`, `search`, `status`, and `resume`.

## Technical Architecture

The project is built upon the LangGraph framework, utilizing a state-based multi-agent system. The core components are nodes that perform specific tasks and a shared state schema that is passed between these nodes. An SQLite database is used for persistent storage of both crawled data and the LangGraph state.

**Main Components:**

-   **`database.py`**: Manages SQLite database operations, queue management, page storage, and search functionality. It ensures concurrent access and performance optimization using `asyncio.Lock` and WAL mode.
-   **`langgraph_crawler/state.py`**: Contains the `CrawlerState` TypedDict, which defines the shared state across the LangGraph graph.
-   **`langgraph_crawler/nodes/`**: Houses the core business logic nodes of the LangGraph graph:
    -   `orchestrator.py`: Manages the crawling queue, fetches pending URLs, and controls the backpressure mechanism.
    -   `crawler.py`: Fetches URLs via HTTP requests, parses HTML, and extracts new links.
    -   `indexer.py`: Saves crawled pages to the database and adds newly found links to the crawling queue.
    -   `search.py`: Executes search queries against the database.
    -   `monitor.py`: Monitors the overall status of the crawling process (queue depth, number of indexed pages, etc.).
-   **`langgraph_crawler/graph.py`**: Defines the LangGraph `StateGraph`, setting up nodes and the transition logic (edges) between them.
-   **`main.py`**: Provides the user interface (CLI) and is responsible for initiating and managing the LangGraph graph.

## Setup

To run the application locally, follow these steps:

1.  **Clone the Repository:**
    ```bash
    git clone <repo_url>
    cd web-crawler
    ```

2.  **Create and Activate a Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    source venv/bin/activate # Linux/macOS
    # or
    .\venv\Scripts\activate # Windows
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    `requirements.txt` content:
    ```
    langgraph>=0.2.0
    langgraph-checkpoint-sqlite>=0.0.1
    langchain-core>=0.2.0
    aiohttp>=3.9.0
    ```

## Usage

The application is run via the command-line interface (CLI).

```bash
python main.py
```

Available commands: `crawl <url> <depth>`, `search <query>`, `status`, `resume`, `exit`.

-   **`crawl <url> <depth>`**: Initiates the crawling process from the specified URL up to a certain depth.
    Example: `crawl https://example.com 2`
-   **`search <query>`**: Searches the database with the specified query and lists the results.
    Example: `search "LangGraph"`
-   **`status`**: Displays the current status of the crawling queue and the number of indexed pages.
-   **`resume`**: Resumes a previously interrupted crawling process from where it left off.
-   **`exit`**: Exits the application.

## Current Status and Known Issues

In the current development phase, the LangGraph integration is not yet complete. According to the test report, there are significant deficiencies:

-   **`langgraph_crawler/graph.py` file is missing**: The main definition of the LangGraph graph should be in this file.
-   **`langgraph_crawler/nodes/monitor.py` file is missing/erroneous**: The file is incomplete and contains a syntax error.
-   **`main.py` lacks LangGraph integration**: The CLI commands still use the old `CrawlerService` class and do not trigger the LangGraph flow. Therefore, `crawl`, `status`, `resume` commands do not demonstrate LangGraph-based functionality.
-   **`turkish_lower` function is missing**: A function expected in tests but not defined in the current code. It should be added if Turkish character conversion is required.

Until these deficiencies are addressed, the core LangGraph-based functionality of the project cannot be fully tested or utilized. Although most unit tests passed, integration and smoke tests failed.
