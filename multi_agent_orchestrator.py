"""
multi_agent_orchestrator.py
────────────────────────────
Gemini API kullanan multi-agent orkestratör.
.env dosyasında GEMINI_API_KEY olmalı.

Kurulum:
    pip install google-generativeai python-dotenv
    
Kullanım:
    python multi_agent_orchestrator.py start
    python multi_agent_orchestrator.py fix "backpressure mantığını düzelt"
    python multi_agent_orchestrator.py status
"""

import os
import json
import sys
import re
from pathlib import Path
from datetime import datetime

import google.generativeai as genai
from google.api_core.exceptions import NotFound, ResourceExhausted
from dotenv import load_dotenv

load_dotenv()


def configure_stdio() -> None:
    """Make Unicode console output work reliably on Windows terminals."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except ValueError:
                # Ignore streams that were replaced by objects without encoding support.
                pass


configure_stdio()

# ── Config ───────────────────────────────────────────────────────────────────

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
MODEL = os.environ.get("GEMINI_MODEL", "models/gemini-2.5-flash")
MODEL_FALLBACKS = [
    MODEL,
    "models/gemini-2.5-flash",
    "models/gemini-2.5-pro",
    "models/gemini-pro-latest",
]
SESSION_STATE_FILE = "session_state.json"
AGENTS_DIR = Path("agents")

# ── Session State (Hafıza) ────────────────────────────────────────────────────

def load_state() -> dict:
    if Path(SESSION_STATE_FILE).exists():
        return json.loads(Path(SESSION_STATE_FILE).read_text(encoding="utf-8"))
    return {
        "project_name": "web-crawler",
        "current_phase": "not_started",
        "completed_tasks": [],
        "pending_tasks": [],
        "last_architect_output": "",
        "last_developer_output": "",
        "last_tester_output": "",
        "last_docs_output": "",
        "files_written": [],
        "open_issues": [],
        "session_log": []
    }

def save_state(state: dict):
    Path(SESSION_STATE_FILE).write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )

# ── Agent System Prompt Yükleyici ─────────────────────────────────────────────

def load_system_prompt(agent_name: str) -> str:
    path = AGENTS_DIR / f"{agent_name}_agent.md"
    if path.exists():
        content = path.read_text(encoding="utf-8")
        instruction = """IMPORTANT INSTRUCTION:
Do not call read_file() or write_file() when you want to create or edit a file. Instead, use EXACTLY the following format.
ALL CONTENT YOU GENERATE MUST BE IN ENGLISH! NO TURKISH!

===FILE: path/to/file.ext===
[full file content here]
===ENDFILE===

Repeat this block for multiple files.

"""
        return instruction + content
    raise FileNotFoundError(f"System prompt bulunamadı: {path}")

# ── Dosya Parser ──────────────────────────────────────────────────────────────

def parse_and_write_files(text: str) -> list[str]:
    """Gemini çıktısındaki dosya bloklarını bulur ve diske yazar."""
    # Match strings strictly starting with ===FILE: and ending with ===ENDFILE===
    # Handle possible spaces, extra equals signs, or markdown codeblocks wrapping the files
    pattern = r"===FILE:\s*(.*?)[ \t=]*\n(.*?)===ENDFILE==="
    matches = re.findall(pattern, text, flags=re.DOTALL)
    
    written_files = []
    for filepath_str, file_content in matches:
        filepath_str = filepath_str.strip().strip("=")
        filepath = Path(filepath_str.strip())
        
        # Dizinleri oluştur
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # İçeriği yaz
        filepath.write_text(file_content, encoding="utf-8")
        written_files.append(str(filepath))
        
    return written_files

# ── Agent Çağırıcı ─────────────────────────────────────────────────────────────

def call_agent(agent_name: str, task: str, extra_context: str = "") -> str:
    """
    Belirtilen agent'ı Gemini API üzerinden çağırır.
    system_instruction → Gemini'nin system prompt alanı.
    Memory: session_state.json her çağrıda bağlam olarak eklenir.
    """
    state = load_state()
    system_prompt = load_system_prompt(agent_name)

    # Mevcut dosyaları oku
    def get_file_content(path_str):
        p = Path(path_str)
        return p.read_text(encoding="utf-8") if p.exists() else "Mevcut değil"

    db_content = get_file_content("database.py")
    crawler_content = get_file_content("crawler_service.py")
    main_content = get_file_content("main.py")

    user_message = f"""
KULLANICI İSTEĞİ:
{task}

MEVCUT DOSYALAR:
--- database.py ---
{db_content}

--- crawler_service.py ---
{crawler_content}

--- main.py ---
{main_content}

PROJE DURUMU (session_state.json):
{json.dumps(state, ensure_ascii=False, indent=2)}

EK BAĞLAM:
{extra_context if extra_context else "Yok"}

ÖNCEKİ ARCHITECT ÇIKTISI:
{state.get('last_architect_output', 'Henüz yok')[:2000]}

ÖNCEKİ DEVELOPER ÇIKTISI:
{state.get('last_developer_output', 'Henüz yok')[:2000]}

ÖNCEKİ TESTER ÇIKTISI:
{state.get('last_tester_output', 'Henüz yok')[:1000]}
"""

    last_error = None
    response = None

    for model_name in dict.fromkeys(MODEL_FALLBACKS):
        gemini = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_prompt,   # Gemini'de system prompt buraya gider
        )

        try:
            response = gemini.generate_content(
                user_message,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=8000,
                    temperature=0.2,   # kod yazan agentlar için düşük tutuyoruz
                )
            )
            break
        except (NotFound, ResourceExhausted) as exc:
            last_error = exc
            continue

    if response is None:
        raise last_error or RuntimeError("Hiçbir Gemini modeli çağrılamadı.")

    try:
        output = response.text
    except ValueError as e:
        print(f"Uyarı: API boş yanıt döndürdü ({e})")
        output = ""

    # Dosyaları parse et ve disk e yaz
    written = parse_and_write_files(output)

    # State güncelle — hafıza korunur
    state[f"last_{agent_name}_output"] = output
    if "files_written" not in state:
        state["files_written"] = []
    
    # Yazılan dosyaları state'e ekle (tekrarsız olarak ekleyebiliriz)
    for f in written:
        if f not in state["files_written"]:
            state["files_written"].append(f)

    state["session_log"].append({
        "timestamp": datetime.now().isoformat(),
        "agent": agent_name,
        "task_summary": task[:100],
        "files_written": written
    })
    save_state(state)

    return output

# ── Ana Orkestrasyon Akışları ──────────────────────────────────────────────────

def start_project():
    """Sıfırdan proje başlatma akışı."""
    state = load_state()
    state["current_phase"] = "architecture"
    save_state(state)

    print("🏛️  ARCHITECT çalışıyor...")
    arch_output = call_agent(
        "architect",
        task="Projeyi sıfırdan başlat. Mimari tasarımı yap, PRD yaz, developer brief hazırla.",
        extra_context="Mevcut dosyaları oku (database.py, crawler_service.py, main.py), LangGraph mimarisini tasarla."
    )
    print(arch_output)
    print("\n" + "─" * 60 + "\n")

    state = load_state()
    state["current_phase"] = "development"
    state["completed_tasks"].append("architecture")
    save_state(state)

    print("💻  DEVELOPER çalışıyor...")
    dev_output = call_agent(
        "developer",
        task="Architect'in tasarımına göre tüm kodu yaz. product_prd.md dosyasını oku ve uygula.",
    )
    print(dev_output)
    print("\n" + "─" * 60 + "\n")

    state = load_state()
    state["current_phase"] = "testing_and_docs"
    state["completed_tasks"].append("development")
    save_state(state)

    print("🧪  TESTER çalışıyor...")
    test_output = call_agent(
        "tester",
        task="Developer'ın yazdığı kodları test et. Test dosyalarını yaz ve çalıştır.",
    )
    print(test_output)
    print("\n" + "─" * 60 + "\n")

    print("📝  DOCS WRITER çalışıyor...")
    docs_output = call_agent(
        "docs_writer",
        task="readme.md, recommendation.md, multi_agent_workflow.md ve /agents/*.md dosyalarını yaz.",
    )
    print(docs_output)
    print("\n" + "─" * 60 + "\n")

    state = load_state()
    state["current_phase"] = "complete"
    state["completed_tasks"].extend(["testing", "documentation"])
    save_state(state)

    print("✅  İlk geliştirme turu tamamlandı!")
    print('Feedback vermek için: python multi_agent_orchestrator.py fix "[isteğin]"')


def apply_feedback(user_request: str):
    """Kullanıcının feedback'ini ilgili agent'a yönlendirir."""
    request_lower = user_request.lower()

    if "docs_writer" in request_lower or any(k in request_lower for k in ["readme", "belge", "dokümantasyon", "workflow"]):
        agent_order = ["docs_writer"]
    elif "architect" in request_lower or any(k in request_lower for k in ["mimari", "tasarım", "prd", "schema", "yapı"]):
        agent_order = ["architect", "developer", "tester"]
    elif "tester" in request_lower or any(k in request_lower for k in ["test", "hata", "bug", "çalışmıyor", "fail"]):
        agent_order = ["tester", "developer"]
    else:
        agent_order = ["developer", "tester"]

    print(f"🎯  Yönlendirme: {' → '.join(agent_order)}")
    print("\n" + "─" * 60 + "\n")

    for agent_name in agent_order:
        print(f"⚙️  {agent_name.upper()} çalışıyor...")
        output = call_agent(agent_name, task=user_request)
        print(output)
        print("\n" + "─" * 60 + "\n")

    state = load_state()
    state["session_log"].append({
        "timestamp": datetime.now().isoformat(),
        "event": "feedback_applied",
        "request": user_request
    })
    save_state(state)

    print("✅  Feedback uygulandı.")


def show_status():
    state = load_state()
    print(f"""
📊 PROJE DURUMU
────────────────
Faz: {state['current_phase']}
Tamamlanan: {', '.join(state['completed_tasks']) or 'Yok'}
Açık sorunlar: {', '.join(state['open_issues']) or 'Yok'}
Son architect: {state['last_architect_output'][:200] + '...' if state['last_architect_output'] else 'Yok'}
Son tester: {state['last_tester_output'][:200] + '...' if state['last_tester_output'] else 'Yok'}
""")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Kullanım:")
        print('  python multi_agent_orchestrator.py start          → Projeyi başlat')
        print('  python multi_agent_orchestrator.py fix "istek"    → Feedback ver')
        print('  python multi_agent_orchestrator.py status         → Durumu gör')
        sys.exit(0)

    command = sys.argv[1]

    if command == "start":
        start_project()
    elif command == "fix":
        if len(sys.argv) < 3:
            print('Kullanım: python multi_agent_orchestrator.py fix "düzeltme isteğin"')
            sys.exit(1)
        apply_feedback(sys.argv[2])
    elif command == "status":
        show_status()
    else:
        print(f"Bilinmeyen komut: {command}")
