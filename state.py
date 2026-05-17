from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class SeyahatState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    ortak_bos_zamanlar: list[str]
    kullanici_lokasyonlari: dict
    secilen_hedef: str
    plan_taslagi: str
    onaylandi: bool
    takvim_ozeti: str
    review_retries: int
