import json
import logging
import os
import re
from datetime import datetime, timedelta

import requests
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.tools import tool

from calendar_logic import find_common_free_slots, load_calendars, summarize_calendars_for_llm

logger = logging.getLogger(__name__)

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
def ortak_bos_zaman_bul(takvim_dosya_yolu: str | None = None) -> str:
    """İki kişinin takvimini karşılaştırıp ortak boş saatleri döndürür (saf Python, halüsinasyonsuz).
    Boş bırakılırsa varsayılan mock JSON kullanılır."""
    try:
        path = (takvim_dosya_yolu or "").strip() or None
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


def _parse_rota_suresi_dakika(rota_metni: str) -> int:
    """'350 km, yaklaşık 4 saat 30 dakika' gibi metinden süreyi çıkarır."""
    hours = 0
    minutes = 0
    if m := re.search(r"(\d+)\s*saat", rota_metni):
        hours = int(m.group(1))
    if m := re.search(r"(\d+)\s*dakika", rota_metni):
        minutes = int(m.group(1))
    total = hours * 60 + minutes
    return total if total > 0 else 180


def _saat_ekle(kalkis_hhmm: str, dakika: int) -> str:
    base = datetime.strptime(kalkis_hhmm, "%H:%M")
    return (base + timedelta(minutes=dakika)).strftime("%H:%M")


def _fallback_bilet_secenekleri(tercih: str, rota_ozeti: str, sure_dk: int) -> list[dict]:
    """OpenAI yoksa veya hata olursa rota süresine göre 2 seçenek üretir."""
    if tercih.lower() == "ucak":
        firmalar = [("THY", 1650), ("Pegasus", 1180)]
        kalkislar = ["17:30", "19:00"]
        sure_dk = min(sure_dk, 120)
    else:
        firmalar = [("Metro Turizm", 480), ("Pamukkale Turizm", 430)]
        kalkislar = ["18:00", "19:30"]

    secenekler = []
    for (firma, fiyat), kalkis in zip(firmalar, kalkislar):
        secenekler.append(
            {
                "firma": firma,
                "kalkis": kalkis,
                "varis_tahmini": _saat_ekle(kalkis, sure_dk),
                "sure": f"{sure_dk // 60}s {sure_dk % 60}dk" if sure_dk >= 60 else f"{sure_dk}dk",
                "fiyat_tl": fiyat,
            }
        )
    return secenekler


def _openai_bilet_secenekleri(
    tarih: str,
    kalkis: str,
    varis: str,
    tercih: str,
    rota_ozeti: str,
    sure_dk: int,
) -> list[dict] | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("bilet_ara: OPENAI_API_KEY tanımlı değil, yedek seçenekler kullanılacak")
        return None

    try:
        from openai import OpenAI
    except ImportError:
        logger.exception("bilet_ara: openai paketi yüklü değil (pip install openai)")
        return None

    prompt = (
        f"Tarih: {tarih}\nGüzergah: {kalkis} → {varis}\nUlaşım: {tercih}\n"
        f"Rota: {rota_ozeti}\nTahmini yolculuk: {sure_dk} dakika.\n\n"
        "Tam 2 gerçekçi Türkiye seferi üret. Kalkış ve varış saatleri yolculuk süresine uysun "
        "(varis = kalkis + süre). Akşam/öğleden sonra kalkışları tercih et. "
        'JSON: {"secenekler":[{"firma","kalkis","varis_tahmini","sure","fiyat_tl"}, ...]} '
        "Sadece 2 öğe, sadece JSON."
    )

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_BILET_MODEL", "gpt-4o-mini"),
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "Seyahat planlama asistanısın. Kısa, tutarlı saatler ve makul TL fiyatları ver.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        raw = response.choices[0].message.content or ""
        logger.info("bilet_ara: OpenAI yanıtı alındı (%s karakter)", len(raw))
        data = json.loads(raw)
        secenekler = data.get("secenekler", data if isinstance(data, list) else [])
        if not isinstance(secenekler, list) or len(secenekler) < 1:
            logger.warning("bilet_ara: OpenAI JSON'da secenekler yok: %s", raw[:200])
            return None
        return secenekler[:2]
    except Exception:
        logger.exception("bilet_ara: OpenAI çağrısı başarısız")
        return None


@tool
def bilet_ara(tarih: str, kalkis: str, varis: str, tercih: str = "otobus") -> str:
    """Güzergahta 2 ulaşım seçeneği döndürür; saatler rota süresine göre OpenAI ile üretilir."""
    tercih_norm = (tercih or "otobus").strip().lower()
    logger.info(
        "bilet_ara çağrıldı: tarih=%s kalkis=%s varis=%s tercih=%s",
        tarih,
        kalkis,
        varis,
        tercih_norm,
    )

    try:
        rota_ozeti = calculate_distance_and_duration.invoke(
            {"origin_city": kalkis, "destination_city": varis}
        )
        logger.info("bilet_ara: rota_ozeti=%s", rota_ozeti)
    except Exception:
        logger.exception("bilet_ara: mesafe/süre hesabı başarısız")
        rota_ozeti = f"{kalkis} → {varis} (rota hesaplanamadı)"

    sure_dk = _parse_rota_suresi_dakika(rota_ozeti) if "km" in rota_ozeti else 180
    if tercih_norm == "ucak":
        sure_dk = min(sure_dk, 120)

    secenekler = _openai_bilet_secenekleri(tarih, kalkis, varis, tercih_norm, rota_ozeti, sure_dk)
    kaynak = "openai"
    if not secenekler:
        secenekler = _fallback_bilet_secenekleri(tercih_norm, rota_ozeti, sure_dk)
        kaynak = "hesaplanan_yedek"
        logger.info("bilet_ara: yedek seçenekler kullanıldı (2 adet)")

    payload = {
        "tarih": tarih,
        "guzergah": f"{kalkis} → {varis}",
        "tercih": tercih_norm,
        "rota_ozeti": rota_ozeti,
        "kaynak": kaynak,
        "secenekler": secenekler,
    }
    logger.info("bilet_ara: tamamlandı kaynak=%s", kaynak)
    return json.dumps(payload, ensure_ascii=False, indent=2)


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
