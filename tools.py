import json
import os
from datetime import datetime

import requests
from langchain_core.tools import tool

try:
    from langchain_community.tools.tavily_search import TavilySearchResults
except ImportError:
    TavilySearchResults = None  # type: ignore[misc, assignment]

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


_tavily_search = None


def _get_tavily_search() -> TavilySearchResults:
    global _tavily_search
    if TavilySearchResults is None:
        raise RuntimeError("langchain_community yüklü değil; Tavily araması kullanılamaz.")
    if _tavily_search is None:
        _tavily_search = TavilySearchResults(max_results=3)
    return _tavily_search


@tool
def ortak_bos_zaman_bul(takvim_dosya_yolu: str) -> str:
    """Takvim JSON yolundan ortak boş saatleri döndürür (saf Python, halüsinasyonsuz)."""
    try:
        path = takvim_dosya_yolu.strip()
        if not path:
            return json.dumps({"hata": "takvim_dosya_yolu zorunludur", "ortak_bos_zamanlar": []}, ensure_ascii=False)
        data = load_calendars(path)
        slots = find_common_free_slots(data)
        return json.dumps(
            {"ortak_bos_zamanlar": slots, "ozet": summarize_calendars_for_llm(data)},
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        return f"Takvim okunamadı: {e}"


def _rush_hour_multiplier(departure_hour: int) -> float:
    """İş çıkışı trafiği için saat dilimine göre süre çarpanı (OSRM taban süresine uygulanır)."""
    if 17 <= departure_hour <= 19:
        return 1.45
    if 7 <= departure_hour <= 9:
        return 1.25
    return 1.0


def _parse_kalkis_zamani(kalkis_saati: str, tarih: str) -> datetime | None:
    if "T" in kalkis_saati:
        return datetime.fromisoformat(kalkis_saati)
    if tarih:
        return datetime.strptime(f"{tarih} {kalkis_saati}", "%Y-%m-%d %H:%M")
    return None


def rota_osrm_hesapla(kalkis_sehir: str, varis_sehir: str) -> dict:
    """OSRM ile km ve süre (saniye). Hata durumunda {'hata': ...}."""
    try:
        origin = _get_city_coordinates(kalkis_sehir)
        if origin is None:
            return {"hata": f"'{kalkis_sehir}' koordinatları bulunamadı."}
        destination = _get_city_coordinates(varis_sehir)
        if destination is None:
            return {"hata": f"'{varis_sehir}' koordinatları bulunamadı."}

        origin_lat, origin_lon = origin
        dest_lat, dest_lon = destination
        osrm_response = requests.get(
            f"{OSRM_URL}/{origin_lon},{origin_lat};{dest_lon},{dest_lat}",
            params={"overview": "false"},
            timeout=15,
        ).json()
        if osrm_response.get("code") != "Ok" or not osrm_response.get("routes"):
            return {"hata": f"{kalkis_sehir} → {varis_sehir} rotası hesaplanamadı."}

        route = osrm_response["routes"][0]
        return {
            "km": round(route["distance"] / 1000),
            "sure_saniye_osrm": float(route["duration"]),
            "sure_metin_osrm": _format_duration_text(route["duration"]),
        }
    except Exception as e:
        return {"hata": f"OSRM hatası: {e}"}


def trafik_ve_mesafe_hesapla(
    kalkis_sehir: str,
    varis_sehir: str,
    kalkis_saati: str,
    tarih: str = "",
) -> dict:
    """Trafik çarpanı uygulanmış yapılandırılmış rota (LLM tahmini yok)."""
    dt = _parse_kalkis_zamani(kalkis_saati, tarih)
    if dt is None:
        return {"hata": "tarih (YYYY-MM-DD) ve kalkis_saati (HH:MM) birlikte gerekli."}

    base = rota_osrm_hesapla(kalkis_sehir, varis_sehir)
    if "hata" in base:
        return base

    carpani = _rush_hour_multiplier(dt.hour)
    sure_trafik = base["sure_saniye_osrm"] * carpani
    yuzde = int((carpani - 1) * 100) if carpani > 1.0 else 0
    return {
        "kalkis_sehir": kalkis_sehir,
        "varis_sehir": varis_sehir,
        "kalkis_zamani": dt.isoformat(),
        "km": base["km"],
        "sure_saniye_osrm": base["sure_saniye_osrm"],
        "sure_saniye_trafik_dahil": sure_trafik,
        "sure_metin": _format_duration_text(sure_trafik),
        "trafik_carpani": carpani,
        "yogun_trafik": carpani > 1.0,
        "trafik_notu": (
            f"Kalkış {dt.strftime('%H:%M')}: yoğun trafik (~%{yuzde} ek süre)."
            if carpani > 1.0
            else f"Kalkış {dt.strftime('%H:%M')}: normal trafik."
        ),
    }


@tool
def trafik_ve_mesafe_getir(
    kalkis_sehir: str,
    varis_sehir: str,
    kalkis_saati: str,
    tarih: str = "",
) -> str:
    """İki şehir arası km ve trafik dahil süre (JSON). kalkis_saati: HH:MM veya ISO; tarih: YYYY-MM-DD."""
    sonuc = trafik_ve_mesafe_hesapla(kalkis_sehir, varis_sehir, kalkis_saati, tarih)
    return json.dumps(sonuc, ensure_ascii=False)


@tool
def bilet_ara(tarih: str, kalkis: str, varis: str, tercih: str = "otobus") -> str:
    """Bilet/sefer araması — yalnızca yapılandırılmış API/Tavily entegrasyonu bağlandığında kullanılır."""
    return json.dumps(
        {
            "hata": "Bilet API entegrasyonu yapılandırılmadı",
            "tarih": tarih,
            "guzergah": f"{kalkis} → {varis}",
            "tercih": tercih,
            "secenekler": [],
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
