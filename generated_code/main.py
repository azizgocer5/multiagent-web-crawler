import asyncio
import logging
import sys
import traceback
from database import Database
from crawler_service import CrawlerService

# Loglama ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("crawler.log"), logging.StreamHandler()]
)

async def main():
    db = Database('crawler.db')
    service = CrawlerService(db)
    
    print("Mini Google CLI Başlatıldı. Komutlar: crawl, search, status, resume, exit")
    
    try:
        while True:
            try:
                # CLI üzerinden asenkron girdi alma
                cmd_input = await asyncio.to_thread(input, '> ')
                parts = cmd_input.split()
                if not parts:
                    continue
                
                cmd = parts[0].lower()
                
                if cmd == 'crawl':
                    if len(parts) < 3:
                        print("Kullanım: crawl <url> <depth>")
                        continue
                    url, depth = parts[1], int(parts[2])
                    db.set_setting('max_depth', str(depth))
                    db.add_to_queue([url], depth=0)
                    service.start_in_background(url, depth)
                    print(f"Crawling başlatıldı: {url}")

                elif cmd == 'search':
                    query = " ".join(parts[1:])
                    if not query:
                        print("Arama terimi girin.")
                        continue
                    try:
                        results = db.search(query)
                        if not results:
                            print("Sonuç bulunamadı.")
                        else:
                            for depth, url, origin in results:
                                print(f"[{depth}] {url} (kaynak: {origin})")
                    except Exception as e:
                        logging.error(f"Arama hatası: {traceback.format_exc()}")
                        print("Arama işlemi başarısız oldu. Lütfen crawler.log dosyasını kontrol edin.")

                elif cmd == 'status':
                    status = db.get_status()
                    print(f"Bekleyen: {status['pending']} | İşleniyor: {status['processing']} | Tamamlanan: {status['done']}")

                elif cmd == 'resume':
                    db.resume_processing()
                    max_depth = int(db.get_setting('max_depth') or 2)
                    service.resume_in_background(max_depth)
                    print("İşlemler devam ettiriliyor...")

                elif cmd == 'exit':
                    print("Kapatılıyor...")
                    service.stop()
                    break

                else:
                    print("Bilinmeyen komut. Kullanılabilir: crawl, search, status, resume, exit")

            except Exception as e:
                logging.error(f"Komut işleme hatası: {traceback.format_exc()}")
                print(f"Bir hata oluştu: {e}")
                
    except KeyboardInterrupt:
        print("\nKullanıcı tarafından durduruldu.")
    finally:
        service.stop()
        print("Sistem güvenli bir şekilde kapatıldı.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logging.critical(f"Uygulama çöktü: {traceback.format_exc()}")
        sys.exit(1)