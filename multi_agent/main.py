import os
import sys
from pathlib import Path

from langgraph.graph import END, START, StateGraph

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from multi_agent.tracing import setup_langsmith, trace_config

setup_langsmith()

from multi_agent.agents import lojistik_node, planlayici_node, reviewer_node
from multi_agent.bootstrap import bootstrap_from_session, bootstrap_node
from multi_agent.kesif_subgraph import kesif_subgraph
from multi_agent.state import SeyahatState
from multi_agent.supervisor import supervisor_node, supervisor_router

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
    return "supervisor"


workflow = StateGraph(SeyahatState)

workflow.add_node("bootstrap", bootstrap_node)
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("lojistik", lojistik_node)
workflow.add_node("kesif", kesif_subgraph)
workflow.add_node("planlayici", planlayici_node)
workflow.add_node("reviewer", reviewer_node)

workflow.add_edge(START, "bootstrap")
workflow.add_conditional_edges(
    "bootstrap",
    _halt_router,
    {END: END, "supervisor": "supervisor"},
)
workflow.add_conditional_edges(
    "supervisor",
    supervisor_router,
    {
        "lojistik": "lojistik",
        "kesif": "kesif",
        "planlayici": "planlayici",
        END: END,
    },
)
workflow.add_edge("lojistik", "supervisor")
workflow.add_edge("kesif", "supervisor")
workflow.add_edge("planlayici", "reviewer")
workflow.add_edge("reviewer", "supervisor")

app = workflow.compile(name="Multi-Agent Seyahat Pipeline")


if __name__ == "__main__":
    print("\n[🚀] Multi-Agent Seyahat Sistemi (yapılandırılmış state)\n")
    session_path = os.getenv("SEYAHAT_SESSION_PATH", DEFAULT_SESSION)
    config = trace_config(
        "multi_agent_travel_v2",
        run_name="Multi-Agent Seyahat Run",
        session_path=session_path,
    )
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
        kalite = sonuc.get("kalite_raporu") or {}
        print(sonuc.get("hata_mesaji") or "ONAY")
        if kalite.get("eksik_turler"):
            print(f"  Eksik türler: {', '.join(kalite['eksik_turler'])}")
        siradaki = sonuc.get("siradaki_ajan")
        if siradaki:
            print(f"  Akış: {siradaki} (revizyon: {sonuc.get('revizyon_sayisi', 0)})")

        print("\n" + "=" * 70)
        print("=== NİHAİ PLAN ===")
        print("=" * 70 + "\n")
        print(sonuc.get("nihai_plan", ""))

    if os.getenv("LANGSMITH_TRACING") or os.getenv("LANGCHAIN_TRACING_V2"):
        project = os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT") or "?"
        print(f"\n(i) LangSmith izleme aktif — proje: {project}")
