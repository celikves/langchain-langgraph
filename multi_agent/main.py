import os
import sys
from pathlib import Path

from langgraph.graph import END, START, StateGraph

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from multi_agent.agents import kesif_node, lojistik_node, planlayici_node, reviewer_node
from multi_agent.bootstrap import bootstrap_from_session, bootstrap_node
from multi_agent.state import SeyahatState

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

DEFAULT_SESSION = str(_ROOT / "data" / "sessions" / "antalya_kizkiza_tatil.json")


def _halt_router(state: SeyahatState) -> str:
    if state.get("hata_durumu"):
        return END
    return "devam"


workflow = StateGraph(SeyahatState)

workflow.add_node("bootstrap", bootstrap_node)
workflow.add_node("lojistik", lojistik_node)
workflow.add_node("kesif", kesif_node)
workflow.add_node("planlayici", planlayici_node)
workflow.add_node("reviewer", reviewer_node)

workflow.add_edge(START, "bootstrap")
workflow.add_conditional_edges(
    "bootstrap",
    _halt_router,
    {END: END, "devam": "lojistik"},
)
workflow.add_conditional_edges(
    "lojistik",
    _halt_router,
    {END: END, "devam": "kesif"},
)
workflow.add_conditional_edges(
    "kesif",
    _halt_router,
    {END: END, "devam": "planlayici"},
)
workflow.add_edge("planlayici", "reviewer")


def reviewer_router(state: SeyahatState):
    if state.get("hata_durumu") or state.get("siradaki_ajan") == "basarisiz_kapanis":
        return END
    if state.get("siradaki_ajan") == "yeniden_planla" and state.get("revizyon_sayisi", 0) < 2:
        return "planlayici"
    return END


workflow.add_conditional_edges(
    "reviewer",
    reviewer_router,
    {"planlayici": "planlayici", END: END},
)

app = workflow.compile()


if __name__ == "__main__":
    print("\n[🚀] Multi-Agent Seyahat Sistemi (yapılandırılmış state)\n")
    config = {"configurable": {"thread_id": "multi_agent_travel_v2"}}

    session_path = os.getenv("SEYAHAT_SESSION_PATH", DEFAULT_SESSION)
    baslangic = {"messages": [], "session_config_path": session_path, **bootstrap_from_session(session_path)}

    print(f"Oturum: {session_path}\n" + "-" * 50)
    sonuc = app.invoke(baslangic, config=config)

    if sonuc.get("hata_durumu"):
        print("\n=== HATA (akış durduruldu) ===")
        print(sonuc["hata_durumu"])
    else:
        print("\n=== KATILIMCI BİLGİLERİ ===")
        for k in sonuc.get("katilimci_bilgileri", []):
            print(f"  {k['isim']}: {k['kalkis_sehri']} (bütçe: {k['butce']})")

        print("\n=== ORTAK BOŞ ZAMANLAR ===")
        for slot in sonuc.get("ortak_bos_zamanlar", []):
            print(f"  • {slot.get('metin', slot)}")

        print("\n=== LOJİSTİK PLANI (araç tabanlı) ===")
        for isim, plan in (sonuc.get("lojistik_plani") or {}).items():
            print(
                f"  {isim}: {plan.get('cikis_saat_metin')} → "
                f"{plan.get('tahmini_varis_saat_metin')} ({plan.get('sure_metin')})"
            )

        pencere = sonuc.get("ortak_bulusma_penceresi") or {}
        print("\n=== ORTAK BULUŞMA ===")
        print(pencere.get("metin", pencere))
        for aks in pencere.get("erken_gelen_aksiyonlari", []):
            print(f"  ⏳ {aks['isim']}: {aks['aksiyon']}")

        print("\n=== REVIEWER ===")
        print(sonuc.get("hata_mesaji") or "ONAY")

        print("\n" + "=" * 70)
        print("=== NİHAİ PLAN ===")
        print("=" * 70 + "\n")
        print(sonuc.get("nihai_plan", ""))

    if os.getenv("LANGSMITH_TRACING"):
        print("\n(i) LangSmith izleme aktif.")
