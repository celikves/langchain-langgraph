"""Oturum JSON → yapılandırılmış LangGraph state (tek gerçeklik kaynağı)."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from calendar_logic import find_common_free_slots, load_calendars
from session_config import MIN_KATILIMCI, MAX_KATILIMCI, build_session_context

from langchain_core.runnables import RunnableConfig
from langsmith import traceable

from multi_agent.logistics_compute import profillerden_katilimci
from multi_agent.state import SeyahatState


def _session_path_from_env_or_state(state: SeyahatState) -> str:
    import os

    return (
        (state.get("session_config_path") or "").strip()
        or os.getenv("SEYAHAT_SESSION_PATH", "").strip()
        or str(_ROOT / "data" / "sessions" / "antalya_kizkiza_tatil.json")
    )


def bootstrap_from_session(session_path: str) -> dict:
    """JSON oturum dosyasından SeyahatState alanlarını üretir."""
    ctx = build_session_context(session_path)
    takvim_path = (ctx.get("takvim_dosyasi") or "").strip()
    if not takvim_path:
        return {"hata_durumu": "Oturum dosyasında takvim_dosyasi tanımlı değil."}

    try:
        calendar_data = load_calendars(takvim_path)
        slots = find_common_free_slots(calendar_data)
    except (OSError, ValueError, KeyError) as e:
        return {"hata_durumu": f"Takvim yüklenemedi: {e}"}

    if not slots:
        return {
            "hata_durumu": "Takvim kesişimi boş: ortak boş zaman bulunamadı.",
            "ortak_bos_zamanlar": [],
            "takvim_dosyasi": takvim_path,
        }

    profiller = ctx["kullanici_profilleri"]
    katilimcilar = profillerden_katilimci(profiller)
    n = len(katilimcilar)
    if n < MIN_KATILIMCI:
        return {"hata_durumu": f"En az {MIN_KATILIMCI} katılımcı profili gerekli."}
    if n > MAX_KATILIMCI:
        return {"hata_durumu": f"En fazla {MAX_KATILIMCI} katılımcı destekleniyor."}

    hedef_tarih = slots[0]["baslangic"][:10]

    return {
        "session_config_path": session_path,
        "hedef_sehir": ctx["hedef_sehir"],
        "takvim_dosyasi": takvim_path,
        "ortak_kisitlamalar": ctx["ortak_kisitlamalar"],
        "hedef_tarih": hedef_tarih,
        "katilimci_bilgileri": katilimcilar,
        "kullanici_profilleri": profiller,
        "ortak_bos_zamanlar": slots,
        "kesif_kategorileri": ctx.get("kesif_kategorileri") or [],
        "kisi_sayisi": ctx.get("kisi_sayisi", n),
        "hata_durumu": "",
        "lojistik_plani": {},
        "ortak_bulusma_penceresi": {},
        "hata_mesaji": "",
        "siradaki_ajan": "",
        "revizyon_sayisi": 0,
        "kalite_raporu": {},
        "kesif_hedef_turler": [],
        "son_dugum": "",
        "lojistik_verisi": {},
        "kesif_verisi": {},
        "nihai_plan": "",
    }


@traceable(name="Bootstrap", run_type="chain", tags=["multi-agent", "bootstrap"])
def bootstrap_node(state: SeyahatState, config: RunnableConfig) -> dict:
    print("\n[📂] Oturum ve takvim bootstrap...")
    session_path = _session_path_from_env_or_state(state)
    result = bootstrap_from_session(session_path)
    if result.get("hata_durumu"):
        print(f"  ✗ {result['hata_durumu']}")
    else:
        n = len(result.get("ortak_bos_zamanlar", []))
        print(f"  ✓ {n} ortak boş zaman slotu yüklendi.")
    result["son_dugum"] = "bootstrap"
    return result
