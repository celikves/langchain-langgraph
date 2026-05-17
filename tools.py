import requests
from langchain_core.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun

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


@tool
def search_places_online(query: str) -> str:
    """Belirli bir şehirdeki mekanları, restoranları veya etkinlikleri bulmak için internette gerçek zamanlı arama yapar.
    Arama sorgusunu (örn: 'Bursa düşük bütçeli kapalı mekanlar ve restoranlar') sen belirlemelisin."""
    try:
        search_tool = DuckDuckGoSearchRun()
        result = search_tool.invoke(query)
        return f"Web Arama Sonuçları: {result}"
    except Exception as e:
        return f"Arama sırasında bir hata oluştu: {str(e)}. Lütfen alternatif ve daha kısa bir sorgu dene."


agent_tools = [calculate_distance_and_duration, get_weather_forecast, search_places_online]
