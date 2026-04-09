import os
from google import genai
from dotenv import load_dotenv

def test_gemini_api():
    print("API Anahtari kontrol ediliyor...")
    
    # .env dosyasini yukle
    load_dotenv()
    api_key = os.getenv("API_KEY")
    
    if not api_key:
        print("[HATA] '.env' dosyasinda API_KEY bulunamadi!")
        return

    try:
        # API'yi yapilandir
        client = genai.Client(api_key=api_key)
        
        # Basit bir model testi
        print("API baglantisi kuruluyor, test mesaji gonderiliyor...")
        
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-preview", 
            contents="Merhaba! Lutfen API testinin basarili oldugunu soyleyen cok kisa bir mesaj yaz."
        )
        
        print("\n[BASARILI] API baglantiniz sorunsuz calisiyor.")
        print("-" * 40)
        print("Yapay Zeka Yaniti:")
        print(response.text)
        print("-" * 40)
        
    except Exception as e:
        print("\n[BASARISIZ] API baglantisi kurulurken bir hata olustu:")
        print(str(e))

if __name__ == "__main__":
    test_gemini_api()
