"""
manager.py — Kullanıcıyla Konuşan Orkestratör

Kullanıcıyla terminal üzerinde doğal dilde konuşur.
Ne yapılmak istendiğini anlar, hangi agent(ların) çalışacağına karar verir,
crew'u dinamik olarak o şekilde kurar ve tetikler.
"""

import os
import re
from crewai import Crew, Process
from crew import (
    architect, db_engineer, crawler_dev, cli_dev, qa,
    make_architect_task, make_db_task, make_crawler_task,
    make_cli_task, make_qa_task,
)

# Sabit pipeline sırası — task'lar ve agent'lar hep bu sıraya göre kurulur.
PIPELINE_ORDER = ["architect", "db", "crawler", "cli", "qa"]

AGENT_MAP = {
    "architect": architect,
    "db":        db_engineer,
    "crawler":   crawler_dev,
    "cli":       cli_dev,
    "qa":        qa,
}

TASK_BUILDER_MAP = {
    "architect": make_architect_task,
    "db":        make_db_task,
    "crawler":   make_crawler_task,
    "cli":       make_cli_task,
    "qa":        make_qa_task,
}

# ── LLM Manager Routing ────────────────────────────────────────

def analyze_with_llm(user_message: str) -> tuple[str, list, dict]:
    """
    Kullanıcı isteğini LLM ile analiz eder, kullanıcının ne demek istediğini (understanding),
    çalıştırılacak ajan rotasını (route)
    ve her biri için özelleştirilmiş açıklamaları (custom_prompts) belirler.
    """
    import json
    import litellm
    from crew import ACTIVE_MODEL_NAME, ACTIVE_API_KEY
    
    sys_prompt = '''Sen, bir Multi-Agent (Çoklu Ajan) sisteminin Baş Mühendisi ve karar alıcısısın (Manager).
Ekibinde şu ajanlar var:
1) "architect": Projenin sistem mimarisini ve arayüz/fonksiyon imzalarını tanımlar.
2) "db": database.py'yi yazar. (SQLite WAL, executemany vb.)
3) "crawler": crawler_service.py ve aiohttp asenkron mekanizmasını yazar.
4) "cli": main.py'deki komut satırı arayüzünü ve çalıştırıcı döngüyü yazar.
5) "qa": Önceki ajanların ürettiği kodu inceler ve rapor çıkarır. QA HER ZAMAN ÇALIŞMALIDIR.

Kullanıcının isteğini analiz et ve SADECE etkilenmesi gereken ajanları seç (ancak 'qa' her zaman seçilmelidir). Gerekli değilse hepsini çalıştırma.
Seçtiğin HER BİR ajan için, o ajana özel "Ne yapması gerektiğine dair" emirler/talimatlar türet. Bu emirler ajana özel, teknik ve net olmalı.
Asla genel yorum yapma, direkt sorunu çözmeye yönelik talimatlar ver.

LÜTFEN SADECE AŞAĞIDAKİ JSON FORMATINDA YANIT VER, başka hiçbir metin veya markdown ekleme:
{
  "understanding": "Kullanıcı crawler'ın depth=1 iken fazla derine indiğini söylüyor. Bunun detaylıca incelenip çözülmesini istiyor.",
  "route": ["crawler", "cli", "qa"],
  "custom_prompts": {
    "crawler": "Kullanıcı crawler'ın depth=1 iken fazla derine indiğini söylüyor. _worker fonksiyonunda depth <= max_depth şartını düzelt ve loop mantığını revize et.",
    "cli": "Kullanıcının aradığı argüman desteğini komut dinleyicisine ekle.",
    "qa": "Özellikle crawler_service içindeki max_depth mantığının doğru uygulanıp uygulanmadığını sıkı bir şekilde denetle."
  }
}'''

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": f"Kullanıcı İsteği: {user_message}"}
    ]

    print(f"🧠 [MANAGER] İstek analiz ediliyor (Model: {ACTIVE_MODEL_NAME})...")
    
    try:
        response = litellm.completion(
            model=ACTIVE_MODEL_NAME,
            api_key=ACTIVE_API_KEY,
            messages=messages,
            temperature=0.1
        )
        content = response.choices[0].message.content.strip()
        
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```\s*', '', content)
        
        data = json.loads(content)
        understanding = data.get("understanding", "Kullanıcının isteği analiz edildi.")
        route = data.get("route", ["architect", "db", "crawler", "cli", "qa"])
        prompts = data.get("custom_prompts", {})
        
        if "qa" not in route:
            route.append("qa")
            
        # Önceliği PIPELINE_ORDER'a göre ayarla
        route = [r for r in PIPELINE_ORDER if r in route]
        
        return understanding, route, prompts
        
    except Exception as e:
        print(f"⚠️ [MANAGER] LLM Analiz hatası: {e}\nVarsayılan tüm pipeline çalıştırılacak.")
        return "Analiz başarısız oldu, tüm pipeline çalıştırılıyor.", PIPELINE_ORDER[:], {}

# ── Task Zinciri ──────────────────────────────────────────────

def build_tasks(route: list, custom_prompts: dict, original_request: str) -> list:
    """
    Seçilen agent'lar için task'ları PIPELINE_ORDER sırasına göre kurar.
    LLM tarafından üretilmiş özel promptları ajanlara enjekte eder.
    """
    tasks = []
    prev = None
    for key in PIPELINE_ORDER:
        if key not in route:
            continue
        context = [prev] if prev else []
        instruction = custom_prompts.get(key, original_request)
        task = TASK_BUILDER_MAP[key](user_request=instruction, context=context)
        tasks.append(task)
        prev = task
    return tasks

# ── Kod Temizleme ─────────────────────────────────────────────

def extract_code_block(text: str, lang: str = "python") -> str:
    """
    Verilen lang'a göre ilk markdown code bloğunu çıkarır.
    Bulamazsa ham metni döner.
    """
    pattern = rf"```{lang}\s*\n(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Dil etiketi olmayan genel ``` bloğu dene
    match = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    return text.strip()

def extract_requirements(text: str) -> str | None:
    """
    CLI agent çıktısından requirements.txt içeriğini ayıklar.
    'aiohttp>=3.9.0' içeren satırı bulur.
    """
    for line in text.split("\n"):
        if "aiohttp" in line and ">=" in line:
            return line.strip()
    return "aiohttp>=3.9.0"  # bulamazsa güvenli varsayılan

# ── Dosya Kaydetme ────────────────────────────────────────────

def save_outputs(tasks: list):
    """
    Her task'ın çıktısını ilgili dosyaya kaydeder.
    task.output.raw → ham LLM çıktısı (str() yerine güvenli).
    """
    os.makedirs("generated_code", exist_ok=True)
    print("\nDosyalar kaydediliyor (generated_code/)...")

    for task in tasks:
        # TaskOutput objesinden ham metni al
        raw = task.output.raw if hasattr(task.output, "raw") else str(task.output)
        role = task.agent.role

        if role == "Sistem Mimarı":
            path = "generated_code/architecture.md"
            with open(path, "w", encoding="utf-8") as f:
                f.write(raw)
            print(f"  [OK] architecture.md")

        elif role == "Veritabanı Mühendisi":
            path = "generated_code/database.py"
            with open(path, "w", encoding="utf-8") as f:
                f.write(extract_code_block(raw, "python"))
            print(f"  [OK] database.py")

        elif role == "Async Sistem Geliştirici":
            path = "generated_code/crawler_service.py"
            with open(path, "w", encoding="utf-8") as f:
                f.write(extract_code_block(raw, "python"))
            print(f"  [OK] crawler_service.py")

        elif role == "CLI ve Entegrasyon Mühendisi":
            # main.py — python bloğunu al
            path = "generated_code/main.py"
            with open(path, "w", encoding="utf-8") as f:
                f.write(extract_code_block(raw, "python"))
            print(f"  [OK] main.py")

            # requirements.txt — ayrı olarak ayıkla
            req_path = "generated_code/requirements.txt"
            with open(req_path, "w", encoding="utf-8") as f:
                f.write(extract_requirements(raw) + "\n")
            print(f"  [OK] requirements.txt")

        elif role == "QA Mühendisi":
            path = "generated_code/qa_report.md"
            with open(path, "w", encoding="utf-8") as f:
                f.write(raw)
            print(f"  [OK] qa_report.md")

# ── Ana Döngü ─────────────────────────────────────────────────

import argparse
import sys

def run_manager(request: str):
    """Tek bir prompt için süreci işletir."""
    understanding, route, custom_prompts = analyze_with_llm(request)
    
    print("\n" + "="*50)
    print(f"🧐 [MANAGER] Sorumdan Anladığı:\n ➡️  {understanding}\n")
    print(f"🚀 [MANAGER] Akıllı Rotalama (Çağrılan Ajanlar ve Verilen Komutlar):")
    for agent_key in route:
        instruction = custom_prompts.get(agent_key, request)
        print(f"\n 🔹 {agent_key.upper()} AJANI:")
        print(f"    Söylenen: {instruction}")
    print("\n" + "="*50 + "\n")

    tasks = build_tasks(route, custom_prompts, request)
    active_agents = [AGENT_MAP[key] for key in PIPELINE_ORDER if key in route]

    crew = Crew(
        agents=active_agents,
        tasks=tasks,
        process=Process.sequential,
        verbose=False,
    )

    print(f"⏳ [MANAGER] {len(tasks)} görev sırasıyla çalıştırılıyor...\n")
    crew.kickoff()
    
    print("\n" + "="*50)
    print("🎯 [MANAGER] Ajanlardan Gelen Cevaplar / Çıktılar:")
    for task in tasks:
        role = task.agent.role
        raw_output = task.output.raw if hasattr(task.output, "raw") else str(task.output)
        preview = raw_output.replace('\n', ' ')[:100] + "..." if len(raw_output) > 100 else raw_output.replace('\n', ' ')
        print(f"\n 🔹 {role} Cevabı:\n    {preview}")
    print("="*50)

    print("\n💾 [MANAGER] Görevler bitti, çıktılar diske yazılıyor...")
    save_outputs(tasks)

    print("\n✅ [MANAGER] BÜTÜN İŞLEMLER BAŞARIYLA TAMAMLANDI!")

def interactive_mode():
    """Etkileşimli terminal döngüsü."""
    print("\n" + "#" * 70)
    print("🤖 WEB CRAWLER BUILDER -- YAPAY ZEKA GELİŞTİRME ASİSTANI 🤖")
    print("#" * 70)
    print(" Sistem mimariyi, veritabanını, backend kodlarını ve testleri yönetir.")
    print(" İstediğiniz değişikliği tek cümleyle söylemeniz yeterlidir.")
    print(" (Çıkmak için: 'exit', 'cikis', veya 'q' yazın)\n")

    while True:
        try:
            user_input = input("🗣️ Sen: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Görüşmek üzere!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "cikis", "quit", "q"):
            print("\n👋 Görüşmek üzere!")
            break

        run_manager(user_input)
        print("\n" + "-" * 70)
        print("❓ Başka bir isteğiniz var mı?")

def main():
    parser = argparse.ArgumentParser(
        description="Multi-Agent AI Manager for Web Crawler",
        epilog="Kullanım: 'python manager.py' (Etkileşimli mod) VEYA 'python manager.py \"veritabanını düzelt\"' (Tek seferlik komut)"
    )
    
    # Tüm argüman stringlerini birleştirip tek bir prompt elde edeceğiz.
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Yapay zeka takımına verilecek geliştirme veya düzeltme talimatı."
    )
    
    args = parser.parse_args()
    prompt_text = " ".join(args.prompt).strip()
    
    if prompt_text:
        # Eğer dışarıdan argüman verilmişse sadece onu işleyip çıkış yapar
        run_manager(prompt_text)
    else:
        # Kod normal çağırılmışsa sürekli prompt'ta bekler
        interactive_mode()

if __name__ == "__main__":
    main()