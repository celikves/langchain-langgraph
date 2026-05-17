import requests
import random
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun

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
    """Belirtilen şehir ve tarih (YYYY-MM-DD formatında) için hava durumu tahminini getirir."""
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={sehir}&count=1&language=tr&format=json"
        geo_response = requests.get(geo_url).json()
        
        if "results" not in geo_response:
            return f"Sistem hatası: '{sehir}' koordinatları bulunamadı. Alternatif plan oluştur."
            
        enlem = geo_response["results"][0]["latitude"]
        boylam = geo_response["results"][0]["longitude"]
        
        weather_url = (f"https://api.open-meteo.com/v1/forecast?latitude={enlem}&longitude={boylam}"
                       f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
                       f"&timezone=Europe%2FIstanbul&start_date={tarih}&end_date={tarih}")
        
        weather_response = requests.get(weather_url).json()
        
        if "daily" not in weather_response or not weather_response["daily"].get("temperature_2m_max"):
            return f"Uyarı: {tarih} tarihi için hava durumu alınamadı. Planı hem açık hem kapalı mekanlara uygun yap."
            
        max_sicaklik = weather_response["daily"]["temperature_2m_max"][0]
        min_sicaklik = weather_response["daily"]["temperature_2m_min"][0]
        yagis_ihtimali = weather_response["daily"]["precipitation_probability_max"][0]
        
        durum_mesaji = (f"{tarih} tarihinde {sehir} için beklenen hava: "
                        f"Gündüz {max_sicaklik}°C, Gece {min_sicaklik}°C. Yağış ihtimali: %{yagis_ihtimali}. ")
        
        if yagis_ihtimali > 40:
            durum_mesaji += "Yağış ihtimali yüksek, planda kapalı mekanlar tercih edilmeli."
        else:
            durum_mesaji += "Hava açık görünüyor, açık hava etkinlikleri planlanabilir."
            
        return durum_mesaji
        
    except Exception as e:
        return f"Hava durumu çekilirken hata oluştu: {str(e)}. Ajan inisiyatif kullanmalı."

@tool
def internette_mekan_ara(sorgu: str) -> str:
    """Belirli bir şehirdeki mekanları, restoranları veya etkinlikleri bulmak için internette gerçek zamanlı arama yapar.
    Arama sorgusunu (örn: 'Bursa düşük bütçeli kapalı mekanlar ve restoranlar') sen belirlemelisin."""
    try:
        arama_araci = DuckDuckGoSearchRun()
        sonuc = arama_araci.invoke(sorgu)
        # LLM'in okuyabilmesi için dönen metin özetini string olarak iletiyoruz
        return f"Web Arama Sonuçları: {sonuc}"
    except Exception as e:
        return f"Arama sırasında bir hata oluştu: {str(e)}. Lütfen alternatif ve daha kısa bir sorgu dene."

# Listeyi yeni aracımızla güncelledik
agent_tools = [mesafe_ve_sure_hesapla, hava_durumu_getir, internette_mekan_ara]