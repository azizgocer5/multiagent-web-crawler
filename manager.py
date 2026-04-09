import os
import sys
from agents import run_agent, clean_code, db_architect_agent, crawler_expert_agent, search_specialist_agent, cli_integration_master_agent

def interactive_manager():
    print("="*60)
    print("🎩 KİŞİSEL YAPAY ZEKA YÖNETİCİSİ (INTERACTIVE MANAGER) BAŞLADI")
    print("="*60)
    print("Bütün projeyi baştan üretmek yerine, sadece istediğiniz parçayı")
    print("hedef alarak ilgili yazılımcı ajana düzelttiririm.\n")
    
    output_dir = "generated_code"
    
    # 1. Mevcut kodları diskten yükleyelim
    codes = {}
    expected_files = ["database.py", "indexer.py", "search.py", "main.py"]
    
    print("📂 Mevcut kodlar yükleniyor...")
    for fname in expected_files:
        path = os.path.join(output_dir, fname)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                codes[fname] = f.read()
        else:
            print(f"⚠️ {fname} bulunamadı. Lütfen önce 'python agents.py' ile sistemi bir kez oluşturun.")
            return

    print("✅ Tüm dosyalar hafızada. \nNe gibi bir değişiklik istersiniz? (Çıkmak için: exit)")
    
    while True:
        feedback = input("\n👤 Kurucu (Siz) > ").strip()
        if not feedback:
            continue
        if feedback.lower() in ["exit", "q", "quit"]:
            print("Kapatılıyor...")
            break
            
        print("\n🤖 Yönetici Ajan: Talebinizi inceliyorum, hedef modülü bulacağım...")
        
        # 2. Hangi dosyanın değişeceğini karar veren Karar Ajanı
        system_prompt = """You are the Project Manager Agent of a Multi-Agent AI System.
The user has provided a feedback or change request for their python web crawler project.
Analyze the request and decide EXACTLY which file needs to be modified.
Options: [database.py, indexer.py, search.py, main.py]

You must output EXACTLY the filename that needs to change, followed by a colon, and then detailed instructions for the specific developer module.
Example 1: 'main.py: The user wants you to make the CLI table green.'
Example 2: 'indexer.py: The user wants to change thread count to 20.'

If multiple files need changes, pick the most relevant one first."""
        
        codes_context = "\n".join([f"=== {k} ===\n{v}" for k, v in codes.items()])
        user_message = f"USER REQUEST: {feedback}\n\nCURRENT FILES:\n{codes_context}"
        
        manager_decision = run_agent(system_prompt, user_message, agent_name="Interactive_Manager")
        print(f"🎯 Hedef Belirlendi: {manager_decision}\n")
        
        target_file = None
        instruction = ""
        
        # 3. İlgili Ajana Yönlendirme
        if "database.py:" in manager_decision:
            target_file = "database.py"
            instruction = manager_decision.split("database.py:")[1]
            print("🛠️ DB Architect çalışıyor, veritabanını güncelliyor...")
            codes[target_file] = clean_code(db_architect_agent(f"Modify database.py based on user feedback:\n{instruction}\n\nCurrent code:\n{codes[target_file]}"))
            
        elif "indexer.py:" in manager_decision:
            target_file = "indexer.py"
            instruction = manager_decision.split("indexer.py:")[1]
            print("🕸️ Crawler Expert çalışıyor, tarayıcıyı güncelliyor...")
            codes[target_file] = clean_code(crawler_expert_agent(f"Modify indexer.py based on user feedback:\n{instruction}\n\nCurrent code:\n{codes[target_file]}"))
            
        elif "search.py:" in manager_decision:
            target_file = "search.py"
            instruction = manager_decision.split("search.py:")[1]
            print("🔍 Search Specialist çalışıyor, arama motorunu güncelliyor...")
            codes[target_file] = clean_code(search_specialist_agent(f"Modify search.py based on user feedback:\n{instruction}\n\nCurrent code:\n{codes[target_file]}"))
            
        elif "main.py:" in manager_decision:
            target_file = "main.py"
            instruction = manager_decision.split("main.py:")[1]
            gen_context = f"=== database.py ===\n{codes['database.py']}\n=== indexer.py ===\n{codes['indexer.py']}\n=== search.py ===\n{codes['search.py']}"
            print("💻 CLI Master çalışıyor, arayüzü güncelliyor...")
            codes[target_file] = clean_code(cli_integration_master_agent(f"Modify main.py based on user feedback:\n{instruction}\n\nCurrent main.py code:\n{codes[target_file]}", gen_context))
            
        else:
            print("❌ Yönetici Agent hedef dosyayı anlayamadı. Lütfen daha belirgin yazın.")
            continue
            
        # 4. Dosyayı diske yazma
        file_path = os.path.join(output_dir, target_file)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(codes[target_file])
            
        print(f"✅ Bitti! {target_file} dosyası başarıyla yeniden yazıldı ve kaydedildi.")

if __name__ == "__main__":
    interactive_manager()
