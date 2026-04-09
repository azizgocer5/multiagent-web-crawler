import asyncio
import sys
import logging
from database import Database
from indexer import Crawler
from search import SearchEngine

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_menu():
    menu = f"""
{Colors.BLUE}
   ___               _           _     ___               _           
  / __|_ _ __ _ __ _| |___ _ _  | |   / __|___ _ _  _ __| |___ _ _ 
 | (__| '_/ _` / _` | / -_) '_| | |__| (__/ _ \ ' \| '_ \ / -_) '_|
  \___|_| \__,_\__,_|_\___|_|   |____|\___\___/_||_| .__/_\___|_|  
                                                   |_|             
{Colors.YELLOW}>> Main Menu{Colors.END}
{Colors.GREEN}1.{Colors.END} Start Crawler (Seed URL + Max Depth)
{Colors.GREEN}2.{Colors.END} Search Indexed Pages
{Colors.GREEN}3.{Colors.END} Show Status
{Colors.GREEN}4.{Colors.END} Exit
"""
    print(menu)

async def run_cli():
    db = Database("crawler.db")
    await db.initialize()
    search_engine = SearchEngine("crawler.db")
    
    while True:
        print_menu()
        choice = await asyncio.get_event_loop().run_in_executor(None, input, f"\n{Colors.BOLD}Crawler (User) > {Colors.END}")
        
        if choice == '1':
            url = await asyncio.get_event_loop().run_in_executor(None, input, "Enter seed URL: ")
            depth = await asyncio.get_event_loop().run_in_executor(None, input, "Enter max depth (e.g. 2): ")
            
            print(f"{Colors.YELLOW}Starting crawler at {url} with depth {depth}...{Colors.END}")
            crawler = Crawler(db=db, max_depth=int(depth))
            asyncio.create_task(crawler.run(url))
            print(f"{Colors.GREEN}✔ Crawler task initiated in background.{Colors.END}")

        elif choice == '2':
            query = await asyncio.get_event_loop().run_in_executor(None, input, "Enter search query: ")
            print(f"{Colors.BLUE}Searching for '{query}'...{Colors.END}")
            results = await search_engine.search(query)
            
            if not results:
                print(f"{Colors.RED}No results found.{Colors.END}")
            else:
                print(f"\n{Colors.BOLD}{'URL':<50} | {'Title':<30}{Colors.END}")
                print("-" * 85)
                for r in results:
                    title = (r['title'] or "No Title")[:30]
                    print(f"{r['url'][:50]:<50} | {title:<30}")

        elif choice == '3':
            stats = await db.get_status_report()
            print(f"\n{Colors.HEADER}--- System Status ---{Colors.END}")
            print(f"{Colors.BLUE}Total Pages Indexed:{Colors.END} {stats['total_indexed']}")
            print(f"{Colors.BLUE}Queue Statistics:{Colors.END}")
            for state, count in stats['queue_stats'].items():
                print(f"  - {state.capitalize()}: {count}")

        elif choice == '4':
            print(f"{Colors.YELLOW}Shutting down...{Colors.END}")
            break
        else:
            print(f"{Colors.RED}Invalid selection. Please enter 1-4.{Colors.END}")

if __name__ == "__main__":
    try:
        asyncio.run(run_cli())
    except KeyboardInterrupt:
        sys.exit(0)