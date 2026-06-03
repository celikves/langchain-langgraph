"""Keşif subgraph — tür bazlı paralel uzman düğümleri + merge (Aşama 1 MA).

LangGraph Send ile plaj / yemek / muzik / gezi keşifleri eşzamanlı çalışır;
kesif_merge düğümü partial sonuçları birleştirir.
"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from langsmith import traceable, get_current_run_tree

from multi_agent.kesif_layer import (
    kesif_hedefli_guncelle,
    kesif_partial_birlestir,
    kesif_sorgulari_ture_gore,
    kesif_sorgulari_uret,
    kesif_tur_calistir,
)
from multi_agent.state import SeyahatState
from multi_agent.tools import kesif_araclari
from multi_agent.tracing import invoke_tool

_TUR_ETIKET = {"plaj": "Plaj", "yemek": "Yemek", "muzik": "Müzik", "gezi": "Gezi"}


def _halt_payload(hata: str) -> dict:
    return {"hata_durumu": hata, "siradaki_ajan": "basarisiz_kapanis"}


def _mekan_fn_factory(config: RunnableConfig | None = None):
    mekan_araci = next(t for t in kesif_araclari if t.name == "internette_mekan_ara")
    return lambda sorgu: str(invoke_tool(mekan_araci, {"sorgu": sorgu}, config))


@traceable(name="Keşif Başlat", run_type="chain", tags=["multi-agent", "kesif"])
def kesif_baslat_node(state: SeyahatState, config: RunnableConfig) -> dict:
    """Hava + sorgu listesi; dispatch düğümüne hazırlık."""
    if state.get("hata_durumu"):
        return {}

    from multi_agent.kesif_layer import _extract_weather_fields

    hedef = state.get("hedef_sehir", "")
    hedef_tarih = state.get("hedef_tarih", "")
    if not hedef or not hedef_tarih:
        return _halt_payload("hedef_sehir veya hedef_tarih eksik.")

    profiller = state.get("kullanici_profilleri") or []
    kategoriler = state.get("kesif_kategorileri") or []
    hedef_turler = state.get("kesif_hedef_turler") or []

    hava = state.get("kesif_hava") or (state.get("kesif_verisi") or {}).get("hava") or {}
    if not hava:
        hava_araci = next(t for t in kesif_araclari if t.name == "hava_durumu_getir")
        hava_raw = str(invoke_tool(hava_araci, {"sehir": hedef, "tarih": hedef_tarih}, config))
        hava = _extract_weather_fields(hava_raw)

    sorgular = kesif_sorgulari_uret(hedef, profiller, kategoriler)
    gruplar = kesif_sorgulari_ture_gore(sorgular)
    if hedef_turler:
        gruplar = {t: items for t, items in gruplar.items() if t in hedef_turler}
        print(f"\n[🔎] Hedefli Keşif — {len(gruplar)} tür uzmanına dağıtılıyor: {', '.join(gruplar)}")
    else:
        print(f"\n[🔎] Keşif Subgraph — {len(gruplar)} tür uzmanına dağıtılıyor (paralel)")
    for tur, items in gruplar.items():
        etiket = _TUR_ETIKET.get(tur, tur)
        print(f"  → kesif_{tur}: {len(items)} arama")

    if hedef_turler and not gruplar:
        return _halt_payload(f"Hedefli keşif için sorgu bulunamadı: {', '.join(hedef_turler)}")

    return {
        "kesif_hava": hava,
        "kesif_partial": [],
        "kesif_tur_gruplari": gruplar,
    }


def kesif_dispatch(state: SeyahatState) -> list[Send]:
    if state.get("hata_durumu"):
        return []
    gruplar = state.get("kesif_tur_gruplari") or {}
    hedef = state.get("hedef_sehir", "")
    return [
        Send(
            "kesif_tur_worker",
            {
                "hedef_sehir": hedef,
                "kesif_aktif_tur": tur,
                "kesif_tur_sorgulari": sorgular,
            },
        )
        for tur, sorgular in gruplar.items()
    ]


@traceable(name="Keşif Tür Uzmanı", run_type="chain", tags=["multi-agent", "kesif"])
def kesif_tur_worker_node(state: SeyahatState, config: RunnableConfig) -> dict:
    """Tek tür keşif uzmanı — kendi sorgu dilimini işler."""
    if state.get("hata_durumu"):
        return {}

    tur = state.get("kesif_aktif_tur", "")
    sorgular = state.get("kesif_tur_sorgulari") or []
    hedef = state.get("hedef_sehir", "")
    if not tur or not sorgular:
        return {}

    etiket = _TUR_ETIKET.get(tur, tur)
    run_tree = get_current_run_tree()
    if run_tree:
        run_tree.name = f"Keşif Uzmanı — {etiket}"
        run_tree.extra = run_tree.extra or {}
        run_tree.extra.setdefault("metadata", {})["kesif_tur"] = tur

    print(f"  [⚡] kesif_{tur} uzmanı çalışıyor ({len(sorgular)} arama)...")

    partial = kesif_tur_calistir(hedef, tur, sorgular, mekan_ara_fn=_mekan_fn_factory(config))
    mekan_say = len(partial.get("mekanlar") or [])
    aktivite_say = len(partial.get("aktiviteler") or [])
    print(f"  ✓ kesif_{tur}: {mekan_say} mekan, {aktivite_say} aktivite")

    return {"kesif_partial": [partial]}


@traceable(name="Keşif Merge", run_type="chain", tags=["multi-agent", "kesif"])
def kesif_merge_node(state: SeyahatState, config: RunnableConfig) -> dict:
    """Paralel uzman çıktılarını birleştirir → kesif_verisi."""
    if state.get("hata_durumu"):
        return {}

    hedef = state.get("hedef_sehir", "")
    profiller = state.get("kullanici_profilleri") or []
    kategoriler = state.get("kesif_kategorileri") or []
    partials = state.get("kesif_partial") or []
    hava = state.get("kesif_hava") or {}
    hedef_turler = state.get("kesif_hedef_turler") or []
    mevcut = state.get("kesif_verisi") or {}

    if hedef_turler and mevcut:
        kesif_verisi, hata = kesif_hedefli_guncelle(
            mevcut, partials, hedef, profiller, kategoriler, hava
        )
        print(f"  ✓ Hedefli merge: {len(hedef_turler)} tür güncellendi")
    else:
        kesif_verisi, hata = kesif_partial_birlestir(hedef, profiller, kategoriler, partials, hava)

    if hata:
        return _halt_payload(hata)

    mekan_adlari = [m["ad"] for m in kesif_verisi.get("mekanlar", [])]
    aktivite_adlari = [a["ad"] for a in kesif_verisi.get("aktiviteler", [])]
    print(
        f"  ✓ Merge: {len(partials)} uzman → "
        f"{kesif_verisi.get('arama_sayisi', 0)} arama, "
        f"{len(mekan_adlari)} mekan, {len(aktivite_adlari)} aktivite"
    )
    if mekan_adlari:
        print(f"  ✓ Mekanlar: {', '.join(mekan_adlari[:5])}")
    if aktivite_adlari:
        print(f"  ✓ Aktiviteler: {', '.join(dict.fromkeys(aktivite_adlari))}")

    return {
        "kesif_verisi": kesif_verisi,
        "kesif_hedef_turler": [],
        "son_dugum": "kesif",
    }


def build_kesif_subgraph():
    g = StateGraph(SeyahatState)
    g.add_node("kesif_baslat", kesif_baslat_node)
    g.add_node("kesif_tur_worker", kesif_tur_worker_node)
    g.add_node("kesif_merge", kesif_merge_node)

    g.add_edge(START, "kesif_baslat")
    g.add_conditional_edges("kesif_baslat", kesif_dispatch, ["kesif_tur_worker"])
    g.add_edge("kesif_tur_worker", "kesif_merge")
    g.add_edge("kesif_merge", END)
    return g.compile(name="Keşif Subgraph")


kesif_subgraph = build_kesif_subgraph()
