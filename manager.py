"""
manager.py — Kullanıcıyla Konuşan Orkestratör

Kullanıcıyla terminal üzerinde doğal dilde konuşur.
Ne yapılmak istendiğini anlar, hangi agent(ların) çalışacağına karar verir,
crew'u dinamik olarak o şekilde kurar ve tetikler.
"""

import os
import re
from crewai import Crew, Process
from crew import (
    architect, db_engineer, crawler_dev, cli_dev, qa,
    make_architect_task, make_db_task, make_crawler_task,
    make_cli_task, make_qa_task,
)

# ── Routing Tablosu ───────────────────────────────────────────
# SIRALAMA ÖNEMLİ: daha spesifik keyword'ler üstte olmalı.
# "fix_crawler" → "fix"ten önce, "fix" → genel keyword'lerden önce.

ROUTE_MAP = [
    ("fix_main",    ["cli"]),
    ("fix_crawler", ["crawler"]),
    ("fix",         ["crawler", "cli"]),
    ("hepsi",       ["architect", "db", "crawler", "cli", "qa"]),
    ("tumu",        ["architect", "db", "crawler", "cli", "qa"]),
    ("tümü",        ["architect", "db", "crawler", "cli", "qa"]),
    ("bastan",      ["architect", "db", "crawler", "cli", "qa"]),
    ("baştan",      ["architect", "db", "crawler", "cli", "qa"]),
    ("sifirdan",    ["architect", "db", "crawler", "cli", "qa"]),
    ("sıfırdan",    ["architect", "db", "crawler", "cli", "qa"]),
    ("mimari",      ["architect"]),
    ("tasarım",     ["architect"]),
    ("database",    ["architect", "db"]),
    ("veritabanı",  ["architect", "db"]),
    ("crawler",     ["architect", "db", "crawler"]),
    ("parser",      ["architect", "db", "crawler"]),
    ("worker",      ["architect", "db", "crawler"]),
    ("cli",         ["architect", "db", "crawler", "cli"]),
    ("main",        ["architect", "db", "crawler", "cli"]),
    ("komut",       ["architect", "db", "crawler", "cli"]),
    ("qa",          ["qa"]),
    ("test",        ["qa"]),
    ("kontrol",     ["qa"]),
    ("denetle",     ["qa"]),
]

# Sabit pipeline sırası — task'lar ve agent'lar hep bu sıraya göre kurulur.
PIPELINE_ORDER = ["architect", "db", "crawler", "cli", "qa"]

AGENT_MAP = {
    "architect": architect,
    "db":        db_engineer,
    "crawler":   crawler_dev,
    "cli":       cli_dev,
    "qa":        qa,
}

TASK_BUILDER_MAP = {
    "architect": make_architect_task,
    "db":        make_db_task,
    "crawler":   make_crawler_task,
    "cli":       make_cli_task,
    "qa":        make_qa_task,
}

# ── Routing ───────────────────────────────────────────────────

def detect_route(user_message: str) -> list:
    """
    ROUTE_MAP'i sırayla tarar (list of tuples → öncelik korunur).
    İlk eşleşen keyword'ün agent listesini döner.
    Eşleşme yoksa tüm pipeline çalışır.
    """
    msg = user_message.lower()
    for keyword, agents in ROUTE_MAP:
        if keyword in msg:
            return agents
    return PIPELINE_ORDER[:]  # Varsayılan: hepsi

# ── Task Zinciri ──────────────────────────────────────────────

def build_tasks(route: list, user_request: str) -> list:
    """
    Seçilen agent'lar için task'ları PIPELINE_ORDER sırasına göre kurar.
    Her task bir öncekinin çıktısını context olarak alır.
    """
    tasks = []
    prev = None
    for key in PIPELINE_ORDER:
        if key not in route:
            continue
        context = [prev] if prev else []
        task = TASK_BUILDER_MAP[key](user_request=user_request, context=context)
        tasks.append(task)
        prev = task
    return tasks

# ── Kod Temizleme ─────────────────────────────────────────────

def extract_code_block(text: str, lang: str = "python") -> str:
    """
    Verilen lang'a göre ilk markdown code bloğunu çıkarır.
    Bulamazsa ham metni döner.
    """
    pattern = rf"```{lang}\s*\n(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Dil etiketi olmayan genel ``` bloğu dene
    match = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    return text.strip()

def extract_requirements(text: str) -> str | None:
    """
    CLI agent çıktısından requirements.txt içeriğini ayıklar.
    'aiohttp>=3.9.0' içeren satırı bulur.
    """
    for line in text.split("\n"):
        if "aiohttp" in line and ">=" in line:
            return line.strip()
    return "aiohttp>=3.9.0"  # bulamazsa güvenli varsayılan

# ── Dosya Kaydetme ────────────────────────────────────────────

def save_outputs(tasks: list):
    """
    Her task'ın çıktısını ilgili dosyaya kaydeder.
    task.output.raw → ham LLM çıktısı (str() yerine güvenli).
    """
    os.makedirs("generated_code", exist_ok=True)
    print("\nDosyalar kaydediliyor (generated_code/)...")

    for task in tasks:
        # TaskOutput objesinden ham metni al
        raw = task.output.raw if hasattr(task.output, "raw") else str(task.output)
        role = task.agent.role

        if role == "Sistem Mimarı":
            path = "generated_code/architecture.md"
            with open(path, "w", encoding="utf-8") as f:
                f.write(raw)
            print(f"  [OK] architecture.md")

        elif role == "Veritabanı Mühendisi":
            path = "generated_code/database.py"
            with open(path, "w", encoding="utf-8") as f:
                f.write(extract_code_block(raw, "python"))
            print(f"  [OK] database.py")

        elif role == "Async Sistem Geliştirici":
            path = "generated_code/crawler_service.py"
            with open(path, "w", encoding="utf-8") as f:
                f.write(extract_code_block(raw, "python"))
            print(f"  [OK] crawler_service.py")

        elif role == "CLI ve Entegrasyon Mühendisi":
            # main.py — python bloğunu al
            path = "generated_code/main.py"
            with open(path, "w", encoding="utf-8") as f:
                f.write(extract_code_block(raw, "python"))
            print(f"  [OK] main.py")

            # requirements.txt — ayrı olarak ayıkla
            req_path = "generated_code/requirements.txt"
            with open(req_path, "w", encoding="utf-8") as f:
                f.write(extract_requirements(raw) + "\n")
            print(f"  [OK] requirements.txt")

        elif role == "QA Mühendisi":
            path = "generated_code/qa_report.md"
            with open(path, "w", encoding="utf-8") as f:
                f.write(raw)
            print(f"  [OK] qa_report.md")

# ── Ana Döngü ─────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Web Crawler Builder -- AI Gelistirme Asistani")
    print("  Ne yapmami istersin? (cikmak icin 'exit')")
    print("=" * 60)

    while True:
        try:
            user_input = input("\nSen: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGorusuruz!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "cikis", "q"):
            print("Gorusuruz!")
            break

        route = detect_route(user_input)
        print(f"\n[Manager] Calisacak agent'lar: {' -> '.join(route)}")

        tasks = build_tasks(route, user_input)

        # Agent listesi task sırasıyla eşleşsin (PIPELINE_ORDER garantisi)
        active_agents = [AGENT_MAP[key] for key in PIPELINE_ORDER if key in route]

        crew = Crew(
            agents=active_agents,
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
        )

        print(f"[Manager] {len(tasks)} gorev baslatiliyor...\n")
        crew.kickoff()

        save_outputs(tasks)

        print("=" * 60)
        print("[Manager] Tum gorevler tamamlandi.")
        print("Baska bir sey ister misin?")


if __name__ == "__main__":
    main()