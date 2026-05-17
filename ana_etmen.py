from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

# Kendi yazdığımız araçlar modülünden listeyi içe aktarıyoruz
from tools import agent_tools

# ==========================================
# ETMEN VE MİMARİ KURULUMU
# ==========================================

llm = ChatOllama(model="qwen2.5:7b", temperature=0)
memory = MemorySaver()

# system_prompt = """Sen uzman bir sürpriz seyahat asistanısın. Kurallara kesinlikle uy:
# 1. İki şehir arasındaki mesafeyi hesapla.
# 2. Gidilecek tarihteki hava durumunu kontrol et.
# 3. Bütçeye uygun mekanlar seç.
# 4. Cevabını saat saat bir program şeklinde Türkçe sun."""

# system_prompt = """Sen uzman bir sürpriz seyahat asistanısın. Planlama yaparken şu adımları izle:
# 1. 'mesafe_ve_sure_hesapla' aracını kullanarak lojistik planını yap.
# 2. 'hava_durumu_getir' aracıyla hedef tarihteki hava durumunu öğren.
# 3. Öğrendiğin hava durumuna ve kullanıcının bütçesine (düşük/yüksek) uygun olacak şekilde, 'internette_mekan_ara' aracı için yaratıcı bir arama sorgusu oluştur (Örn: 'Bursa ucuz kapalı mekanlar').
# 4. Tüm bu verileri sentezleyerek saat saat detaylı bir Türkçe program sun. Neden o mekanı seçtiğini hava durumu veya bütçe verisiyle destekleyerek kısaca açıkla."""


system_prompt = """Sen üst düzey, otonom bir seyahat asistanısın. Asla kullanıcıya 'araştırabilirsiniz' veya 'bulabilirsiniz' gibi tavsiyelerde bulunma. İşi SEN yapmalısın.

Şu adımları KESİN bir sırayla izle:
1. 'mesafe_ve_sure_hesapla' aracı ile lojistiği çıkar.
2. 'hava_durumu_getir' aracı ile hedef tarihteki hava verisini al.
3. KESİNLİKLE 'internette_mekan_ara' aracını ÇALIŞTIR. Sorguya hava durumunu ve bütçeyi dahil et (Örn: 'Bursa yağmurlu hava ucuz kapalı restoranlar'). 
4. Araçtan dönen sonuçların içindeki GERÇEK MEKAN İSİMLERİNİ (Örn: X Restoranı, Y Müzesi) alarak saat saat bir program oluştur.

Eğer spesifik bir mekan ismi vermiyorsan, görevde başarısız olmuş sayılırsın."""

# Ajanı import ettiğimiz agent_tools ile kuruyoruz
agent_executor = create_react_agent(
    llm, 
    agent_tools, 
    checkpointer=memory
)

# ==========================================
# ANA AKIŞ VE TEST
# ==========================================

if __name__ == "__main__":
    print("\n[!] Akıllı Seyahat Ajanı Başlatılıyor...\n")
    config = {"configurable": {"thread_id": "seyahat_projesi_v2"}}
    
    kullanici_sorusu_1 = (
        "Hafta sonu arkadaşımla buluşacağım. Ben İstanbul'dan, o ise İzmir'den gelecek ve "
        "ortak nokta olarak Bursa'da buluşmaya karar verdik. Bütçemiz 'düşük'. "
        "23 Mayıs 2026 tarihi için bize hava durumuna da uygun sabahtan akşama bir plan yapar mısın?"
    )
    
    print(f"1. İSTEK: {kullanici_sorusu_1}\n" + "-"*50)
    
    yanit_1 = agent_executor.invoke({
        "messages": [
            ("system", system_prompt),
            ("user", kullanici_sorusu_1)
        ]
    }, config)
    
    print("\n=== NİHAİ PLAN ===\n" + yanit_1["messages"][-1].content)
    
    print("\n" + "="*70 + "\n")
    
    kullanici_sorusu_2 = "Peki bu plana akşam yemeği için bir de tatlıcı ekler misin?"
    print(f"2. İSTEK (HAFIZA TESTİ): {kullanici_sorusu_2}\n" + "-"*50)
    
    yanit_2 = agent_executor.invoke({
        "messages": [
            ("user", kullanici_sorusu_2)
        ]
    }, config)
    
    print("\n=== GÜNCELLENMİŞ PLAN ===\n" + yanit_2["messages"][-1].content)