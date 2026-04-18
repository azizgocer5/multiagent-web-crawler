import asyncio
from crawler_service import CrawlerService
from database import Database

async def main():
    db = Database('crawler.db')
    lock = asyncio.Lock()
    service = CrawlerService(db)

    while True:
        komut_raw = await asyncio.to_thread(input, '> ')
        komut = komut_raw.split()
        if not komut:
            continue

        if komut[0] == 'crawl':
            if len(komut) != 3:
                print("Kullanım: crawl <url> <depth>")
                continue
            url, depth = komut[1], komut[2]
            await db.set_setting('max_depth', str(depth))
            await db.add_to_queue(lock, [url], depth=0)
            service.start_in_background(url, int(depth))

        elif komut[0] == 'search':
            if len(komut) != 2:
                print("Kullanım: search <query>")
                continue
            query = komut[1]
            results = await db.search(query)
            if not results:
                print("Sonuç bulunamadı.")
            for result in results:
                # url, title, score
                print(f"[Score: {result[2]}] {result[1]} (kaynak: {result[0]})")

        elif komut[0] == 'status':
            status = await db.get_status()
            print(f"Bekleyen: {status['pending']} | İşleniyor: {status['processing']} | Tamamlanan: {status['done']}")

        elif komut[0] == 'resume':
            await db.resume_processing(lock)
            max_depth = int(await db.get_setting('max_depth') or 2)
            service.resume_in_background(max_depth)

        elif komut[0] == 'exit':
            break

        else:
            print("Kullanım:")
            print("  crawl <url> <depth>")
            print("  search <query>")
            print("  status")
            print("  resume")
            print("  exit")

if __name__ == '__main__':
    asyncio.run(main())