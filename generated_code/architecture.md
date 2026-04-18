# Mimari Tasarım Belgesi: Mini Google Crawler (v1.0)

Bu belge, sistemin asenkron yapısını, modüller arası arayüzleri ve veri akışını tanımlayan referans dokümanıdır.

---

### 1. Dosya API'leri ve Arayüzler

#### `database.py`
```python
import sqlite3
import asyncio

class Database:
    def __init__(self, db_path: str) -> None: ...
    async def initialize(self) -> None: ...  # WAL mode ve tablo kurulumu
    async def save_pages(self, data: list[tuple[str, str]]) -> None: ... # executemany
    async def close(self) -> None: ...
```

#### `crawler_service.py`
```python
import aiohttp
import asyncio
from database import Database

class CrawlerService:
    def __init__(self, db: Database, max_concurrent: int, delay: float) -> None: ...
    async def crawl(self, start_url: str) -> None: ...
    async def _fetch(self, session: aiohttp.ClientSession, url: str) -> str | None: ...
    async def _parse(self, html: str) -> list[str]: ...
```

#### `main.py`
```python
from database import Database
from crawler_service import CrawlerService

async def main() -> None: ...
```

---

### 2. Thread Sınırları

*   **Main Thread:** Tüm `asyncio` event loop'u bu thread üzerinde çalışır.
*   **I/O Operasyonları:** `aiohttp` (Network I/O) ve `sqlite3` (Disk I/O) işlemleri, `asyncio` event loop'unu bloklamayacak şekilde `await` anahtar kelimesi ile yönetilir.
*   **Kısıt:** `sqlite3` kütüphanesi doğası gereği bloklayıcıdır. `Database` sınıfı içindeki metodlar, `asyncio.to_thread` veya `loop.run_in_executor` kullanılarak veya `aiosqlite` benzeri bir yapı taklit edilerek (thread-safe lock ile) main thread'in bloklanması engellenmelidir.

---

### 3. Veri Akış Diyagramı

1.  **Başlatma:** `main.py` -> `Database` (init) -> `CrawlerService` (init).
2.  **İstek:** `CrawlerService` -> `aiohttp.ClientSession.get()` -> `HTML Content`.
3.  **İşleme:** `HTML Content` -> `MiniParser` (HTMLParser) -> `List[URLs]`.
4.  **Senkronizasyon:** `CrawlerService` -> `asyncio.Lock()` (Lock edinilir).
5.  **Kalıcılık:** `Database.save_pages()` -> `sqlite3.executemany()` -> `Pages` tablosu.
6.  **Tamamlama:** `asyncio.Lock()` (Lock serbest bırakılır).

---

### 4. CrawlerService.__init__ ve Instance Değişkenleri

**Parametreler:**
*   `db` (`Database`): Veritabanı yönetim sınıfı instance'ı.
*   `max_concurrent` (`int`): `asyncio.Semaphore` için eşzamanlılık sınırı.
*   `delay` (`float`): İstekler arası `asyncio.sleep()` süresi.

**Instance Değişkenleri:**
*   `self.db`: `Database` objesi.
*   `self.semaphore`: `asyncio.Semaphore(max_concurrent)` (Bağlantı darboğazını önlemek için).
*   `self.lock`: `asyncio.Lock()` (Veritabanı yazma çakışmalarını önlemek için).
*   `self.visited`: `set[str]` (Ziyaret edilen URL'leri takip etmek için).
*   `self.delay`: `float` (Hız sınırlayıcı).

---

### Teknik Notlar (Mimari Kurallar)
*   **Modül Dışa Aktarma:** `database.py` içerisinde `__all__ = ["Database"]` tanımlanarak sadece `Database` sınıfının dışarıya açık olması sağlanmalıdır.
*   **WAL Modu:** `Database.initialize` metodu içerisinde `connection.execute("PRAGMA journal_mode=WAL;")` çağrısı zorunludur.
*   **Hata Yönetimi:** `MiniParser` içerisinde `handle_starttag` metodu sadece `<a>` etiketlerini ve `href` niteliklerini toplamalıdır.
*   **Güvenlik:** `sqlite3` işlemlerinde SQL Injection'ı önlemek için her zaman parametreli sorgular (`?` placeholder) kullanılmalıdır.