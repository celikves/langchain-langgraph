import requests
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"


def _sehir_koordinati_getir(sehir: str) -> tuple[float, float] | None:
    response = requests.get(
        GEOCODING_URL,
        params={"name": sehir, "count": 1, "language": "tr", "format": "json"},
        timeout=10,
    ).json()
    if "results" not in response:
        return None
    result = response["results"][0]
    return result["latitude"], result["longitude"]


def _sure_metni(saniye: float) -> str:
    saat = int(saniye // 3600)
    dakika = int((saniye % 3600) // 60)
    if saat and dakika:
        return f"yaklaşık {saat} saat {dakika} dakika"
    if saat:
        return f"yaklaşık {saat} saat"
    return f"yaklaşık {dakika} dakika"


@tool
def mesafe_ve_sure_hesapla(kalkis_sehri: str, varis_sehri: str) -> str:
    """İki şehir arasındaki seyahat mesafesini ve tahmini varış süresini hesaplar."""
    try:
        kalkis = _sehir_koordinati_getir(kalkis_sehri)
        if kalkis is None:
            return f"Sistem hatası: '{kalkis_sehri}' koordinatları bulunamadı."

        varis = _sehir_koordinati_getir(varis_sehri)
        if varis is None:
            return f"Sistem hatası: '{varis_sehri}' koordinatları bulunamadı."

        k_enlem, k_boylam = kalkis
        v_enlem, v_boylam = varis
        osrm_response = requests.get(
            f"{OSRM_URL}/{k_boylam},{k_enlem};{v_boylam},{v_enlem}",
            params={"overview": "false"},
            timeout=15,
        ).json()

        if osrm_response.get("code") != "Ok" or not osrm_response.get("routes"):
            return (
                f"{kalkis_sehri} ile {varis_sehri} arası rota hesaplanamadı. "
                "Alternatif plan oluştur."
            )

        rota = osrm_response["routes"][0]
        km = round(rota["distance"] / 1000)
        return f"{km} km, {_sure_metni(rota['duration'])}"

    except Exception as e:
        return f"Mesafe hesaplanırken hata oluştu: {str(e)}. Ajan inisiyatif kullanmalı."

@tool
def hava_durumu_getir(sehir: str, tarih: str) -> str:
    """Belirtilen şehir ve tarih (YYYY-MM-DD formatında) için hava durumu tahminini getirir."""
    try:
        koordinat = _sehir_koordinati_getir(sehir)
        if koordinat is None:
            return f"Sistem hatası: '{sehir}' koordinatları bulunamadı. Alternatif plan oluştur."

        enlem, boylam = koordinat
        
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