import os
from dotenv import load_dotenv

load_dotenv()

from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from tools import agent_tools

# ==========================================
# MAIN AGENT SETUP
# ==========================================

llm = ChatOllama(model="qwen2.5:7b", temperature=0)
memory = MemorySaver()

system_prompt = """Sen üst düzey, otonom bir seyahat asistanısın. Asla kullanıcıya 'araştırabilirsiniz' veya 'bulabilirsiniz' gibi tavsiyelerde bulunma. İşi SEN yapmalısın.

Şu adımları KESİN bir sırayla izle:
1. 'calculate_distance_and_duration' aracı ile lojistiği çıkar.
2. 'get_weather_forecast' aracı ile hedef tarihteki hava verisini al.
3. KESİNLİKLE 'search_places_online' aracını ÇALIŞTIR. Sorguya hava durumunu ve bütçeyi dahil et (Örn: 'Bursa yağmurlu hava ucuz kapalı restoranlar').
4. Araçtan dönen sonuçların içindeki GERÇEK MEKAN İSİMLERİNİ (Örn: X Restoranı, Y Müzesi) alarak saat saat bir program oluştur.

Eğer spesifik bir mekan ismi vermiyorsan, görevde başarısız olmuş sayılırsın."""

agent_executor = create_react_agent(
    llm,
    agent_tools,
    checkpointer=memory,
)

# ==========================================
# MAIN FLOW AND TEST
# ==========================================

if __name__ == "__main__":
    print("\n[!] Akıllı Seyahat Ajanı Başlatılıyor... (LangSmith İzlemesi Aktif)\n")
    config = {"configurable": {"thread_id": "travel_project_v4"}}

    user_query_1 = (
        "Hafta sonu arkadaşımla buluşacağım. Ben İstanbul'dan, o ise İzmir'den gelecek ve "
        "ortak nokta olarak Bursa'da buluşmaya karar verdik. Bütçemiz 'düşük'. "
        "23 Mayıs 2026 tarihi için bize hava durumuna da uygun sabahtan akşama bir plan yapar mısın?"
    )

    print(f"1. İSTEK: {user_query_1}\n" + "-" * 50)

    response_1 = agent_executor.invoke(
        {
            "messages": [
                ("system", system_prompt),
                ("user", user_query_1),
            ]
        },
        config,
    )

    print("\n=== NİHAİ PLAN ===\n" + response_1["messages"][-1].content)

    print("\n" + "=" * 70 + "\n")

    user_query_2 = "Peki bu plana akşam yemeği için bir de tatlıcı ekler misin?"
    print(f"2. İSTEK (HAFIZA TESTİ): {user_query_2}\n" + "-" * 50)

    response_2 = agent_executor.invoke(
        {
            "messages": [
                ("user", user_query_2),
            ]
        },
        config,
    )

    print("\n=== GÜNCELLENMİŞ PLAN ===\n" + response_2["messages"][-1].content)
