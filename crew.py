"""
crew.py - Agent and task factories for the crawler builder.

The manager imports this module, selects a working LLM through LiteLLM,
and uses the task factory functions below to generate tightly-scoped
artifacts under generated_code/.
"""

from __future__ import annotations

import os
from datetime import datetime

import litellm
from crewai import Agent, LLM, Task
from dotenv import load_dotenv

load_dotenv()


MODEL_CHAIN = [
    {"model": "gemini/gemini-3.1-flash-lite-preview", "api_key": os.getenv("API_KEY")},
    {"model": "gemini/gemini-2.5-pro", "api_key": os.getenv("API_KEY")},
    {"model": "gemini/gemini-2.5-pro-preview-05-06", "api_key": os.getenv("API_KEY")},
    {"model": "gemini/gemini-2.5-flash-preview-04-17", "api_key": os.getenv("API_KEY")},
    {"model": "gemini/gemini-2.0-flash", "api_key": os.getenv("API_KEY")},
    {"model": "gemini/gemini-2.0-flash-lite", "api_key": os.getenv("API_KEY")},
    {"model": "groq/llama-3.3-70b-versatile", "api_key": os.getenv("GROQ_KEY")},
    {"model": "gemini/gemini-1.5-flash", "api_key": os.getenv("API_KEY")},
    {"model": "groq/meta-llama/llama-4-scout-17b-16e-instruct", "api_key": os.getenv("GROQ_KEY")},
    {"model": "groq/llama-3.1-8b-instant", "api_key": os.getenv("GROQ_KEY")},
]

ACTIVE_MODEL_NAME: str | None = None
ACTIVE_API_KEY: str | None = None


def _select_llm() -> LLM:
    global ACTIVE_MODEL_NAME, ACTIVE_API_KEY

    for entry in MODEL_CHAIN:
        model_name = entry["model"]
        api_key = entry["api_key"]

        if not api_key:
            print(f"  [SKIP] {model_name} -- API key missing")
            continue

        try:
            print(f"  [TRY]  {model_name} ...", end=" ", flush=True)
            response = litellm.completion(
                model=model_name,
                api_key=api_key,
                messages=[{"role": "user", "content": "Reply with OK only."}],
                max_tokens=8,
                temperature=0.0,
            )
            result = response.choices[0].message.content.strip()
            print(f"OK ({result})")
            ACTIVE_MODEL_NAME = model_name
            ACTIVE_API_KEY = api_key
            return LLM(
                model=model_name,
                api_key=api_key,
                temperature=0.2,
                max_tokens=8000,
            )
        except Exception as exc:
            print(f"FAIL: {str(exc)[:100]}")

    raise RuntimeError("No configured LLM responded successfully.")


print("=" * 50)
print("LLM Model Selection")
print("=" * 50)
active_llm = _select_llm()


ARCHITECTURE_BRIEF = """
Project target: a local mini search engine with an asyncio + aiohttp crawler and an SQLite index.

Files:
- main.py: interactive CLI
- crawler_service.py: async crawler engine
- database.py: async-friendly SQLite wrapper
- requirements.txt: minimal runtime dependencies

Hard constraints:
- HTTP client must be aiohttp only.
- Database must use sqlite3 only and enable WAL mode.
- There must be a single event loop. Do not create a second loop in another thread.
- threading.Thread is forbidden for running the crawler.
- Background crawl work must be started with asyncio.create_task(...) from the main loop.
- All write operations must be coordinated with one shared asyncio.Lock.
- The crawler must use a bounded in-memory queue and a bounded worker count.
- The same URL must not be crawled twice.
- Search must continue to work while crawling is active.
- CLI output must stay ASCII-safe. No emoji.
"""

OUTPUT_CONTRACT = """
Output contract:
- Return only file blocks, no intro and no explanation.
- Each file block must follow this exact format:
FILE: <filename>
```python
<complete file content>
```
- For markdown or text files, use ```text instead of ```python.
- Return full replacement files, never diffs.
"""


def agent_step_callback(step_output, agent_name: str) -> None:
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"agent_{agent_name.lower().replace(' ', '_')}.log")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(log_file, "a", encoding="utf-8") as handle:
        handle.write(f"\n--- STEP AT {timestamp} ---\n")
        handle.write(str(step_output))
        handle.write("\n" + "=" * 50 + "\n")


architect = Agent(
    role="System Architect",
    goal="Design a correct single-loop architecture and clean file interfaces.",
    backstory=(
        "You design resilient async Python systems and prevent event loop conflicts, "
        "queue blowups, and integration mismatches before code is written."
    ),
    llm=active_llm,
    verbose=False,
    step_callback=lambda step: agent_step_callback(step, "System Architect"),
)

db_engineer = Agent(
    role="Database Engineer",
    goal="Write a robust SQLite layer with WAL mode and lock-safe write operations.",
    backstory=(
        "You specialize in SQLite concurrency, WAL mode, and practical search queries. "
        "You care deeply about duplicate avoidance, resumability, and predictable APIs."
    ),
    llm=active_llm,
    verbose=False,
    step_callback=lambda step: agent_step_callback(step, "Database Engineer"),
)

crawler_dev = Agent(
    role="Crawler Engineer",
    goal="Write an async crawler that is bounded, resumable, and easy to test.",
    backstory=(
        "You build asyncio services that stay responsive under load, recover from fetch errors, "
        "and never rely on forbidden thread-based loop tricks."
    ),
    llm=active_llm,
    verbose=False,
    step_callback=lambda step: agent_step_callback(step, "Crawler Engineer"),
)

cli_dev = Agent(
    role="CLI Engineer",
    goal="Integrate the crawler into a reliable CLI that keeps the main loop responsive.",
    backstory=(
        "You build practical CLIs for async systems and make integration details explicit. "
        "You never assume methods that other modules do not actually provide."
    ),
    llm=active_llm,
    verbose=False,
    step_callback=lambda step: agent_step_callback(step, "CLI Engineer"),
)

qa = Agent(
    role="QA Engineer",
    goal="Audit the generated system strictly, fix defects, and produce an acceptance report.",
    backstory=(
        "You review for behavioral bugs first: deadlocks, queue leaks, duplicate crawling, "
        "bad shutdown paths, missing dependencies, and broken CLI contracts."
    ),
    llm=active_llm,
    verbose=False,
    step_callback=lambda step: agent_step_callback(step, "QA Engineer"),
)


def make_architect_task(user_request: str, context: list) -> Task:
    return Task(
        description=(
            f"{ARCHITECTURE_BRIEF}\n\n"
            f"{OUTPUT_CONTRACT}\n\n"
            f"Manager instruction:\n{user_request}\n\n"
            "Produce exactly one file block:\n"
            "FILE: architecture.md\n"
            "It must define:\n"
            "- Public APIs for database.py, crawler_service.py, and main.py\n"
            "- Single-event-loop lifecycle\n"
            "- Crawl state transitions: pending -> processing -> done\n"
            "- Duplicate URL prevention and queue back-pressure rules\n"
            "- How search works while crawling is active\n"
        ),
        expected_output="A single architecture.md file block.",
        agent=architect,
        context=context,
    )


def make_db_task(user_request: str, context: list) -> Task:
    return Task(
        description=(
            f"{ARCHITECTURE_BRIEF}\n\n"
            f"{OUTPUT_CONTRACT}\n\n"
            f"Manager instruction:\n{user_request}\n\n"
            "Produce exactly one file block for database.py.\n"
            "Required API:\n"
            "- class Database\n"
            "- __init__(db_path: str) -> None\n"
            "- async def force_pending(url: str, depth: int, lock: asyncio.Lock) -> None\n"
            "- async def add_to_queue(urls: list[str], depth: int, lock: asyncio.Lock) -> int\n"
            "- async def get_pending(limit: int) -> list[tuple[str, int]]\n"
            "- async def mark_processing(url: str, lock: asyncio.Lock) -> None\n"
            "- async def mark_done(url: str, lock: asyncio.Lock) -> None\n"
            "- async def save_page(url: str, title: str, body: str, origin_url: str, depth: int, lock: asyncio.Lock) -> None\n"
            "- async def resume_processing(lock: asyncio.Lock) -> None\n"
            "- async def get_status() -> dict[str, int]\n"
            "- async def search(query: str) -> list[dict]\n"
            "- async def get_setting(key: str) -> str | None\n"
            "- async def set_setting(key: str, value: str, lock: asyncio.Lock) -> None\n"
            "- async def close() -> None\n"
            "Rules:\n"
            "- Acceptance harness will call these methods with exactly these argument counts. Do not rename them and do not remove the lock parameter from write methods.\n"
            "- Enable WAL mode and use sqlite3.Row.\n"
            "- queue(url PRIMARY KEY, depth, state), pages(url PRIMARY KEY, title, body, origin_url, depth), settings(key PRIMARY KEY, value).\n"
            "- Use executemany for batch queue inserts.\n"
            "- Writes must be done inside the provided lock.\n"
            "- search() should score title matches higher than body matches and handle Turkish-friendly normalization.\n"
        ),
        expected_output="A single database.py file block.",
        agent=db_engineer,
        context=context,
    )


def make_crawler_task(user_request: str, context: list) -> Task:
    return Task(
        description=(
            f"{ARCHITECTURE_BRIEF}\n\n"
            f"{OUTPUT_CONTRACT}\n\n"
            f"Manager instruction:\n{user_request}\n\n"
            "Produce exactly one file block for crawler_service.py.\n"
            "Required API:\n"
            "- class MiniParser(HTMLParser)\n"
            "- class CrawlerService\n"
            "- def __init__(self, db, worker_count: int = 10)\n"
            "- async def _worker(self, session: aiohttp.ClientSession) -> None\n"
            "- async def _run_index_job(self, max_depth: int) -> None\n"
            "- async def _engine(self, seed_url: str | None, max_depth: int) -> None\n"
            "- def start_in_background(self, seed_url: str, max_depth: int) -> None\n"
            "- def resume_in_background(self, max_depth: int) -> None\n"
            "- def stop(self) -> None\n"
            "Rules:\n"
            "- Acceptance harness will instantiate CrawlerService(db), read service.db_lock, and call start_in_background(seed_url, max_depth), resume_in_background(max_depth), and stop(). Keep those names and keep db_lock as a public attribute.\n"
            "- Keep the helper name _run_index_job exactly as written. Do not rename it to _indexer or another name.\n"
            "- memory_queue must be asyncio.Queue(maxsize=100).\n"
            "- db_lock must be a shared asyncio.Lock.\n"
            "- Database write methods already receive the shared lock. Do NOT wrap calls to db.save_page/add_to_queue/mark_processing/mark_done inside another async with self.db_lock block, or you will deadlock.\n"
            "- Use aiohttp.ClientTimeout(total=10).\n"
            "- Process HTML only when Content-Type contains text/html.\n"
            "- MiniParser must ignore script/style/head text, collect title/body text, and gather links.\n"
            "- Normalize discovered links with urljoin and keep http/https only.\n"
            "- Do not enqueue URLs deeper than max_depth.\n"
            "- On every fetch error, the URL must still be marked done so the system can make progress.\n"
            "- start_in_background/resume_in_background must use asyncio.create_task on the current loop only.\n"
            "- _background_tasks must discard completed tasks automatically.\n"
            "- Forbidden: threading.Thread, asyncio.run in background helpers, requests, bs4, time.sleep.\n"
        ),
        expected_output="A single crawler_service.py file block.",
        agent=crawler_dev,
        context=context,
    )


def make_cli_task(user_request: str, context: list) -> Task:
    return Task(
        description=(
            f"{ARCHITECTURE_BRIEF}\n\n"
            f"{OUTPUT_CONTRACT}\n\n"
            f"Manager instruction:\n{user_request}\n\n"
            "Produce exactly two file blocks: main.py and requirements.txt.\n"
            "main.py requirements:\n"
            "- Create Database('crawler.db') and CrawlerService(db).\n"
            "- Run everything on one event loop.\n"
            "- Read commands with await asyncio.to_thread(input, '> ').\n"
            "- crawl <url> <depth>: persist max_depth, seed the queue, then call start_in_background.\n"
            "- search <query>: print depth, url, origin_url, and title in an ASCII-safe format.\n"
            "- status: print pending, processing, done, and active background task count.\n"
            "- resume: restore processing rows to pending, read max_depth, and call resume_in_background.\n"
            "- exit: stop the crawler and close the database cleanly.\n"
            "- Use Rich carefully but keep output ASCII-safe.\n"
            "requirements.txt requirements:\n"
            "- Include only the minimum runtime dependencies needed by the generated files.\n"
            "- If Rich is imported, rich must be listed.\n"
        ),
        expected_output="main.py and requirements.txt file blocks.",
        agent=cli_dev,
        context=context,
    )


def make_qa_task(user_request: str, context: list) -> Task:
    return Task(
        description=(
            f"{ARCHITECTURE_BRIEF}\n\n"
            f"{OUTPUT_CONTRACT}\n\n"
            f"Manager instruction:\n{user_request}\n\n"
            "Audit all generated files and produce exactly one qa_report.md file block first.\n"
            "The report must include:\n"
            "- Pass/fail checklist for database.py, crawler_service.py, main.py, requirements.txt\n"
            "- Concrete bug list with file names and reasons\n"
            "- Acceptance test expectations for syntax, crawl progress, duplicate prevention, and search during crawl\n"
            "If any generated file is wrong, append corrected full replacement file blocks after qa_report.md.\n"
            "Reject these defects explicitly if present:\n"
            "- Second event loop or background thread for crawling\n"
            "- Missing WAL mode\n"
            "- Unbounded queue\n"
            "- Duplicate URL insertion\n"
            "- Missing dependency declarations\n"
            "- A crawl path that can leave rows stuck in processing forever\n"
            "- Holding self.db_lock in crawler_service.py while calling database methods that also acquire the same lock\n"
            "- Search output that omits origin_url/depth/title data promised by the CLI contract\n"
        ),
        expected_output="qa_report.md and optional corrected file blocks.",
        agent=qa,
        context=context,
    )
