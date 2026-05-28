from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage

from state import SeyahatState
from tools import lojistik_araclari, kesif_araclari

# ==========================================
# ORTAK LLM KURULUMU
# ==========================================
# Tüm ajanlar bu modeli kullanacak. 
# Sıcaklık (temperature) 0 tutularak analitik ve tutarlı sonuçlar hedefleniyor.
llm = ChatOllama(model="qwen2.5:7b", temperature=0)

# ==========================================
# 1. LOJİSTİK AJANI VE DÜĞÜMÜ
# ==========================================
lojistik_prompt = """Sen uzman bir Lojistik Ajanısın. 
Görevin, kullanıcıların takvim kısıtlamalarını ve aralarındaki mesafeyi hesaplayarak en uygun yola çıkış ve buluşma saatlerini bulmaktır. 
KESİNLİKLE 'ortak_bos_zaman_bul' ve 'mesafe_ve_sure_hesapla' araçlarını kullan."""

# Lojistik ajanını kendi araçlarıyla izole bir şekilde oluşturuyoruz
lojistik_ajani = create_react_agent(llm, tools=lojistik_araclari, prompt=lojistik_prompt)

def lojistik_node(state: SeyahatState):
    print("\n[🤖] Lojistik Ajanı Çalışıyor...")
    # State'ten verileri alıp ajana sunuyoruz
    baglam = (
        f"Kullanıcı Profilleri: {state.get('kullanici_profilleri')}\n"
        f"Ortak Kısıtlamalar: {state.get('ortak_kisitlamalar')}"
    )
    
    sonuc = lojistik_ajani.invoke({"messages": [HumanMessage(content=baglam)]})
    
    # Ajanın ürettiği en son mesajı alıp state'in 'lojistik_verisi' kısmına güncelliyoruz
    return {"lojistik_verisi": sonuc["messages"][-1].content}

# ==========================================
# 2. KEŞİF AJANI VE DÜĞÜMÜ
# ==========================================
kesif_prompt = """Sen uzman bir Keşif Ajanısın. 
Görevin, hedef şehirdeki hava durumunu öğrenmek ve hava koşullarına uygun, bütçeyi aşmayan gerçek mekanlar bulmaktır. 
KESİNLİKLE 'hava_durumu_getir' ve 'internette_mekan_ara' araçlarını kullan."""

kesif_ajani = create_react_agent(llm, tools=kesif_araclari, prompt=kesif_prompt)

def kesif_node(state: SeyahatState):
    print("\n[🔎] Keşif Ajanı Çalışıyor...")
    # Keşif ajanı, lojistik ajanının bulduğu saatleri bilmeli ki ona göre restoran arasın
    baglam = (
        f"Hedef: Antalya\n"
        f"Lojistik Planı ve Saatler: {state.get('lojistik_verisi')}\n"
        f"Mekanlar için hedef bütçe: Orta"
    )
    
    sonuc = kesif_ajani.invoke({"messages": [HumanMessage(content=baglam)]})
    return {"kesif_verisi": sonuc["messages"][-1].content}

# ==========================================
# 3. PLANLAYICI AJAN (SENTEZ) DÜĞÜMÜ
# ==========================================
# Planlayıcı dış dünya ile iletişime geçmez (tool kullanmaz).
# Sadece State'teki verileri alıp akıcı bir metne döker.
def planlayici_node(state: SeyahatState):
    print("\n[✍️] Planlayıcı Ajan Sentez Yapıyor...")
    
    planlayici_prompt = f"""Sen Baş Planlayıcı Ajansın.
Aşağıdaki ham lojistik ve keşif verilerini kullanarak saat saat yapılandırılmış, akıcı ve romantik bir sürpriz hafta sonu seyahat planı oluştur.

--- Lojistik Verisi ---
{state.get('lojistik_verisi')}

--- Keşif Verisi ---
{state.get('kesif_verisi')}

Kurallar:
1. Sadece 'Keşif Verisi' içinde geçen gerçek mekan isimlerini kullan. Halüsinasyon görme.
2. Zaman planında lojistik saatleriyle çelişme.
3. Planı "Cuma Akşamı", "Cumartesi", "Pazar" başlıklarıyla düzenle.
4. Çıktı dili Türkçe olsun.
"""

    sonuc = llm.invoke(
        [
            SystemMessage(content="Sen deneyimli bir seyahat planlayıcısısın."),
            HumanMessage(content=planlayici_prompt),
        ]
    )

    return {"nihai_plan": sonuc.content}