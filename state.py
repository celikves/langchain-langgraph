from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class AsistanState(TypedDict, total=False):
    """Tek ajan StateGraph — mesajlar + dinamik oturum alanları."""

    messages: Annotated[list, add_messages]
    bootstrapped: bool
    session_config_path: str

    ana_gorev: str
    kullanici_profilleri: list[dict]
    kullanici_baglami: str
    zaman_kisitlamalari: str
    ortak_kisitlamalar: str
    is_akis_adimlari: str
    ozel_kurallar: str

    hedef_sehir: str
    takvim_dosyasi: str
    takvim_ozeti: str
    ortak_bos_zamanlar: list[dict]


# LangGraph çok düğümlü akış (travel_graph.py)
class SeyahatState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    ortak_bos_zamanlar: list[dict]
    kullanici_lokasyonlari: dict
    secilen_hedef: str
    plan_taslagi: str
    onaylandi: bool
    takvim_ozeti: str
    review_retries: int
