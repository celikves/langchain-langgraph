"""Multi-agent araçları — kök `tools.py` ve `calendar_logic` (mock/fallback yok)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from multi_agent.place_extract import mekanlari_cikar  # noqa: E402
from tools import (  # noqa: E402
    bilet_ara as _bilet_ara,
    get_weather_forecast,
    ortak_bos_zaman_bul as _ortak_bos_zaman_bul,
    search_places_online,
    trafik_ve_mesafe_getir as _trafik_ve_mesafe_getir,
)

try:
    from langchain_tavily import TavilySearch
except ImportError:
    TavilySearch = None

try:
    from langchain_community.tools.tavily_search import TavilySearchResults
except ImportError:
    TavilySearchResults = None

_tavily_araci = None


def _tavily_ham_sonuc(sorgu: str) -> tuple[Any, str]:
    """(ham sonuç listesi veya metin, uyarı)"""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return [], "TAVILY_API_KEY tanımlı değil."

    global _tavily_araci
    try:
        if TavilySearch is not None:
            if _tavily_araci is None:
                _tavily_araci = TavilySearch(max_results=5, tavily_api_key=api_key)
            return _tavily_araci.invoke({"query": sorgu}), ""
        if TavilySearchResults is not None:
            if _tavily_araci is None:
                _tavily_araci = TavilySearchResults(max_results=5, tavily_api_key=api_key)
            return _tavily_araci.invoke(sorgu), ""
    except Exception as e:
        return [], f"Tavily hatası: {e}"

    ham = search_places_online.invoke({"query": sorgu})
    return ham, ""


@tool
def ortak_bos_zaman_bul(takvim_dosya_yolu: str) -> str:
    """Takvim JSON yolundan ortak boş saatleri döndürür (calendar_logic)."""
    return _ortak_bos_zaman_bul.invoke({"takvim_dosya_yolu": takvim_dosya_yolu})


@tool
def trafik_ve_mesafe_getir(
    kalkis_sehir: str,
    varis_sehir: str,
    kalkis_saati: str,
    tarih: str = "",
) -> str:
    """Trafik dahil rota süresi (JSON) — OSRM + saat dilimi çarpanı."""
    return _trafik_ve_mesafe_getir.invoke(
        {
            "kalkis_sehir": kalkis_sehir,
            "varis_sehir": varis_sehir,
            "kalkis_saati": kalkis_saati,
            "tarih": tarih,
        }
    )


@tool
def bilet_ara(tarih: str, kalkis: str, varis: str, tercih: str = "otobus") -> str:
    """Güzergahta sefer/bilet araması (yapılandırılmış JSON)."""
    return _bilet_ara.invoke(
        {"tarih": tarih, "kalkis": kalkis, "varis": varis, "tercih": tercih}
    )


@tool
def hava_durumu_getir(sehir: str, tarih: str) -> str:
    """Şehir ve tarih için hava durumu (Open-Meteo)."""
    return get_weather_forecast.invoke({"city": sehir, "date": tarih})


@tool
def internette_mekan_ara(sorgu: str) -> str:
    """Tavily ile gerçek mekan adları (liste başlıkları filtrelenir)."""
    ham, uyari = _tavily_ham_sonuc(sorgu)
    mekanlar = mekanlari_cikar(ham)
    if not mekanlar:
        return json.dumps(
            {
                "mekanlar": [],
                "uyari": uyari or "Geçerli mekan adı çıkarılamadı (yalnızca liste başlıkları döndü).",
            },
            ensure_ascii=False,
        )
    return json.dumps({"mekanlar": mekanlar, "uyari": uyari}, ensure_ascii=False)


lojistik_araclari = [ortak_bos_zaman_bul, trafik_ve_mesafe_getir, bilet_ara]
kesif_araclari = [hava_durumu_getir, internette_mekan_ara]
