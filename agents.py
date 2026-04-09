import os
import ast
from google import genai
from dotenv import load_dotenv
from datetime import datetime

from groq import Groq

load_dotenv()

api_key = os.getenv("API_KEY")
client = genai.Client(api_key=api_key)

groq_key = os.getenv("GROQ_KEY")
groq_client = Groq(api_key=groq_key) if groq_key else None

def run_agent(system_prompt, user_message, agent_name="Agent", provider="gemini", model=None):
    full_prompt = f"{system_prompt}\n\nUSER REQUEST:\n{user_message}"
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if provider == "groq" and groq_client:
        try:
            response = groq_client.chat.completions.create(
                messages=[
                    {"role": "user", "content": full_prompt}
                ],
                model="openai/gpt-oss-120b",
            )
            text_response = response.choices[0].message.content
            api_label = "GROQ"
        except Exception as e:
            text_response = f"Error calling Groq API: {e}"
            api_label = "GROQ_ERROR"
    else:
        actual_model = model if model else "gemini-3.1-flash-lite-preview"
        response = client.models.generate_content(
            model=actual_model,
            contents=full_prompt
        )
        text_response = response.text
        api_label = f"GEMINI ({actual_model})"
        
    log_text = f"\n{'='*50}\n[TIMESTAMP: {timestamp} | API: {api_label}]\n{'='*50}\n{text_response}\n"
    os.makedirs("generated_code", exist_ok=True)
    
    with open(f"generated_code/{agent_name}_log.txt", "a", encoding="utf-8") as f:
        f.write(log_text)
        
    return text_response

def db_architect_agent(requirements):
    system_prompt = """You are an expert AI Database Architect agent.
Your task is to design a local SQLite database infrastructure (`database.py`) for a concurrent web crawler and search engine.

Please walk through your thought process step-by-step (Chain of Thought):
1. Analyze Requirements: Determine what data needs to be stored (URLs, content, depth, visited status).
2. Concurrency Solution: Think about configurations required for SQLite to handle concurrent reads (search) and writes (indexing) simultaneously (e.g., WAL mode).
3. Schema Design: Define tables, indexes, and columns.
4. CRUD Operations: Create signatures and drafts for the essential basic functions (insert, update, query).
5. Code Generation: As a result of your analysis, write clean, modular, and well-commented Python code. Remember to stay within your boundaries and that you are solely responsible for `database.py`."""
    return run_agent(system_prompt, requirements, agent_name="DB_Architect")

def crawler_expert_agent(requirements):
    system_prompt = """You are an expert AI Crawler Developer (Crawler Expert) agent.
Your task is to design a concurrent, depth-controlled, and rate-limited (back pressure) web indexer (`indexer.py`).

Please walk through your thought process step-by-step (Chain of Thought):
1. Analysis: Plan how to crawl pages starting from the 'origin' URL up to depth 'k'.
2. Concurrency and Asynchronous Structure: Think about how to utilize Python's native async features (asyncio, aiohttp/urllib, etc.).
3. Control Mechanisms: Determine how to prevent re-crawling the same URL (visited tracker), manage the queue (bounded queue), and set worker limits.
4. Fault Tolerance: Devise a logic to save the queue state to the DB so the system can resume if it crashes.
5. Code Generation: Prepare robust and fault-tolerant Python code (`indexer.py`) that strictly follows your thought process steps."""
    return run_agent(system_prompt, requirements, agent_name="Crawler_Expert")

def search_specialist_agent(requirements):
    system_prompt = """You are an experienced AI Search Specialist agent.
Your task is to create a non-blocking search engine infrastructure (`search.py`) that will concurrently search through the pages saved in the database.

Please walk through your thought process step-by-step (Chain of Thought):
1. Data Reading Logic: Design how search operations will be executed without getting blocked by read/write locks while the Indexer is running and writing to the database in the background.
2. Query Structure: Think about the SQL queries and keyword matching algorithms (title/body) needed to provide the `(relevant_url, origin_url, depth)` return format.
3. Performance: Evaluate potential optimizations for fast searching in SQLite.
4. Code Generation: Create simple and effective `search.py` code to manage the search operations."""
    return run_agent(system_prompt, requirements, agent_name="Search_Specialist", model="gemini-3.1-flash-lite-preview")

def cli_integration_master_agent(requirements, generated_context):
    system_prompt = f"""You are an AI CLI and System Integration Master agent.
Your task is to create the `main.py` file, which brings together the modules written by the DB Architect, Crawler Expert, and Search Specialist, and provides the user interaction.

CRITICAL: Here is the actual code for the modules you must integrate:
{generated_context}

Please walk through your thought process step-by-step (Chain of Thought):
1. Module Analysis: Read the code above for `indexer.py` and `database.py`. Look EXACTLY at what classes and methods are defined (e.g. `Indexer` and its `start()` method). Do NOT guess or hallucinate methods (like `start_background_loop`) that don't exist!
2. Event Loop & Threading Management: Determine how to run the asynchronous crawler (using its exact methods) in a background thread or task so the CLI remains responsive.
3. CLI Design: Design a rich, interactive, and BEAUTIFUL command-line interface. Use standard ANSI escape codes for vibrant colors (blue, green, red, yellow). Add an impressive ASCII art banner at startup. Display search results in a neatly formatted ASCII table. Ensure the prompt (`Crawler (User) >`) is distinct and visually appealing. Emphasize a premium UX even in the terminal!
4. Code Generation: Write the complete `main.py` code that orchestrates the supplied code."""
    return run_agent(system_prompt, requirements, agent_name="CLI_Master")

def clean_code(text):
    lines = text.split('\n')
    extracted = []
    inside_code = False
    
    if '```' in text:
        for line in lines:
            if line.startswith('```py') or line.startswith('```python'):
                inside_code = True
                continue
            elif line.startswith('```') and inside_code:
                inside_code = False
                continue
            if inside_code:
                extracted.append(line)
        return '\n'.join(extracted)
    return text

def get_exports(code_text):
    try:
        tree = ast.parse(clean_code(code_text))
        exports = [node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        return ", ".join(exports) if exports else "None"
    except Exception as e:
        return f"Syntax Error: {e}"

def qa_test_manager_agent(requirements, codes):
    system_prompt = """You are Agent 5 (QA/Test Manager), an EXTREMELY STRICT, detail-oriented, and unyielding Quality Assurance Manager.
Your MANDATE is to aggressively review the generated code from all agents (DB Architect, Crawler Expert, Search Specialist, CLI Master) against the PRD.
DO NOT BE LENIENT. If there is even a minor logical flaw, syntax error, missing import, potential race condition, or slight deviation from the PRD (such as ignoring WAL mode, poor async handling, or using forbidden libraries), YOU MUST REJECT IT IMMEDIATELY.

You have absolute authority to reject the code and force the responsible agent to rewrite it.
If there is an issue with ANY module, you must output EXACTLY one of the following commands at the very end of your response to demand a fix:
- FIX_DB: <strict and detailed feedback pointing out the exact flaw in database.py>
- FIX_CRAWLER: <strict and detailed feedback pointing out the exact flaw in indexer.py>
- FIX_SEARCH: <strict and detailed feedback pointing out the exact flaw in search.py>
- FIX_CLI: <strict and detailed feedback pointing out the exact flaw in main.py>

ONLY if absolutely EVERY snippet of code is production-ready, flawlessly integrated, properly asynchronous, and completely bug-free, output:
- ALL_PASSED
Next, write a clear "QA Final Report" summarizing your strict review phase, testing strategy, and final results.
Finally, write the complete code for `test_main.py` which will thoroughly test the system.

Please walk through your thought process step-by-step with extreme skepticism:
1. Deeply inspect `database.py` (Must have WAL mode, thread-safe connections, proper schema, robust Error handling).
2. Deeply inspect `indexer.py` (Must use asyncio correctly, bounded queue, visited set, proper rate limiting, NO Celery/Redis).
3. Deeply inspect `search.py` (Must support non-blocking reads during background indexing writes).
4. Deeply inspect `main.py` (Must handle the background event loop cleanly while accepting CLI inputs).
5. VERIFY EXPORTS & IMPORTS: Cross-reference what each file imports against the actual EXPORTS LIST provided below. If a file tries to import a function from another module that does NOT exist in its exports list, YOU MUST IMMEDIATELY REJECT (e.g. FIX_CLI if main.py does it).
6. VERDICT: Execute your final decision (FIX_XXX or ALL_PASSED & write test code)."""
    
    exports_info = "--- EXPORTED FUNCTIONS & CLASSES DIRECTORY ---\n"
    for fname, code in codes.items():
        exports_info += f"Module '{fname}' actually exports: {get_exports(code)}\n"

    codes_context = "\n".join([f"=== {filename} ===\n{code}" for filename, code in codes.items()])
    full_user_request = f"PRD:\n{requirements}\n\n{exports_info}\n\nGENERATED CODES TO REVIEW:\n{codes_context}"
    return run_agent(system_prompt, full_user_request, agent_name="QA_Manager")

def get_example_code():
    filepath = "crawler_project_architecture.md"
    if not os.path.exists(filepath):
        print(f"BİLGİ: Örnek mimari dosyası bulunamadı: {filepath}")
        return ""
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            return f"\n\n--- EXAMPLE CRAWLER ARCHITECTURE FOR INSPIRATION (NOT FINAL) ---\n{content}\n"
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return ""

def orchestrator():
    print("🚀 Starting Multi-Agent Web Crawler Development Process...\n")
    
    clean_prd = "A mini web crawler and search engine powered by SQLite, capable of asynchronous and concurrent execution. Heavy third-party libraries (like Celery, Redis) are strictly forbidden."
    
    # Append the example code to the PRD
    project_prd = clean_prd + get_example_code()
    
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
    gen_context = f"=== database.py ===\n{db_code}\n=== indexer.py ===\n{crawler_code}\n=== search.py ===\n{search_code}"
    cli_code = cli_integration_master_agent(project_prd, gen_context)
    print("✅ Integration module created.\n")
    
    codes = {
        "database.py": db_code,
        "indexer.py": crawler_code,
        "search.py": search_code,
        "main.py": cli_code
    }
    
    print("🕵️ 5. QA/Test Manager is stepping in to review the system...")
    max_retries = 3
    for attempt in range(max_retries):
        print(f"   [QA Iteration {attempt + 1}] Reviewing generated codes...")
        qa_response = qa_test_manager_agent(clean_prd, codes)
        
        if "FIX_DB:" in qa_response:
            print("   ❌ QA found issues in database.py. Mandating DB Architect to fix it...")
            feedback = qa_response.split("FIX_DB:")[1]
            codes["database.py"] = db_architect_agent(project_prd + f"\n\nQA FEEDBACK TO FIX:\n{feedback}")
        elif "FIX_CRAWLER:" in qa_response:
            print("   ❌ QA found issues in indexer.py. Mandating Crawler Expert to fix it...")
            feedback = qa_response.split("FIX_CRAWLER:")[1]
            codes["indexer.py"] = crawler_expert_agent(project_prd + f"\n\nQA FEEDBACK TO FIX:\n{feedback}")
        elif "FIX_SEARCH:" in qa_response:
            print("   ❌ QA found issues in search.py. Mandating Search Specialist to fix it...")
            feedback = qa_response.split("FIX_SEARCH:")[1]
            codes["search.py"] = search_specialist_agent(project_prd + f"\n\nQA FEEDBACK TO FIX:\n{feedback}")
        elif "FIX_CLI:" in qa_response:
            print("   ❌ QA found issues in main.py. Mandating CLI Master to fix it...")
            feedback = qa_response.split("FIX_CLI:")[1]
            codes["main.py"] = cli_integration_master_agent(project_prd + f"\n\nQA FEEDBACK TO FIX:\n{feedback}")
        else:
            print("   ✅ QA approved all modules!\n")
            print("--- QA FINAL REPORT ---")
            print(qa_response)
            print("-----------------------\n")
            codes["test_main.py"] = qa_response
            codes["qa_report.md"] = qa_response
            break
    else:
        print("   ⚠️ QA iteration limit reached. Saving current state with QA feedback as test file.")
        print("--- QA FINAL REPORT (FAILED/TIMEOUT) ---")
        print(qa_response)
        print("----------------------------------------\n")
        codes["test_main.py"] = qa_response
        codes["qa_report.md"] = qa_response

    # Return the final codes for saving
    return codes

if __name__ == "__main__":
    result_codes = orchestrator()
    
    output_dir = "generated_code"
    os.makedirs(output_dir, exist_ok=True)
    
    print("\n💾 Kodlar dosyalara kaydediliyor...\n")
    for filename, code_content in result_codes.items():
        file_path = os.path.join(output_dir, filename)
        
        if filename.endswith(".md"):
            cleaned_content = code_content
        else:
            cleaned_content = clean_code(code_content)
            
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(cleaned_content)
        print(f"✅ Olusturuldu: {file_path}")
        
    print("\n🚀 Tum islem basariyla tamamlandi! Uretilen dosyalari 'generated_code' klasorunde bulabilirsiniz.")