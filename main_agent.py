import os

from dotenv import load_dotenv

load_dotenv()

from session_config import DEFAULT_SESSION_PATH
from single_agent_graph import single_agent

# ==========================================
# TEK AJAN — DİNAMİK OTURUM + StateGraph
# ==========================================

if __name__ == "__main__":
    print("\n[!] Dinamik Seyahat Ajanı (StateGraph + JSON oturum)\n")
    config = {"configurable": {"thread_id": "dynamic_travel_v1"}}

    initial_state = {
        "session_config_path": str(DEFAULT_SESSION_PATH),
        "messages": [],
    }

    user_query_1 = (
        "Ben Manisa Akhisar'dan, en yakın arkadaşım Ankara'dan yola çıkacak. "
        "İkimiz de kızız; uzun zamandır görüşemediğimiz için bu hafta sonu Antalya'da buluşmak istiyoruz. "
        "Benim cuma günü saat 17:00'ye kadar mesaim var, arkadaşımın cuma günü boş. "
        "Cuma akşamı yola çıkacak şekilde, Antalya'daki hava durumuna uygun, "
        "cumartesi ve pazarı kapsayan detaylı bir plan hazırlar mısın? Bütçemiz orta."
    )

    print(f"Oturum: {DEFAULT_SESSION_PATH}")
    print(f"\n1. İSTEK: {user_query_1}\n" + "-" * 50)

    response_1 = single_agent.invoke(
        {**initial_state, "messages": [("user", user_query_1)]},
        config,
    )

    print("\n=== KATILIMCI BAĞLAMI (state) ===")
    print(response_1.get("kullanici_baglami", "")[:500], "...")

    print("\n=== NİHAİ PLAN ===\n" + response_1["messages"][-1].content)

    print("\n" + "=" * 70 + "\n")

    user_query_2 = (
        "Plan harika ama cumartesi akşam yemeğinden sonra deniz manzaralı, "
        "sakin bir tatlıcı veya kafe ekleyelim; arkadaşımla sohbet edip geç saate kadar "
        "vakit geçirmek istiyoruz. Saatleri buna göre günceller misin?"
    )

    print(f"2. İSTEK (HAFIZA): {user_query_2}\n" + "-" * 50)

    response_2 = single_agent.invoke(
        {"messages": [("user", user_query_2)]},
        config,
    )

    print("\n=== GÜNCELLENMİŞ PLAN ===\n" + response_2["messages"][-1].content)

    if os.getenv("LANGSMITH_TRACING"):
        print("\n(i) LangSmith izleme aktif.")
