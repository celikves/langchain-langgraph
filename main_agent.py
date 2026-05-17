import os

from dotenv import load_dotenv

load_dotenv()

from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from prompts import SCENARIO_DEFAULTS, build_prompt_template
from tools import agent_tools

# ==========================================
# ANA ETMEN VE MİMARİ KURULUMU
# ==========================================

llm = ChatOllama(model="qwen2.5:7b", temperature=0)
memory = MemorySaver()
prompt_template = build_prompt_template()

agent_executor = create_react_agent(
    llm,
    agent_tools,
    checkpointer=memory,
)

# ==========================================
# ANA AKIŞ VE HAFIZA TESTİ
# ==========================================

if __name__ == "__main__":
    print("\n[!] Akıllı Seyahat Ajanı Başlatılıyor... (LangSmith İzlemesi Aktif)\n")
    config = {"configurable": {"thread_id": "travel_project_v6"}}

    user_query_1 = (
        "Ben Manisa Akhisar'dan, en yakın arkadaşım Ankara'dan yola çıkacak. "
        "İkimiz de kızız; uzun zamandır görüşemediğimiz için bu hafta sonu Antalya'da buluşmak istiyoruz. "
        "Benim cuma günü saat 17:00'ye kadar mesaim var, arkadaşımın cuma günü boş. "
        "Cuma akşamı yola çıkacak şekilde, Antalya'daki hava durumuna uygun, "
        "cumartesi ve pazarı kapsayan detaylı bir plan hazırlar mısın? Bütçemiz orta."
    )

    print(f"1. İSTEK: {user_query_1}\n" + "-" * 50)

    messages_1 = prompt_template.format_messages(
        messages=[("user", user_query_1)],
        **SCENARIO_DEFAULTS,
    )

    response_1 = agent_executor.invoke({"messages": messages_1}, config)

    print("\n=== NİHAİ PLAN ===\n" + response_1["messages"][-1].content)

    print("\n" + "=" * 70 + "\n")

    user_query_2 = (
        "Plan harika ama cumartesi akşam yemeğinden sonra deniz manzaralı, "
        "sakin bir tatlıcı veya kafe ekleyelim; arkadaşımla sohbet edip geç saate kadar "
        "vakit geçirmek istiyoruz. Saatleri buna göre günceller misin?"
    )

    print(f"2. İSTEK (HAFIZA TESTİ): {user_query_2}\n" + "-" * 50)

    response_2 = agent_executor.invoke(
        {"messages": [("user", user_query_2)]},
        config,
    )

    print("\n=== GÜNCELLENMİŞ PLAN ===\n" + response_2["messages"][-1].content)

    if os.getenv("LANGSMITH_TRACING"):
        print("\n(i) LangSmith izleme aktif.")
