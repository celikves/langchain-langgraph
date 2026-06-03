"""Supervisor — state bayraklarına göre dinamik yönlendirme (Aşama 2 MA)."""

from __future__ import annotations

from langgraph.graph import END

from langchain_core.runnables import RunnableConfig
from langsmith import traceable

from multi_agent.state import SeyahatState, SiradakiAjan


@traceable(name="Supervisor", run_type="chain", tags=["multi-agent", "supervisor"])
def supervisor_node(state: SeyahatState, config: RunnableConfig) -> dict:
    """Hedefli keşif bayraklarını hazırlar; yönlendirme supervisor_router'da."""
    if state.get("hata_durumu"):
        return {}

    siradaki = state.get("siradaki_ajan") or ""
    rapor = state.get("kalite_raporu") or {}
    eksik = list(rapor.get("eksik_turler") or [])

    if siradaki == "hedefli_kesif" and eksik:
        print(f"\n[🎯] Supervisor — hedefli keşif: {', '.join(eksik)}")
        return {"kesif_hedef_turler": eksik, "kesif_partial": []}

    son = state.get("son_dugum") or ""
    if son:
        print(f"\n[🧭] Supervisor — son düğüm: {son}, siradaki_ajan: {siradaki or '(otomatik)'}")
    return {}


def supervisor_router(state: SeyahatState) -> str | SiradakiAjan:
    if state.get("hata_durumu"):
        return END

    siradaki = state.get("siradaki_ajan") or ""
    son = state.get("son_dugum") or ""

    if siradaki == "basarisiz_kapanis":
        return END
    if siradaki == "bitir":
        return END

    if son == "reviewer":
        if siradaki == "hedefli_kesif":
            return "kesif"
        if siradaki == "yeniden_planla":
            if state.get("revizyon_sayisi", 0) >= 2:
                return END
            return "planlayici"
        return END

    if son in ("", "bootstrap"):
        return "lojistik"
    if son == "lojistik":
        return "kesif"
    if son == "kesif":
        return "planlayici"

    return END
