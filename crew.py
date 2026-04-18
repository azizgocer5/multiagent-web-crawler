"""
crew.py — Agent ve Task Factory Tanımları (CrewAI)

5 uzman agent + dinamik task factory fonksiyonları.
Manager istediği kombinasyonu çalıştırabilir.
"""

import os
import litellm
from dotenv import load_dotenv
from crewai import Agent, Task, LLM

load_dotenv()

# ── LLM Fallback Zinciri ─────────────────────────────────────
# En iyi modelden en düşüğe dener, ilk çalışanı kullanır.

MODEL_CHAIN = [
    # ── Groq modelleri (öncelikli) ──
    {"model": "gemini/gemini-3.1-flash-lite-preview",   "api_key": os.getenv("API_KEY")},
    {"model": "groq/llama-3.3-70b-versatile",                   "api_key": os.getenv("GROQ_KEY")},
    # ── Gemini modelleri ──
    {"model": "gemini/gemini-2.5-pro",                  "api_key": os.getenv("API_KEY")},
    {"model": "gemini/gemini-2.5-pro-preview-05-06",    "api_key": os.getenv("API_KEY")},
    {"model": "gemini/gemini-2.5-flash-preview-04-17",  "api_key": os.getenv("API_KEY")},
    {"model": "gemini/gemini-2.0-flash",                "api_key": os.getenv("API_KEY")},
    {"model": "gemini/gemini-2.0-flash-lite",           "api_key": os.getenv("API_KEY")},
    {"model": "gemini/gemini-1.5-flash",                "api_key": os.getenv("API_KEY")},
    # ── Groq modelleri (fallback) ──
    {"model": "groq/meta-llama/llama-4-scout-17b-16e-instruct", "api_key": os.getenv("GROQ_KEY")},
    {"model": "groq/llama-3.3-70b-versatile",                   "api_key": os.getenv("GROQ_KEY")},
    {"model": "groq/llama-3.1-8b-instant",                      "api_key": os.getenv("GROQ_KEY")},
]


def _select_llm() -> LLM:
    """
    Model zincirini en iyiden en dusuge dener.
    Ilk basarili yanit veren modeli secer ve doner.
    """
    for entry in MODEL_CHAIN:
        model_name = entry["model"]
        api_key = entry["api_key"]

        if not api_key:
            print(f"  [SKIP] {model_name} -- API key yok, atlaniyor")
            continue

        try:
            print(f"  [TRY]  {model_name} deneniyor...", end=" ", flush=True)
            # LiteLLM ile kucuk bir test cagrisi
            response = litellm.completion(
                model=model_name,
                api_key=api_key,
                messages=[{"role": "user", "content": "Merhaba, kisa bir test. Sadece 'OK' yaz."}],
                max_tokens=10,
                temperature=0.0,
            )
            result = response.choices[0].message.content.strip()
            print(f"OK! Yanit: {result}")
            print(f"  [WIN]  Secilen model: {model_name}\n")
            return LLM(
                model=model_name,
                api_key=api_key,
                temperature=0.3,
                max_tokens=8000,
            )
        except Exception as e:
            error_msg = str(e)[:80]
            print(f"FAIL: {error_msg}")
            continue

    # Hicbiri calismazsa son care
    raise RuntimeError(
        "Hicbir model yanit vermedi! API anahtarlarini ve kota limitlerini kontrol edin."
    )


print("=" * 50)
print("LLM Model Secimi -- Fallback Zinciri")
print("=" * 50)
active_llm = _select_llm()

# ── Ortak Mimari Brief (tüm task'lara inject edilir) ──────────
ARCHITECTURE_BRIEF = """
Hedef proje: Python asyncio + aiohttp tabanlı web crawler (Mini Google).
Dosyalar: main.py (CLI), crawler_service.py (async motor), database.py (SQLite).
Zorunlu kısıtlar:
- HTTP: sadece aiohttp (requests/httpx yasak)
- Parsing: sadece html.parser tabanlı MiniParser (beautifulsoup yasak)
- DB: sadece sqlite3 (SQLAlchemy/ORM yasak)
- Her bağlantıda: PRAGMA journal_mode=WAL
- DB yazmaları: asyncio.Lock altında
- Toplu insert: executemany (döngüde INSERT yasak)
- Bekleme: asyncio.sleep() (time.sleep() yasak)
"""

# ── Agent Tanımları ───────────────────────────────────────────

architect = Agent(
    role="Sistem Mimarı",
    goal="Projenin iskeletini ve modüller arası arayüzleri net biçimde tasarlamak",
    backstory=(
        "Asenkron Python sistemleri konusunda uzmanlaşmış kıdemli bir yazılım mimarısın. "
        "Concurrency hatalarını ve performans darboğazlarını önceden görürsün. "
        "Tasarımın diğer tüm agent'ların referans belgesi olur."
    ),
    llm=active_llm,
    verbose=True,
)

db_engineer = Agent(
    role="Veritabanı Mühendisi",
    goal="database.py dosyasını thread-safe ve eksiksiz yazmak",
    backstory=(
        "SQLite WAL modunu ve concurrency sınırlarını derinlemesine bilen birisin. "
        "Her yazma işlemini kilit altına alırsın, toplu insert için daima executemany kullanırsın. "
        "Race condition senin sözlüğünde yoktur."
    ),
    llm=active_llm,
    verbose=True,
)

crawler_dev = Agent(
    role="Async Sistem Geliştirici",
    goal="crawler_service.py ve MiniParser'ı eksiksiz yazmak",
    backstory=(
        "Python asyncio ve aiohttp'yi içselleştirmiş bir backend mühendisisin. "
        "Event loop'u asla bloke etmezsin. try/finally senin için refleks, "
        "asyncio.sleep() senin için nefes almak gibidir."
    ),
    llm=active_llm,
    verbose=True,
)

cli_dev = Agent(
    role="CLI ve Entegrasyon Mühendisi",
    goal="main.py ve requirements.txt dosyalarını yazmak",
    backstory=(
        "Kullanıcı deneyimini ve thread güvenliğini eş zamanlı düşünen bir mühendisisin. "
        "Senkron CLI ile async arka planı sorunsuz köprülersin. "
        "requirements.txt'i minimal tutarsın: gereksiz bağımlılık eklemek karakterine aykırıdır."
    ),
    llm=active_llm,
    verbose=True,
)

qa = Agent(
    role="QA Mühendisi",
    goal="Üretilen tüm dosyaları kontrol listesiyle denetleyip hataları düzeltmek",
    backstory=(
        "Concurrency bug'larını, SQLite kilitlenmelerini ve async antipatternleri "
        "uyurken fark edersin. Kod review'unda merhametin yoktur. "
        "Onayladığın kod production'a gider."
    ),
    llm=active_llm,
    verbose=True,
)

# ── Task Factory Fonksiyonları ────────────────────────────────

def make_architect_task(user_request: str, context: list) -> Task:
    return Task(
        description=(
            f"{ARCHITECTURE_BRIEF}\n\n"
            f"Kullanıcı isteği: {user_request}\n\n"
            "Şunları üret:\n"
            "1. Her dosyanın public API'si: fonksiyon imzaları ve dönüş tipleri\n"
            "2. Thread sınırları: hangi kod main thread'de, hangisi background thread'de\n"
            "3. Veri akış diyagramı: URL'nin `crawl` komutundan `Pages` tablosuna "
            "geçtiği her adım\n"
            "4. CrawlerService.__init__ parametreleri ve instance değişkenleri\n\n"
            "Çıktın diğer tüm agent'ların referans belgesidir. Teknik ve eksiksiz olsun."
        ),
        expected_output=(
            "Mimari tasarım belgesi: dosya API'leri, thread sınırları, veri akış diyagramı, "
            "CrawlerService init parametreleri"
        ),
        agent=architect,
        context=context,
    )


def make_db_task(user_request: str, context: list) -> Task:
    return Task(
        description=(
            f"{ARCHITECTURE_BRIEF}\n\n"
            f"Kullanıcı isteği: {user_request}\n\n"
            "Mimari tasarımı kullanarak database.py dosyasını yaz.\n\n"
            "Zorunlu metodlar:\n"
            "- __init__(db_path): bağlantıyı aç, WAL'ı aktif et, 3 tabloyu oluştur\n"
            "- add_to_queue(urls: list[str], depth: int): INSERT OR IGNORE + executemany\n"
            "- get_pending(limit: int) -> list[tuple]: state='pending' olanlar\n"
            "- mark_processing(url: str): state → 'processing'\n"
            "- mark_done(url: str): state → 'done'\n"
            "- save_page(url, title, body, origin_url, depth): Pages'e INSERT OR IGNORE\n"
            "- resume_processing(): state='processing' → 'pending'\n"
            "- get_status() -> dict: {'pending': N, 'processing': N, 'done': N}\n"
            "- search(query: str) -> list[tuple]: turkish_lower ile title(+10)/body(+1) puanlama\n"
            "- get_setting(key) -> str | None\n"
            "- set_setting(key, value): INSERT OR REPLACE\n\n"
            "Kurallar:\n"
            "- Yazma metodları dışarıdan inject edilen lock alır (asyncio.Lock)\n"
            "- executemany dışında döngüde INSERT kesinlikle yasak\n"
            "- Dosya sonuna __main__ test bloğu ekle (her metodu çağır)"
        ),
        expected_output="Eksiksiz ve çalışır database.py dosya içeriği",
        agent=db_engineer,
        context=context,
    )


def make_crawler_task(user_request: str, context: list) -> Task:
    return Task(
        description=(
            f"{ARCHITECTURE_BRIEF}\n\n"
            f"Kullanıcı isteği: {user_request}\n\n"
            "Mimari ve database.py kullanarak crawler_service.py yaz.\n\n"
            "MiniParser(HTMLParser):\n"
            "- handle_starttag: script/style/head → _skip=True; a tag → href topla\n"
            "- handle_endtag: _skip=False\n"
            "- handle_data: _skip=False ise body'ye ekle; title içindeyse title'a ekle\n"
            "- get_links(base_url) -> list[str]: urljoin + sadece http/https filtresi\n\n"
            "CrawlerService:\n"
            "- __init__(db, worker_count=30):\n"
            "    self.memory_queue = asyncio.Queue(maxsize=100)\n"
            "    self.db_lock = asyncio.Lock()\n"
            "    self._running = False\n"
            "- _worker(session) adımları:\n"
            "    1. memory_queue'dan (url, depth) al\n"
            "    2. aiohttp GET (timeout=aiohttp.ClientTimeout(total=10))\n"
            "    3. Content-Type 'text/html' değilse → mark_done, devam\n"
            "    4. MiniParser ile parse et\n"
            "    5. async with self.db_lock: save_page + add_to_queue(yeni_linkler, depth+1)\n"
            "    6. mark_done\n"
            "    7. try/except: herhangi hata → mark_done, logging.warning\n"
            "- _run_index_job(max_depth) adımları:\n"
            "    1. while self._running:\n"
            "    2. qsize >= 100 → asyncio.sleep(0.5); continue\n"
            "    3. get_pending(limit=10) → boşsa asyncio.sleep(0.5); continue\n"
            "    4. Her URL: mark_processing + memory_queue.put((url, depth))\n"
            "    5. asyncio.sleep(0.1)\n"
            "- start_in_background(seed_url, max_depth):\n"
            "    threading.Thread(target=lambda: asyncio.run(self.start(...)))\n"
            "- resume_in_background(max_depth): aynı pattern\n\n"
            "Yasak: time.sleep, requests, beautifulsoup, döngüde DB yazma"
        ),
        expected_output="Eksiksiz ve çalışır crawler_service.py dosya içeriği",
        agent=crawler_dev,
        context=context,
    )


def make_cli_task(user_request: str, context: list) -> Task:
    return Task(
        description=(
            f"{ARCHITECTURE_BRIEF}\n\n"
            f"Kullanıcı isteği: {user_request}\n\n"
            "Tüm önceki dosyaları import ederek main.py yaz.\n\n"
            "Yapı:\n"
            "- Database('crawler.db') ve CrawlerService(db) başlat\n"
            "- while True döngüsü: input('> ') ile komut al\n\n"
            "Komutlar:\n"
            "- crawl <url> <depth>:\n"
            "    db.set_setting('max_depth', str(depth))\n"
            "    db.add_to_queue([url], depth=0)\n"
            "    service.start_in_background(url, depth)\n"
            "- search <query>: db.search(query) → '[depth] url (kaynak: origin)' formatında listele\n"
            "- status: db.get_status() → 'Bekleyen: N | İşleniyor: N | Tamamlanan: N'\n"
            "- resume:\n"
            "    db.resume_processing()\n"
            "    max_depth = int(db.get_setting('max_depth') or 2)\n"
            "    service.resume_in_background(max_depth)\n"
            "- exit: break\n"
            "- bilinmeyen komut: kullanım bilgisi yaz\n\n"
            "requirements.txt:\n"
            "Tek satır: aiohttp>=3.9.0\n"
            "Başka hiçbir şey ekleme."
        ),
        expected_output="Eksiksiz main.py ve requirements.txt dosya içerikleri",
        agent=cli_dev,
        context=context,
    )


def make_qa_task(user_request: str, context: list) -> Task:
    return Task(
        description=(
            f"Kullanıcı isteği: {user_request}\n\n"
            "Üretilen tüm dosyaları denetle. Her kontrolü geç/geçemedi olarak işaretle "
            "ve başarısız olanları düzelt.\n\n"
            "database.py:\n"
            "[ ] WAL pragma her bağlantıda\n"
            "[ ] add_to_queue executemany kullanıyor\n"
            "[ ] Yazma metodları lock parametresi alıyor\n"
            "[ ] search() turkish_lower normalizasyonu yapıyor\n"
            "[ ] resume_processing() processing→pending\n\n"
            "crawler_service.py:\n"
            "[ ] _worker try/except ile sarılı\n"
            "[ ] Hata durumunda mark_done çağrılıyor\n"
            "[ ] DB yazmaları async with self.db_lock içinde\n"
            "[ ] time.sleep() YOK, asyncio.sleep() VAR\n"
            "[ ] memory_queue maxsize=100\n"
            "[ ] Producer qsize>=100 ise bekliyor\n"
            "[ ] aiohttp timeout=10s\n"
            "[ ] Content-Type text/html kontrolü var\n"
            "[ ] urljoin ile tam URL dönüşümü\n"
            "[ ] MiniParser script/style/head atlıyor\n\n"
            "main.py:\n"
            "[ ] crawl max_depth'i Settings'e kaydediyor\n"
            "[ ] resume max_depth'i Settings'ten okuyor\n"
            "[ ] CLI ana thread'de, crawler arka planda\n\n"
            "Her dosya için çıktı:\n"
            "1. Kontrol listesi (✅/❌ her madde)\n"
            "2. Bulunan sorunlar (satır + açıklama)\n"
            "3. Düzeltilmiş tam dosya içeriği\n"
            "(Sorun yoksa: ✅ [dosyaadi] — Tüm kontroller geçti.)"
        ),
        expected_output=(
            "Her dosya için: kontrol listesi sonuçları + hata raporu + düzeltilmiş final kod"
        ),
        agent=qa,
        context=context,
    )
