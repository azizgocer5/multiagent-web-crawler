"""
manager.py - Interactive orchestrator for the crawler builder.

The manager analyzes a developer request, selects the relevant agents,
runs the CrewAI workflow, saves generated artifacts, and then performs
real acceptance checks against the generated crawler.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

from crewai import Crew, Process

from crew import (
    ACTIVE_API_KEY,
    ACTIVE_MODEL_NAME,
    architect,
    cli_dev,
    crawler_dev,
    db_engineer,
    make_architect_task,
    make_cli_task,
    make_crawler_task,
    make_db_task,
    make_qa_task,
    qa,
)


BASE_DIR = Path(__file__).resolve().parent
GENERATED_DIR = BASE_DIR / "generated_code"
PIPELINE_ORDER = ["architect", "db", "crawler", "cli", "qa"]

AGENT_MAP = {
    "architect": architect,
    "db": db_engineer,
    "crawler": crawler_dev,
    "cli": cli_dev,
    "qa": qa,
}

TASK_BUILDER_MAP = {
    "architect": make_architect_task,
    "db": make_db_task,
    "crawler": make_crawler_task,
    "cli": make_cli_task,
    "qa": make_qa_task,
}

ROLE_DEFAULT_FILES = {
    "System Architect": "architecture.md",
    "Database Engineer": "database.py",
    "Crawler Engineer": "crawler_service.py",
    "CLI Engineer": "main.py",
    "QA Engineer": "qa_report.md",
}

SMOKE_TEST_SCRIPT = textwrap.dedent(
    r"""
    import asyncio
    import functools
    import shutil
    import sys
    import threading
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    from pathlib import Path

    repo = Path.cwd()
    generated_dir = repo / "generated_code"
    sys.path.insert(0, str(generated_dir))

    from database import Database
    from crawler_service import CrawlerService


    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass


    def start_server(root: Path):
        handler = functools.partial(QuietHandler, directory=str(root))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread


    async def exercise_crawler():
        site_dir = generated_dir / "_smoke_site"
        if site_dir.exists():
            shutil.rmtree(site_dir, ignore_errors=True)
        site_dir.mkdir(parents=True, exist_ok=True)

        (site_dir / "index.html").write_text(
            "<html><head><title>Alpha Root</title></head>"
            "<body><a href='/page2.html'>page2</a><a href='/page2.html'>dup</a>"
            "<p>alpha unique root body</p></body></html>",
            encoding="utf-8",
        )
        (site_dir / "page2.html").write_text(
            "<html><head><title>Beta Leaf</title></head>"
            "<body><p>beta unique child body</p></body></html>",
            encoding="utf-8",
        )

        db_path = generated_dir / "_smoke.db"
        if db_path.exists():
            db_path.unlink()

        server, thread = start_server(site_dir)
        db = Database(str(db_path))
        service = CrawlerService(db, worker_count=4)
        base_url = f"http://127.0.0.1:{server.server_port}"

        try:
            await db.set_setting("max_depth", "1", service.db_lock)
            await db.force_pending(f"{base_url}/index.html", 0, service.db_lock)
            service.start_in_background(f"{base_url}/index.html", 1)

            deadline = asyncio.get_running_loop().time() + 12
            alpha_results = []
            beta_results = []
            status = {}
            while asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.25)
                status = await db.get_status()
                alpha_results = await db.search("alpha")
                beta_results = await db.search("beta")
                if status.get("done", 0) >= 2 and alpha_results and beta_results:
                    break

            service.stop()
            await asyncio.sleep(0.5)
            remaining = await db.get_pending(20)
            combined_results = await db.search("unique")
            await db.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            if site_dir.exists():
                shutil.rmtree(site_dir, ignore_errors=True)
            if db_path.exists():
                db_path.unlink()

        assert alpha_results, f"alpha search returned no results; status={status}"
        assert beta_results, f"beta search returned no results; status={status}"
        assert status.get("done", 0) >= 2, f"expected >=2 done rows, got {status}"
        assert not remaining, f"pending queue not drained: {remaining}"
        assert len(combined_results) >= 2, f"expected >=2 indexed pages, got {len(combined_results)}"
        print("SMOKE_OK", status, len(combined_results))


    asyncio.run(exercise_crawler())
    """
)

API_CONTRACT_SCRIPT = textwrap.dedent(
    r"""
    import asyncio
    import inspect
    import sys
    from pathlib import Path

    repo = Path.cwd()
    generated_dir = repo / "generated_code"
    sys.path.insert(0, str(generated_dir))

    from database import Database
    from crawler_service import CrawlerService

    def expect_params(fn, expected):
        actual = list(inspect.signature(fn).parameters)
        assert actual == expected, f"{fn.__qualname__} params {actual} != {expected}"

    expect_params(Database.force_pending, ["self", "url", "depth", "lock"])
    expect_params(Database.add_to_queue, ["self", "urls", "depth", "lock"])
    expect_params(Database.mark_processing, ["self", "url", "lock"])
    expect_params(Database.mark_done, ["self", "url", "lock"])
    expect_params(Database.save_page, ["self", "url", "title", "body", "origin_url", "depth", "lock"])
    expect_params(Database.resume_processing, ["self", "lock"])
    expect_params(Database.set_setting, ["self", "key", "value", "lock"])
    expect_params(CrawlerService.start_in_background, ["self", "seed_url", "max_depth"])
    expect_params(CrawlerService.resume_in_background, ["self", "max_depth"])
    expect_params(CrawlerService.stop, ["self"])
    assert hasattr(CrawlerService, "_run_index_job"), "CrawlerService is missing required _run_index_job"

    db = Database(str(generated_dir / "_contract.db"))
    service = CrawlerService(db)
    assert hasattr(service, "db_lock"), "CrawlerService instance is missing db_lock"
    contract_db_path = generated_dir / "_contract.db"

    async def close_db():
        await db.close()

    asyncio.run(close_db())
    if contract_db_path.exists():
        contract_db_path.unlink()
    print("API_OK")
    """
)


def analyze_with_llm(user_message: str, current_code: str) -> tuple[str, list[str], dict[str, str]]:
    import litellm

    system_prompt = """
You are the engineering manager for a multi-agent crawler builder.
Available agent keys:
- architect: system design and API contracts
- db: database.py
- crawler: crawler_service.py
- cli: main.py + requirements.txt
- qa: qa_report.md and corrected replacement files

Routing rules:
- qa must always be included.
- If the request is broad, touches crawler quality, or asks for a working crawler, include db + crawler + cli + qa.
- Prefer the full pipeline if there is any risk of interface mismatch.

Known failure modes to avoid:
- starting a second event loop in another thread
- using threading.Thread for crawler execution
- missing WAL mode
- not listing rich in requirements when Rich is imported
- saving raw markdown instead of actual code files
- accepting generated code without compile/smoke validation

Return JSON only:
{
  "understanding": "...",
  "route": ["architect", "db", "crawler", "cli", "qa"],
  "custom_prompts": {
    "crawler": "...",
    "cli": "...",
    "qa": "..."
  }
}
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"Developer request:\n{user_message}\n\n"
                f"Current generated code snapshot:\n{current_code[:12000]}"
            ),
        },
    ]

    print(f"[MANAGER] Analyzing request with {ACTIVE_MODEL_NAME}...")

    try:
        response = litellm.completion(
            model=ACTIVE_MODEL_NAME,
            api_key=ACTIVE_API_KEY,
            messages=messages,
            temperature=0.1,
        )
        content = response.choices[0].message.content.strip()
        content = re.sub(r"```json\s*", "", content)
        content = re.sub(r"```\s*", "", content)
        data = json.loads(content)
        understanding = data.get("understanding", "The request was analyzed.")
        route = data.get("route", PIPELINE_ORDER[:])
        prompts = data.get("custom_prompts", {})
    except Exception as exc:
        print(f"[MANAGER] Analysis failed, falling back to full pipeline: {exc}")
        understanding = "Falling back to the full pipeline for safety."
        route = PIPELINE_ORDER[:]
        prompts = {}

    if "qa" not in route:
        route.append("qa")

    route = [key for key in PIPELINE_ORDER if key in route]
    if not route:
        route = PIPELINE_ORDER[:]
    return understanding, route, prompts


def load_current_code_context() -> str:
    if not GENERATED_DIR.exists():
        return ""

    parts = ["### CURRENT GENERATED CODE ###"]
    for path in sorted(GENERATED_DIR.iterdir()):
        if path.is_file() and path.suffix in {".py", ".md", ".txt"}:
            try:
                parts.append(f"\n--- FILE: {path.name} ---\n{path.read_text(encoding='utf-8')}")
            except Exception:
                continue
    return "\n".join(parts)


def build_tasks(
    route: list[str],
    custom_prompts: dict[str, str],
    original_request: str,
    include_current_code: bool = True,
) -> list:
    current_code = load_current_code_context() if include_current_code else ""
    tasks = []
    previous_task = None

    for key in PIPELINE_ORDER:
        if key not in route:
            continue

        task_context = [previous_task] if previous_task else []
        instruction = custom_prompts.get(key, original_request)
        full_instruction = f"{instruction}\n\n{current_code}" if current_code else instruction
        task = TASK_BUILDER_MAP[key](user_request=full_instruction, context=task_context)
        tasks.append(task)
        previous_task = task

    return tasks


def extract_file_blocks(text: str) -> dict[str, str]:
    pattern = re.compile(
        r"FILE:\s*(?P<name>[^\n]+?)\s*\n```(?:python|text)?\n(?P<body>.*?)```",
        re.DOTALL,
    )
    return {
        match.group("name").strip(): match.group("body").strip() + "\n"
        for match in pattern.finditer(text)
    }


def extract_code_block(text: str, language: str = "python") -> str:
    typed = re.search(rf"```{language}\s*\n(.*?)```", text, re.DOTALL)
    if typed:
        return typed.group(1).strip() + "\n"

    generic = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if generic:
        return generic.group(1).strip() + "\n"

    return text.strip() + "\n"


def extract_requirements(text: str) -> str:
    blocks = extract_file_blocks(text)
    if "requirements.txt" in blocks:
        return blocks["requirements.txt"]

    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and re.match(r"^[A-Za-z0-9_.-]+([><=!~].*)?$", stripped):
            lines.append(stripped)

    return "\n".join(lines) + ("\n" if lines else "")


def collect_artifacts(tasks: list) -> dict[str, str]:
    artifacts: dict[str, str] = {}

    for task in tasks:
        raw = task.output.raw if hasattr(task.output, "raw") else str(task.output)
        blocks = extract_file_blocks(raw)
        role = task.agent.role
        if role == "QA Engineer":
            if "qa_report.md" in blocks:
                artifacts["qa_report.md"] = blocks["qa_report.md"]
            elif raw.strip():
                artifacts["qa_report.md"] = raw.strip() + "\n"
            continue

        artifacts.update(blocks)

        if blocks:
            continue

        default_name = ROLE_DEFAULT_FILES.get(role)
        if not default_name:
            continue

        if default_name.endswith(".py"):
            artifacts[default_name] = extract_code_block(raw, "python")
        elif default_name.endswith(".md"):
            artifacts[default_name] = raw.strip() + "\n"

        if role == "CLI Engineer":
            requirements = extract_requirements(raw)
            if requirements.strip():
                artifacts["requirements.txt"] = requirements

    return artifacts


def save_outputs(tasks: list) -> dict[str, str]:
    GENERATED_DIR.mkdir(exist_ok=True)
    artifacts = collect_artifacts(tasks)

    required_defaults = [
        "architecture.md",
        "database.py",
        "crawler_service.py",
        "main.py",
        "requirements.txt",
        "qa_report.md",
    ]
    for name in required_defaults:
        artifacts.setdefault(name, "")

    print("\n[MANAGER] Saving artifacts to generated_code/ ...")
    for filename, content in artifacts.items():
        target = GENERATED_DIR / filename
        target.write_text(content, encoding="utf-8")
        print(f"  [OK] {filename}")

    return artifacts


def write_verification_report(report: str) -> None:
    GENERATED_DIR.mkdir(exist_ok=True)
    (GENERATED_DIR / "verification_report.txt").write_text(report.strip() + "\n", encoding="utf-8")


def run_python_snippet(snippet: str, timeout: int = 40) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", snippet],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def verify_generated_code() -> tuple[bool, str]:
    missing = [
        name
        for name in ["database.py", "crawler_service.py", "main.py", "requirements.txt"]
        if not (GENERATED_DIR / name).exists()
    ]
    if missing:
        return False, f"Missing generated files: {', '.join(missing)}"

    database_text = (GENERATED_DIR / "database.py").read_text(encoding="utf-8", errors="ignore")
    crawler_text = (GENERATED_DIR / "crawler_service.py").read_text(encoding="utf-8", errors="ignore")
    main_text = (GENERATED_DIR / "main.py").read_text(encoding="utf-8", errors="ignore")
    requirements_text = (GENERATED_DIR / "requirements.txt").read_text(encoding="utf-8", errors="ignore")

    static_failures = []
    if "threading.Thread" in crawler_text or "threading.Thread" in main_text:
        static_failures.append("Crawler execution still uses threading.Thread.")
    if "asyncio.run(" in crawler_text:
        static_failures.append("crawler_service.py still contains asyncio.run(...).")
    if "async with self.db_lock" in crawler_text:
        static_failures.append(
            "crawler_service.py wraps database calls in async with self.db_lock. "
            "Database methods already acquire that lock, so this can deadlock and leave rows stuck in processing."
        )
    if "aiohttp" not in requirements_text.lower():
        static_failures.append("requirements.txt is missing aiohttp.")
    if "rich" in main_text.lower() and "rich" not in requirements_text.lower():
        static_failures.append("requirements.txt is missing rich even though main.py imports it.")
    if "PRAGMA journal_mode=WAL" not in database_text and "pragma journal_mode=wal" not in database_text.lower():
        static_failures.append("database.py does not clearly enable WAL mode.")

    if static_failures:
        return False, "\n".join(static_failures)

    compile_result = subprocess.run(
        [sys.executable, "-m", "compileall", str(GENERATED_DIR)],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        timeout=40,
    )
    if compile_result.returncode != 0:
        report = "Compile check failed.\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}".format(
            stdout=compile_result.stdout.strip(),
            stderr=compile_result.stderr.strip(),
        )
        return False, report

    contract_result = run_python_snippet(API_CONTRACT_SCRIPT, timeout=30)
    if contract_result.returncode != 0:
        report = "API contract check failed.\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}".format(
            stdout=contract_result.stdout.strip(),
            stderr=contract_result.stderr.strip(),
        )
        return False, report

    cli_result = subprocess.run(
        [sys.executable, "main.py"],
        cwd=GENERATED_DIR,
        input="exit\n",
        capture_output=True,
        text=True,
        timeout=20,
    )
    if cli_result.returncode != 0:
        report = "CLI startup check failed.\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}".format(
            stdout=cli_result.stdout.strip(),
            stderr=cli_result.stderr.strip(),
        )
        return False, report

    smoke_result = run_python_snippet(SMOKE_TEST_SCRIPT, timeout=45)
    if smoke_result.returncode != 0:
        report = "Smoke test failed.\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}".format(
            stdout=smoke_result.stdout.strip(),
            stderr=smoke_result.stderr.strip(),
        )
        return False, report

    report = "All acceptance checks passed.\n"
    report += f"Compile output:\n{compile_result.stdout.strip()}\n"
    report += f"API output:\n{contract_result.stdout.strip()}\n"
    report += f"CLI output:\n{cli_result.stdout.strip()}\n"
    report += f"Smoke output:\n{smoke_result.stdout.strip()}\n"
    return True, report


def describe_route(route: list[str], custom_prompts: dict[str, str], fallback_request: str) -> None:
    print("\n" + "=" * 60)
    print("[MANAGER] Selected route:")
    for agent_key in route:
        instruction = fallback_request
        preview = instruction.replace("\n", " ")
        if len(preview) > 160:
            preview = preview[:157] + "..."
        print(f"- {agent_key}: {preview}")
    print("=" * 60 + "\n")


def safe_console_text(text: str) -> str:
    return text.encode("ascii", errors="replace").decode("ascii")


def run_manager(request: str, max_attempts: int = 3) -> None:
    current_code = load_current_code_context()
    understanding, route, custom_prompts = analyze_with_llm(request, current_code)

    print("\n" + "=" * 60)
    print("[MANAGER] Understanding:")
    print(understanding)
    print("=" * 60)
    describe_route(route, custom_prompts, request)

    verification_feedback = ""
    final_ok = False

    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            print(f"[MANAGER] Retry attempt {attempt}/{max_attempts} with acceptance-test feedback.\n")

        active_route = route if attempt == 1 else PIPELINE_ORDER[:]
        effective_prompts = {}
        if verification_feedback:
            feedback_block = (
                "\n\nAcceptance-test failures to fix immediately:\n"
                f"{verification_feedback}\n"
                "Return corrected replacement files that fully address these failures."
            )
            for key in active_route:
                effective_prompts[key] = effective_prompts.get(key, request) + feedback_block

        tasks = build_tasks(active_route, effective_prompts, request, include_current_code=False)
        active_agents = [AGENT_MAP[key] for key in PIPELINE_ORDER if key in active_route]

        crew = Crew(
            agents=active_agents,
            tasks=tasks,
            process=Process.sequential,
            verbose=False,
        )

        print(f"[MANAGER] Running {len(tasks)} tasks...")
        crew.kickoff()

        print("\n[MANAGER] Task output previews:")
        for task in tasks:
            raw_output = task.output.raw if hasattr(task.output, "raw") else str(task.output)
            preview = safe_console_text(raw_output.replace("\n", " "))
            if len(preview) > 140:
                preview = preview[:137] + "..."
            print(f"- {task.agent.role}: {preview}")

        save_outputs(tasks)
        verified, report = verify_generated_code()
        write_verification_report(report)

        if verified:
            print("\n[MANAGER] Acceptance checks passed.")
            final_ok = True
            break

        verification_feedback = report
        print("\n[MANAGER] Acceptance checks failed.")
        print(safe_console_text(report))

    if not final_ok:
        print("\n[MANAGER] Failed to reach a passing build within the retry limit.")
    else:
        print("\n[MANAGER] Build completed successfully.")


def interactive_mode() -> None:
    print("\n" + "#" * 70)
    print("WEB CRAWLER BUILDER")
    print("#" * 70)
    print("Describe the change you want and the manager will route it to the agents.")
    print("Type 'exit', 'quit', or 'q' to leave.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break

        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "q"}:
            print("\nGoodbye.")
            break

        run_manager(user_input)
        print("\n" + "-" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-agent manager for the local web crawler builder.",
        epilog='Usage: python manager.py "make the crawler production-ready"',
    )
    parser.add_argument("prompt", nargs="*", help="Instruction for the agent team.")
    args = parser.parse_args()

    prompt_text = " ".join(args.prompt).strip()
    if prompt_text:
        run_manager(prompt_text)
    else:
        interactive_mode()


if __name__ == "__main__":
    main()
