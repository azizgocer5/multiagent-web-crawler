import asyncio
import sys

from crawler_service import CrawlerService
from database import Database


async def main() -> None:
    db = Database("crawler.db")
    crawler = CrawlerService(db)

    print("Mini Search Engine CLI")
    print("Commands: crawl <url> <depth>, search <query>, status, resume, exit")

    try:
        while True:
            raw = await asyncio.to_thread(input, "> ")
            parts = raw.strip().split()
            if not parts:
                continue

            cmd = parts[0].lower()

            if cmd == "crawl" and len(parts) >= 3:
                url = parts[1]
                depth = int(parts[2])
                await db.set_setting("max_depth", str(depth), crawler.db_lock)
                crawler.start_in_background(url, depth)
                print(f"Started crawling {url} at depth {depth}")

            elif cmd == "search" and len(parts) >= 2:
                query = " ".join(parts[1:])
                results = await db.search(query)
                if not results:
                    print("No results found.")
                else:
                    for row in results:
                        print(
                            f"[depth={row['depth']}] {row['title']} | "
                            f"{row['url']} | origin={row['origin_url']}"
                        )

            elif cmd == "status":
                status = await db.get_status()
                print(
                    f"Pending: {status['pending']}, "
                    f"Processing: {status['processing']}, "
                    f"Done: {status['done']}"
                )
                print(f"Active background tasks: {len(crawler._background_tasks)}")

            elif cmd == "resume":
                await db.resume_processing(crawler.db_lock)
                max_depth = int(await db.get_setting("max_depth") or "2")
                crawler.resume_in_background(max_depth)
                print("Resumed crawl.")

            elif cmd == "exit":
                break

            else:
                print("Unknown command or missing arguments.")
    finally:
        crawler.stop()
        await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
