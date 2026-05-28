import os
import requests
from langchain_core.tools import tool

try:
    # Yeni paket (önerilen)
    from langchain_tavily import TavilySearch
except ImportError:
    TavilySearch = None

try:
    # Geriye dönük uyumluluk
    from langchain_community.tools.tavily_search import TavilySearchResults
except ImportError:
    TavilySearchResults = None

# ==========================================
# 1. LOJİSTİK AJANI ARAÇLARI (Takvim & Ulaşım)
# ==========================================

@tool
def ortak_bos_zaman_bul(kullanici_kisitlamalari: str) -> str:
    """
    Kullanıcıların mesai bitiş saatlerini veya takvim kısıtlamalarını analiz ederek 
    en erken yola çıkış ve buluşma saatini hesaplar.
    """
    # Geliştirme aşamasında mock (simüle edilmiş) veri dönüyoruz.
    # İleride buraya gerçek bir .ics parser eklenebilir.
    return (
        f"Analiz edilen kısıtlamalar: {kullanici_kisitlamalari}. "
        "Sonuç: En geç çıkan kişinin mesaisi 17:00'de bitiyor. "
        "Trafik payı ile yola çıkış en erken 18:00, Antalya'da buluşma saati 23:30 olarak planlanmalıdır."
    )

@tool
def mesafe_ve_sure_hesapla(kalkis_sehri: str, varis_sehri: str) -> str:
    """İki şehir arasındaki seyahat mesafesini ve tahmini varış süresini hesaplar."""
    # Sabit veriler. OSRM API'ye geçiş yapılana kadar kullanılacak geçici sözlük.
    mesafeler = {
        ("Akhisar", "Antalya"): "415 km, yaklaşık 5.5 saat",
        ("Ankara", "Antalya"): "480 km, yaklaşık 6 saat",
        ("İzmir", "Antalya"): "460 km, yaklaşık 6 saat",
        ("İstanbul", "Antalya"): "700 km, yaklaşık 8.5 saat"
    }
    rota = (kalkis_sehri, varis_sehri)
    ters_rota = (varis_sehri, kalkis_sehri)
    
    if rota in mesafeler: return mesafeler[rota]
    elif ters_rota in mesafeler: return mesafeler[ters_rota]
    return f"{kalkis_sehri} ve {varis_sehri} arası ortalama 500 km ve 6 saat varsayılabilir."

# ==========================================
# 2. KEŞİF AJANI ARAÇLARI (Hava Durumu & Mekan)
# ==========================================

@tool
def hava_durumu_getir(sehir: str, tarih: str) -> str:
    """Belirtilen şehir ve tarih (YYYY-MM-DD) için hava durumu tahminini getirir."""
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={sehir}&count=1&language=tr&format=json"
        geo_response = requests.get(geo_url).json()
        
        if "results" not in geo_response:
            return f"Sistem hatası: '{sehir}' bulunamadı."
            
        enlem = geo_response["results"][0]["latitude"]
        boylam = geo_response["results"][0]["longitude"]
        
        weather_url = (f"https://api.open-meteo.com/v1/forecast?latitude={enlem}&longitude={boylam}"
                       f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
                       f"&timezone=Europe%2FIstanbul&start_date={tarih}&end_date={tarih}")
        
        weather_response = requests.get(weather_url).json()
        
        max_sicaklik = weather_response["daily"]["temperature_2m_max"][0]
        yagis_ihtimali = weather_response["daily"]["precipitation_probability_max"][0]
        
        durum = "Yağışlı/Kapalı" if yagis_ihtimali > 40 else "Açık/Güneşli"
        return f"{tarih} tarihinde {sehir} hava durumu: {max_sicaklik}°C, {durum}. Yağış ihtimali: %{yagis_ihtimali}."
        
    except Exception as e:
        return f"Hava durumu çekilemedi. Hata: {str(e)}"

_tavily_araci = None


def _tavily_aracini_getir():
    """Tavily aracını sadece gerektiğinde oluşturur (lazy init)."""
    global _tavily_araci

    if _tavily_araci is not None:
        return _tavily_araci

    tavily_api_key = os.getenv("TAVILY_API_KEY")
    if not tavily_api_key:
        return None

    if TavilySearch is not None:
        _tavily_araci = TavilySearch(max_results=3, tavily_api_key=tavily_api_key)
        return _tavily_araci

    if TavilySearchResults is not None:
        _tavily_araci = TavilySearchResults(max_results=3, tavily_api_key=tavily_api_key)
        return _tavily_araci

    return None


@tool
def internette_mekan_ara(sorgu: str) -> str:
    """
    Verilen sorguya göre internette mekan araştırması yapar.
    TAVILY_API_KEY yoksa açıklayıcı bir hata mesajı döner.
    """
    tavily_araci = _tavily_aracini_getir()
    if tavily_araci is None:
        return (
            "Tavily araması kullanılamıyor. Lütfen ortam değişkeni olarak TAVILY_API_KEY tanımlayın "
            "ve gerekirse 'langchain-tavily' paketini kurun."
        )

    try:
        sonuc = tavily_araci.invoke({"query": sorgu})
        return str(sonuc)
    except Exception as e:
        return f"İnternet araması sırasında hata oluştu: {str(e)}"

# ==========================================
# 3. DIŞA AKTARMA (EXPORTS)
# ==========================================
# Ajanları oluştururken bu listeleri kullanacağız.

lojistik_araclari = [ortak_bos_zaman_bul, mesafe_ve_sure_hesapla]
kesif_araclari = [hava_durumu_getir, internette_mekan_ara]