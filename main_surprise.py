"""LangGraph akışı — iki arkadaş: Akhisar / Ankara → Antalya."""

import os

from dotenv import load_dotenv

load_dotenv()

from travel_graph import surprise_visit_agent

if __name__ == "__main__":
    print("\n[!] Kişisel Asistan — LangGraph (Takvim → Planlayıcı → Review)\n")
    config = {"configurable": {"thread_id": "antalya_surprise_v2"}}

    user_query_1 = (
        "Ben Manisa Akhisar'dan, en yakın arkadaşım Ankara'dan yola çıkacak. "
        "İkimiz de kızız; uzun zamandır görüşemediğimiz için bu hafta sonu Antalya'da buluşmak istiyoruz. "
        "Benim cuma günü saat 17:00'ye kadar mesaim var, arkadaşımın cuma günü boş. "
        "Cuma akşamı yola çıkacak şekilde, Antalya'daki hava durumuna uygun, "
        "cumartesi ve pazarı kapsayan detaylı bir plan hazırlar mısın? Bütçemiz orta."
    )

    print(f"1. İSTEK:\n{user_query_1}\n" + "-" * 50)

    result = surprise_visit_agent.invoke(
        {"messages": [("user", user_query_1)]},
        config,
    )

    print("\n=== ORTAK BOŞ ZAMANLAR (Python) ===")
    for slot in result.get("ortak_bos_zamanlar", []):
        metin = slot.get("metin", slot) if isinstance(slot, dict) else slot
        print(f"  • {metin}")

    print("\n=== LOKASYONLAR ===")
    print(result.get("kullanici_lokasyonlari"))

    print("\n=== NİHAİ PLAN (Review) ===\n")
    print(result.get("plan_taslagi") or result["messages"][-1].content)
    print(f"\nOnaylandı: {result.get('onaylandi')}")

    print("\n" + "=" * 70 + "\n")

    user_query_2 = (
        "Plan harika ama cumartesi akşam yemeğinden sonra deniz manzaralı, "
        "sakin bir tatlıcı veya kafe ekleyelim; arkadaşımla sohbet edip geç saate kadar "
        "vakit geçirmek istiyoruz. Saatleri buna göre günceller misin?"
    )

    print(f"2. İSTEK (HAFIZA):\n{user_query_2}\n" + "-" * 50)

    result_2 = surprise_visit_agent.invoke(
        {"messages": [("user", user_query_2)]},
        config,
    )

    print("\n=== GÜNCELLENMİŞ PLAN ===\n")
    print(result_2.get("plan_taslagi") or result_2["messages"][-1].content)

    if os.getenv("LANGSMITH_TRACING"):
        print("\n(i) LangSmith izleme aktif.")
