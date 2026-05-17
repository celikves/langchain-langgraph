import json
import os
from datetime import datetime

import requests
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.tools import tool

from calendar_logic import find_common_free_slots, load_calendars, summarize_calendars_for_llm

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"


def _get_city_coordinates(city: str) -> tuple[float, float] | None:
    response = requests.get(
        GEOCODING_URL,
        params={"name": city, "count": 1, "language": "tr", "format": "json"},
        timeout=10,
    ).json()
    if "results" not in response:
        return None
    result = response["results"][0]
    return result["latitude"], result["longitude"]


def _format_duration_text(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours and minutes:
        return f"yaklaşık {hours} saat {minutes} dakika"
    if hours:
        return f"yaklaşık {hours} saat"
    return f"yaklaşık {minutes} dakika"


@tool
def calculate_distance_and_duration(origin_city: str, destination_city: str) -> str:
    """İki şehir arasındaki seyahat mesafesini ve tahmini varış süresini hesaplar."""
    try:
        origin = _get_city_coordinates(origin_city)
        if origin is None:
            return f"Sistem hatası: '{origin_city}' koordinatları bulunamadı."

        destination = _get_city_coordinates(destination_city)
        if destination is None:
            return f"Sistem hatası: '{destination_city}' koordinatları bulunamadı."

        origin_lat, origin_lon = origin
        dest_lat, dest_lon = destination
        osrm_response = requests.get(
            f"{OSRM_URL}/{origin_lon},{origin_lat};{dest_lon},{dest_lat}",
            params={"overview": "false"},
            timeout=15,
        ).json()

        if osrm_response.get("code") != "Ok" or not osrm_response.get("routes"):
            return (
                f"{origin_city} ile {destination_city} arası rota hesaplanamadı. "
                "Alternatif plan oluştur."
            )

        route = osrm_response["routes"][0]
        km = round(route["distance"] / 1000)
        return f"{km} km, {_format_duration_text(route['duration'])}"

    except Exception as e:
        return f"Mesafe hesaplanırken hata oluştu: {str(e)}. Ajan inisiyatif kullanmalı."


@tool
def get_weather_forecast(city: str, date: str) -> str:
    """Belirtilen şehir ve tarih (YYYY-MM-DD formatında) için hava durumu tahminini getirir."""
    try:
        coordinates = _get_city_coordinates(city)
        if coordinates is None:
            return f"Sistem hatası: '{city}' koordinatları bulunamadı. Alternatif plan oluştur."

        latitude, longitude = coordinates

        weather_url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
            f"&timezone=Europe%2FIstanbul&start_date={date}&end_date={date}"
        )

        weather_response = requests.get(weather_url).json()

        if "daily" not in weather_response or not weather_response["daily"].get("temperature_2m_max"):
            return (
                f"Uyarı: {date} tarihi için hava durumu alınamadı. "
                "Planı hem açık hem kapalı mekanlara uygun yap."
            )

        max_temp = weather_response["daily"]["temperature_2m_max"][0]
        min_temp = weather_response["daily"]["temperature_2m_min"][0]
        precipitation_probability = weather_response["daily"]["precipitation_probability_max"][0]

        status_message = (
            f"{date} tarihinde {city} için beklenen hava: "
            f"Gündüz {max_temp}°C, Gece {min_temp}°C. Yağış ihtimali: %{precipitation_probability}. "
        )

        if precipitation_probability > 40:
            status_message += "Yağış ihtimali yüksek, planda kapalı mekanlar tercih edilmeli."
        else:
            status_message += "Hava açık görünüyor, açık hava etkinlikleri planlanabilir."

        return status_message

    except Exception as e:
        return f"Hava durumu çekilirken hata oluştu: {str(e)}. Ajan inisiyatif kullanmalı."


def _format_tavily_results(results) -> str:
    if isinstance(results, str):
        try:
            results = json.loads(results)
        except json.JSONDecodeError:
            return results
    if not results:
        return "Sonuç bulunamadı."
    lines = []
    for i, item in enumerate(results, 1):
        if isinstance(item, dict):
            title = item.get("title", "Başlıksız")
            content = item.get("content", item.get("snippet", ""))
            url = item.get("url", "")
            lines.append(f"{i}. {title}\n   {content}\n   Kaynak: {url}")
        else:
            lines.append(f"{i}. {item}")
    return "\n\n".join(lines)


_tavily_search: TavilySearchResults | None = None


def _get_tavily_search() -> TavilySearchResults:
    global _tavily_search
    if _tavily_search is None:
        _tavily_search = TavilySearchResults(max_results=3)
    return _tavily_search


@tool
def ortak_bos_zaman_bul(takvim_dosya_yolu: str = "") -> str:
    """İki kişinin takvimini karşılaştırıp ortak boş saatleri döndürür (saf Python, halüsinasyonsuz).
    Boş bırakılırsa varsayılan mock JSON kullanılır."""
    try:
        path = takvim_dosya_yolu.strip() or None
        data = load_calendars(path) if path else load_calendars()
        slots = find_common_free_slots(data)
        return json.dumps(
            {"ortak_bos_zamanlar": slots, "ozet": summarize_calendars_for_llm(data)},
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        return f"Takvim okunamadı: {e}"


def _rush_hour_multiplier(departure_hour: int) -> float:
    """İş çıkışı trafiği için basit çarpan (gerçek API yerine geliştirme aşaması)."""
    if 17 <= departure_hour <= 19:
        return 1.45
    if 7 <= departure_hour <= 9:
        return 1.25
    return 1.0


@tool
def trafik_ve_mesafe_getir(kalkis_sehir: str, varis_sehir: str, kalkis_saati: str) -> str:
    """Belirtilen saatte iki şehir arası mesafe ve trafik etkisi dahil tahmini süreyi hesaplar.
    kalkis_saati: HH:MM veya YYYY-MM-DDTHH:MM formatında."""
    try:
        if "T" in kalkis_saati:
            dt = datetime.fromisoformat(kalkis_saati)
        else:
            dt = datetime.strptime(kalkis_saati, "%H:%M").replace(year=2026, month=5, day=22)
        hour = dt.hour

        raw = calculate_distance_and_duration.invoke(
            {"origin_city": kalkis_sehir, "destination_city": varis_sehir}
        )
        if "km" not in raw:
            return raw

        multiplier = _rush_hour_multiplier(hour)
        if multiplier > 1.0:
            return (
                f"{raw}. Kalkış saati {dt.strftime('%H:%M')}: yoğun trafik bekleniyor "
                f"(süreye ~%{int((multiplier - 1) * 100)} ek pay). "
                f"Terminal/istasyona gitmeden önce bu payı plana dahil et."
            )
        return f"{raw}. Kalkış saati {dt.strftime('%H:%M')}: normal trafik koşulları varsayıldı."
    except Exception as e:
        return f"Trafik/mesafe hesabı başarısız: {e}"


@tool
def bilet_ara(tarih: str, kalkis: str, varis: str, tercih: str = "otobus") -> str:
    """Belirtilen güzergahta örnek ulaşım seçenekleri (geliştirme mock'u).
    Gerçek entegrasyon için Tavily veya taşıyıcı API kullanılabilir."""
    mock = {
        "otobus": [
            {"firma": "Metro Turizm", "kalkis": "18:30", "varis_tahmini": "23:15", "fiyat_tl": 450},
            {"firma": "Pamukkale", "kalkis": "19:00", "varis_tahmini": "23:45", "fiyat_tl": 420},
        ],
        "ucak": [
            {"firma": "THY", "kalkis": "18:45", "varis_tahmini": "19:40", "fiyat_tl": 1850},
            {"firma": "Pegasus", "kalkis": "20:10", "varis_tahmini": "21:05", "fiyat_tl": 1200},
        ],
    }
    secenekler = mock.get(tercih.lower(), mock["otobus"])
    return json.dumps(
        {
            "tarih": tarih,
            "guzergah": f"{kalkis} → {varis}",
            "tercih": tercih,
            "not": "Mock veri — üretimde gerçek API bağlanmalı.",
            "secenekler": secenekler,
        },
        ensure_ascii=False,
        indent=2,
    )


@tool
def search_places_online(query: str) -> str:
    """Belirli bir şehirdeki mekanları, restoranları veya etkinlikleri bulmak için internette gerçek zamanlı arama yapar.
    Arama sorgusunu (örn: 'Bursa düşük bütçeli kapalı mekanlar ve restoranlar') sen belirlemelisin."""
    if not os.getenv("TAVILY_API_KEY"):
        return (
            "TAVILY_API_KEY ortam değişkeni tanımlı değil. "
            "tavily.com üzerinden ücretsiz API anahtarı alıp .env dosyasına ekleyin."
        )
    try:
        result = _get_tavily_search().invoke(query)
        return f"Web Arama Sonuçları (Tavily):\n{_format_tavily_results(result)}"
    except Exception as e:
        return f"Arama sırasında bir hata oluştu: {str(e)}. Lütfen alternatif ve daha kısa bir sorgu dene."


surprise_visit_tools = [
    ortak_bos_zaman_bul,
    trafik_ve_mesafe_getir,
    bilet_ara,
    calculate_distance_and_duration,
    get_weather_forecast,
    search_places_online,
]

agent_tools = [
    ortak_bos_zaman_bul,
    trafik_ve_mesafe_getir,
    bilet_ara,
    calculate_distance_and_duration,
    get_weather_forecast,
    search_places_online,
]
