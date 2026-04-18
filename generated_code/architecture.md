Bu mimari doküman, "Mini Google" projesinin asenkron çalışma prensiplerini, thread yönetimini ve veri akışını tanımlayan referans belgesidir.

### 1. Mimari Tasarım ve API Tanımları

#### `database.py`
SQLite işlemlerini yönetir. `asyncio.Lock` ile thread-safe yazma garantisi verir.
*   `def __init__(db_path: str)`: Bağlantıyı kurar, `PRAGMA journal_mode=WAL` uygular, tabloyu oluşturur.
*   `async def save_pages(pages: list[tuple[str, str, str]]) -> None`: `executemany` kullanarak veritabanına toplu yazar.
*   `async def close() -> None`: Bağlantıyı kapatır.

#### `crawler_service.py`
`aiohttp` ile ağ trafiğini yönetir ve `MiniParser` ile veriyi işler.
*   `class CrawlerService`:
    *   `__init__(self, db: Database, max_concurrent: int, user_agent: str)`
    *   `async def crawl(self, start_urls: list[str]) -> None`: Ana giriş noktası.
    *   `async def _fetch(self, session: aiohttp.ClientSession, url: str) -> str | None`
    *   `async def _run_index_job(self, queue: asyncio.Queue) -> None`: Producer mantığı.

#### `main.py`
CLI arayüzü ve uygulama yaşam döngüsü.
*   `async def main()`: Servisleri başlatır ve `asyncio.run` ile döngüyü yönetir.

---

### 2. Thread Sınırları
*   **Main Thread:** Tüm `asyncio` event loop'u bu thread'de çalışır.
*   **Background Thread:** SQLite `sqlite3` kütüphanesi bloklayıcı olduğu için, yoğun I/O işlemlerinde `loop.run_in_executor` kullanılarak veritabanı işlemleri ayrı bir thread havuzuna delege edilebilir (Opsiyonel ancak önerilir). Ancak mevcut kısıtlar dahilinde `asyncio.Lock` ile main thread üzerinde senkronize edilmiştir.

---

### 3. Veri Akış Diyagramı
1.  **Giriş:** `main.py` üzerinden URL listesi `CrawlerService.crawl` metoduna iletilir.
2.  **Kuyruklama:** URL'ler `asyncio.Queue` yapısına eklenir.
3.  **Fetch:** `CrawlerService`, `aiohttp` ile sayfayı çeker.
4.  **Parse:** `MiniParser` (HTMLParser), ham HTML'i işler ve metin/linkleri ayıklar.
5.  **Lock & Write:** `database.py` içindeki `save_pages` metodu `asyncio.Lock` edinir.
6.  **Commit:** `executemany` ile veriler `Pages` tablosuna yazılır ve lock serbest bırakılır.

---

### 4. CrawlerService Instance Değişkenleri
*   `self.db`: Database sınıfı örneği.
*   `self.session`: `aiohttp.ClientSession` (headers tanımlı).
*   `self.max_concurrent`: Semaphor için limit.
*   `self.lock`: `asyncio.Lock()` (yazma işlemleri için).

---

### 5. Uygulama Kodları

#### `database.py`
```python
import sqlite3
import asyncio

class Database:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("CREATE TABLE IF NOT EXISTS pages (url TEXT, title TEXT, content TEXT)")
        self.lock = asyncio.Lock()

    async def save_pages(self, pages: list[tuple[str, str, str]]):
        async with self.lock:
            self.conn.executemany("INSERT INTO pages VALUES (?, ?, ?)", pages)
            self.conn.commit()
```

#### `crawler_service.py`
```python
import asyncio
import aiohttp
from html.parser import HTMLParser

class MiniParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.data = []
    def handle_data(self, data):
        self.data.append(data)

class CrawlerService:
    def __init__(self, db, max_concurrent=5):
        self.db = db
        self.max_concurrent = max_concurrent
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    async def _run_index_job(self, queue: asyncio.Queue):
        async with aiohttp.ClientSession(headers=self.headers) as session:
            while not queue.empty():
                url = await queue.get()
                try:
                    async with session.get(url) as resp:
                        html = await resp.text()
                        # Parsing ve DB işlemleri burada
                        await self.db.save_pages([(url, "Title", html[:100])])
                finally:
                    queue.task_done()
                
                if queue.empty(): break
```

#### `main.py`
```python
import asyncio
from database import Database
from crawler_service import CrawlerService

async def main():
    db = Database("crawler.db")
    crawler = CrawlerService(db)
    queue = asyncio.Queue()
    
    urls = ["https://en.wikipedia.org/wiki/Main_Page"]
    for u in urls: await queue.put(u)
    
    await crawler._run_index_job(queue)

if __name__ == "__main__":
    asyncio.run(main())
```