import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("API_KEY")

genai.configure(api_key=api_key)
model = genai.GenerativeModel("gemini-3.1-pro")

def run_agent(system_prompt, user_message):
    # Chain of thought kullanımını teşvik etmek için prompt yapısını yapılandırıyoruz
    full_prompt = f"{system_prompt}\n\nUSER REQUEST:\n{user_message}"
    response = model.generate_content(full_prompt)
    return response.text

def db_architect_agent(requirements):
    system_prompt = """You are an expert AI Database Architect agent.
Your task is to design a local SQLite database infrastructure (`database.py`) for a concurrent web crawler and search engine.

Please walk through your thought process step-by-step (Chain of Thought):
1. Analyze Requirements: Determine what data needs to be stored (URLs, content, depth, visited status).
2. Concurrency Solution: Think about configurations required for SQLite to handle concurrent reads (search) and writes (indexing) simultaneously (e.g., WAL mode).
3. Schema Design: Define tables, indexes, and columns.
4. CRUD Operations: Create signatures and drafts for the essential basic functions (insert, update, query).
5. Code Generation: As a result of your analysis, write clean, modular, and well-commented Python code. Remember to stay within your boundaries and that you are solely responsible for `database.py`."""
    return run_agent(system_prompt, requirements)

def crawler_expert_agent(requirements):
    system_prompt = """You are an expert AI Crawler Developer (Crawler Expert) agent.
Your task is to design a concurrent, depth-controlled, and rate-limited (back pressure) web indexer (`indexer.py`).

Please walk through your thought process step-by-step (Chain of Thought):
1. Analysis: Plan how to crawl pages starting from the 'origin' URL up to depth 'k'.
2. Concurrency and Asynchronous Structure: Think about how to utilize Python's native async features (asyncio, aiohttp/urllib, etc.).
3. Control Mechanisms: Determine how to prevent re-crawling the same URL (visited tracker), manage the queue (bounded queue), and set worker limits.
4. Fault Tolerance: Devise a logic to save the queue state to the DB so the system can resume if it crashes.
5. Code Generation: Prepare robust and fault-tolerant Python code (`indexer.py`) that strictly follows your thought process steps."""
    return run_agent(system_prompt, requirements)

def search_specialist_agent(requirements):
    system_prompt = """You are an experienced AI Search Specialist agent.
Your task is to create a non-blocking search engine infrastructure (`search.py`) that will concurrently search through the pages saved in the database.

Please walk through your thought process step-by-step (Chain of Thought):
1. Data Reading Logic: Design how search operations will be executed without getting blocked by read/write locks while the Indexer is running and writing to the database in the background.
2. Query Structure: Think about the SQL queries and keyword matching algorithms (title/body) needed to provide the `(relevant_url, origin_url, depth)` return format.
3. Performance: Evaluate potential optimizations for fast searching in SQLite.
4. Code Generation: Create simple and effective `search.py` code to manage the search operations."""
    return run_agent(system_prompt, requirements)

def cli_integration_master_agent(requirements):
    system_prompt = """You are an AI CLI and System Integration Master agent.
Your task is to create the `main.py` file, which brings together the modules written by the DB Architect, Crawler Expert, and Search Specialist, and provides the user interaction.

Please walk through your thought process step-by-step (Chain of Thought):
1. Module Integration: Plan how `database.py`, `indexer.py`, and `search.py` will be imported and connected.
2. Event Loop & Threading Management: Determine how the crawler running in the background and the CLI interface (and search commands) running in the foreground will operate simultaneously without conflicts.
3. CLI Design: Design a command-line interface that can parse and process 'index <url> <depth>', 'search <keyword>', and 'status' commands.
4. Code Generation: Write the complete `main.py` code that orchestrates all the pieces."""
    return run_agent(system_prompt, requirements)

def get_example_code():
    example_dir = os.getenv("EXAMPLE_CRAWLER_DIR")
    if not example_dir or not os.path.exists(example_dir):
        print(f"BİLGİ: Örnek crawler dizini bulunamadı: {example_dir}")
        return ""
    
    example_files = ["database.py", "crawler_service.py", "main.py", "api.py"]
    example_context = "\n\n--- EXAMPLE CRAWLER CODE FOR INSPIRATION ---\n"
    
    for filename in example_files:
        filepath = os.path.join(example_dir, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    example_context += f"\n\n# === {filename} ===\n{content}\n"
            except Exception as e:
                print(f"Error reading {filename}: {e}")
                
    return example_context

def orchestrator():
    print("🚀 Starting Multi-Agent Web Crawler Development Process...\n")
    
    project_prd = "A mini web crawler and search engine powered by SQLite, capable of asynchronous and concurrent execution. Heavy third-party libraries (like Celery, Redis) are strictly forbidden."
    
    # Append the example code to the PRD
    project_prd += get_example_code()
    
    print("🛠️ 1. Database Architect is working...")
    db_code = db_architect_agent(project_prd)
    print("✅ Database architecture created.\n")
    
    print("🕸️ 2. Crawler Expert is working...")
    crawler_code = crawler_expert_agent(project_prd)
    print("✅ Crawler module created.\n")
    
    print("🔍 3. Search Specialist is working...")
    search_code = search_specialist_agent(project_prd)
    print("✅ Search module created.\n")
    
    print("💻 4. CLI & Integration Master is working...")
    cli_code = cli_integration_master_agent(project_prd)
    print("✅ Integration module created.\n")
    
    # In a real workflow, these codes step would be saved to respective python files (database.py, etc.)
    return {
        "database.py": db_code,
        "indexer.py": crawler_code,
        "search.py": search_code,
        "main.py": cli_code
    }

if __name__ == "__main__":
    # Test run (Uncomment orchestrator to run)
    # result_codes = orchestrator()
    # print(result_codes)
    print("Agents have been updated to use English prompts with Chain of Thought methodology as per product_prd.md.")