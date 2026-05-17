from langchain_core.tools import tool
import random
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

# ==========================================
# 1. BÖLÜM: ARAÇLAR (TOOLS)
# ==========================================

@tool
def mesafe_ve_sure_hesapla(kalkis_sehri: str, varis_sehri: str) -> str:
    """İki şehir arasındaki seyahat mesafesini ve tahmini varış süresini hesaplar."""
    mesafeler = {
        ("İstanbul", "Bursa"): "155 km, yaklaşık 2 saat",
        ("Ankara", "Bursa"): "385 km, yaklaşık 4.5 saat",
        ("İzmir", "Bursa"): "345 km, yaklaşık 4 saat"
    }
    rota = (kalkis_sehri, varis_sehri)
    ters_rota = (varis_sehri, kalkis_sehri)
    
    if rota in mesafeler: return mesafeler[rota]
    elif ters_rota in mesafeler: return mesafeler[ters_rota]
    return f"{kalkis_sehri} ve {varis_sehri} arası mesafe sistemde bulunamadı. Ortalama 300 km ve 3 saat varsayılabilir."

@tool
def hava_durumu_getir(sehir: str, tarih: str) -> str:
    """Belirtilen şehir ve tarih için hava durumu tahminini getirir."""
    durumlar = ["Güneşli, açık hava etkinlikleri için ideal", 
                "Yağmurlu, şemsiye gerekli ve kapalı mekanlar tercih edilmeli"]
    return f"{tarih} tarihinde {sehir} için hava durumu: {random.choice(durumlar)}."

@tool
def mekan_bul(sehir: str, butce_durumu: str) -> str:
    """Bütçe durumuna (düşük, orta, yüksek) göre mekan önerisi yapar."""
    if butce_durumu.lower() == "yüksek": return f"{sehir} merkezinde lüks restoran ve VIP tur."
    elif butce_durumu.lower() == "düşük": return f"{sehir} şehrinde tarihi esnaf lokantası ve ücretsiz park gezisi."
    return f"{sehir} şehrinde popüler bir orta sınıf kafe."

tools = [mesafe_ve_sure_hesapla, hava_durumu_getir, mekan_bul]

# ==========================================
# 2. BÖLÜM: BEYİN (MODERN LANGGRAPH MİMARİSİ)
# ==========================================

llm = ChatOllama(model="qwen2.5:7b", temperature=0)

# Hafıza yönetimini sağlayan nesne
memory = MemorySaver()

system_prompt = """Sen uzman bir sürpriz seyahat asistanısın. Kurallara kesinlikle uy:
1. İki şehir arasındaki mesafeyi hesapla.
2. Gidilecek tarihteki hava durumunu kontrol et.
3. Bütçeye uygun mekanlar seç.
4. Cevabını saat saat bir program şeklinde Türkçe sun."""

# ÇÖZÜM: state_modifier parametresini kaldırdık. 
# Ajanı sadece çekirdek bileşenleri (LLM, araçlar ve hafıza) ile kuruyoruz.
agent_executor = create_react_agent(
    llm, 
    tools, 
    checkpointer=memory
)

# ==========================================
# 3. BÖLÜM: ANA AKIŞ VE HAFIZA TESTİ
# ==========================================

if __name__ == "__main__":
    print("\n[!] Akıllı Seyahat Ajanı Başlatılıyor...\n")
    
    config = {"configurable": {"thread_id": "seyahat_projesi_1"}}
    
    # --- 1. ADIM: İLK PLANIN OLUŞTURULMASI ---
    kullanici_sorusu_1 = (
        "Hafta sonu arkadaşımla buluşacağım. Ben İstanbul'dan, o ise İzmir'den gelecek ve "
        "ortak nokta olarak Bursa'da buluşmaya karar verdik. Bütçemiz 'düşük'. "
        "23 Mayıs 2026 tarihi için bize hava durumuna da uygun sabahtan akşama bir plan yapar mısın?"
    )
    
    print(f"1. İSTEK: {kullanici_sorusu_1}\n" + "-"*50)
    
    # ÇÖZÜM: Sistem komutunu (system_prompt) grafın başlangıç durumuna (state) manuel olarak ekliyoruz.
    yanit_1 = agent_executor.invoke({
        "messages": [
            ("system", system_prompt),
            ("user", kullanici_sorusu_1)
        ]
    }, config)
    
    print("\n=== NİHAİ PLAN ===\n" + yanit_1["messages"][-1].content)
    
    print("\n" + "="*70 + "\n")
    
    # --- 2. ADIM: BAĞLAM (CONTEXT) VE HAFIZA TESTİ ---
    kullanici_sorusu_2 = "Peki bu plana akşam yemeği için bir de tatlıcı ekler misin?"
    
    print(f"2. İSTEK (HAFIZA TESTİ): {kullanici_sorusu_2}\n" + "-"*50)
    
    # İkinci soruda tekrar system_prompt göndermemize gerek yok, hafıza onu da hatırlayacaktır.
    yanit_2 = agent_executor.invoke({
        "messages": [
            ("user", kullanici_sorusu_2)
        ]
    }, config)
    
    print("\n=== GÜNCELLENMİŞ PLAN ===\n" + yanit_2["messages"][-1].content)