import os

from langgraph.graph import StateGraph, START, END
from state import SeyahatState
from agents import lojistik_node, kesif_node, planlayici_node, reviewer_node

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

# ==========================================
# 1. GRAPH'IN (AKISIN) İNŞASI
# ==========================================

# State (Hafıza) sınıfımızı baz alan bir grafik başlatıyoruz
workflow = StateGraph(SeyahatState)

# Düğümleri (Ajanları) ekliyoruz
workflow.add_node("lojistik", lojistik_node)
workflow.add_node("kesif", kesif_node)
workflow.add_node("planlayici", planlayici_node)
workflow.add_node("reviewer", reviewer_node)

# Kenarları (Akış Sırasını) bağlıyoruz
workflow.add_edge(START, "lojistik")        # Başlangıç -> Lojistik Ajanı
workflow.add_edge("lojistik", "kesif")      # Lojistik Ajanı -> Keşif Ajanı
workflow.add_edge("kesif", "planlayici")    # Keşif Ajanı -> Planlayıcı Ajan
workflow.add_edge("planlayici", "reviewer")  # Planlayıcı -> Reviewer


def reviewer_router(state: SeyahatState):
    if state.get("siradaki_ajan") == "yeniden_planla" and state.get("revizyon_sayisi", 0) < 2:
        return "planlayici"
    return END


workflow.add_conditional_edges(
    "reviewer",
    reviewer_router,
    {"planlayici": "planlayici", END: END},
)

# Sistemi derleyip çalıştırılabilir hale getiriyoruz
app = workflow.compile()

# ==========================================
# 2. ÇALIŞTIRMA VE TEST
# ==========================================

if __name__ == "__main__":
    print("\n[🚀] Multi-Agent Seyahat Sistemi Başlatılıyor...\n")
    config = {"configurable": {"thread_id": "multi_agent_travel_v1"}}

    # Sistemin dışarıdan alacağı dinamik bağlamı (JSON mantığıyla) simüle ediyoruz
    baslangic_durumu = {
        "messages": [],
        "kullanici_profilleri": [
            {"isim": "Vesile", "kalkis_yeri": "Akhisar", "mesai_bitis": "17:00", "rol": "Sürprizi organize eden"},
            {"isim": "Kız Arkadaşı", "kalkis_yeri": "Ankara", "mesai_bitis": "Serbest", "rol": "Sürpriz yapılacak kişi"}
        ],
        "ortak_kisitlamalar": "Hedef şehir Antalya. Sürpriz bir hafta sonu tatili. Bütçe: Orta. Cuma günü 17:00 mesai bitişi kesinlikle hesaba katılmalı.",
        "hedef_tarih": "2026-06-04",
        "hata_mesaji": "",
        "siradaki_ajan": "",
        "revizyon_sayisi": 0,
    }

    print("Sistem tek geçiş invoke ile çalıştırılıyor...\n" + "-" * 50)
    sonuc_state = app.invoke(baslangic_durumu, config=config)

    print("\n=== LOJISTIK_VERISI ===")
    print(sonuc_state.get("lojistik_verisi", "Yok"))

    print("\n=== KESIF_VERISI ===")
    print(sonuc_state.get("kesif_verisi", "Yok"))

    print("\n=== REVIEWER_KARARI ===")
    print(sonuc_state.get("hata_mesaji", "ONAY"))

    print("\n" + "=" * 70)
    print("=== 🎯 NİHAİ SÜRPRİZ PLANI ===")
    print("=" * 70 + "\n")
    print(sonuc_state.get("nihai_plan", "Plan oluşturulamadı."))

    if os.getenv("LANGSMITH_TRACING"):
        print("\n(i) LangSmith izleme aktif.")