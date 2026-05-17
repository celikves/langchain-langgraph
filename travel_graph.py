"""LangGraph: Takvim → Planlayıcı → İnceleme (Akhisar–Ankara–Antalya)."""

from __future__ import annotations

import json

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from calendar_logic import find_common_free_slots, load_calendars, summarize_calendars_for_llm
from graph_prompts import REVIEW_SYSTEM_PROMPT, format_planner_system_prompt
from session_config import build_session_context
from state import SeyahatState
from tools import surprise_visit_tools

load_dotenv()

llm = ChatOllama(model="qwen2.5:7b", temperature=0)
llm_with_tools = llm.bind_tools(surprise_visit_tools)
tool_node = ToolNode(surprise_visit_tools)


def calendar_node(state: SeyahatState) -> dict:
    """Saf Python — LLM takvim okumaz."""
    data = load_calendars()
    slots = find_common_free_slots(data)
    slot_metinleri = [s["metin"] for s in slots]
    ozet = summarize_calendars_for_llm(data)

    kisiler = data["kisiler"]
    hedef = data["meta"].get("hedef_sehir", "Antalya")
    lokasyonlar = {
        "katilimcilar": [
            {"ad": k["ad"], "sehir": k["sehir"], "rol": k.get("rol", key)}
            for key, k in kisiler.items()
        ],
        "bulusma_noktasi": hedef,
    }

    return {
        "ortak_bos_zamanlar": slot_metinleri,
        "kullanici_lokasyonlari": lokasyonlar,
        "secilen_hedef": hedef,
        "takvim_ozeti": ozet,
        "messages": [
            AIMessage(
                content=(
                    "Takvim düğümü tamamlandı.\n\n"
                    f"{ozet}\n\n"
                    f"Buluşma hedefi: {hedef}. Planlayıcı senkronizasyon ve trafik araçlarını kullanabilir."
                )
            )
        ],
    }


def planner_node(state: SeyahatState) -> dict:
    bos = state.get("ortak_bos_zamanlar") or []
    lok = state.get("kullanici_lokasyonlari") or {}
    hedef = state.get("secilen_hedef", "Antalya")

    context = (
        f"Buluşma hedefi: {hedef}\n"
        f"Lokasyonlar: {json.dumps(lok, ensure_ascii=False)}\n"
        f"Ortak boş zamanlar (Python): {', '.join(bos) if bos else 'yok'}\n"
        f"Mesai kısıtı: hafta içi 08:00–17:00 arası seyahat/etkinlik YASAK.\n"
        f"Takvim özeti:\n{state.get('takvim_ozeti', '')}"
    )

    if state.get("plan_taslagi") and not state.get("onaylandi"):
        context += f"\n\nÖnceki Review geri bildirimi (düzelt):\n{state['plan_taslagi']}"

    user_msgs = [m for m in state.get("messages", []) if isinstance(m, HumanMessage)]
    last_user = user_msgs[-1].content if user_msgs else "Antalya buluşma planı oluştur."

    session_ctx = build_session_context()
    planner_system = format_planner_system_prompt(
        hedef_sehir=hedef,
        kullanici_baglami=session_ctx["kullanici_baglami"],
    )
    response = llm_with_tools.invoke(
        [
            SystemMessage(content=planner_system),
            HumanMessage(content=f"{context}\n\nKullanıcı isteği:\n{last_user}"),
        ]
    )
    return {"messages": [response]}


def should_continue_planner(state: SeyahatState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "review"


def review_node(state: SeyahatState) -> dict:
    bos = state.get("ortak_bos_zamanlar") or []
    plan_parts = []
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, AIMessage) and msg.content and "Takvim düğümü" not in (msg.content or ""):
            plan_parts.append(msg.content)
        if len(plan_parts) >= 3:
            break

    plan_metni = "\n---\n".join(reversed(plan_parts)) if plan_parts else "Plan üretilemedi."

    review_input = (
        f"Ortak boş zamanlar: {bos}\n"
        f"Hedef: {state.get('secilen_hedef', 'Antalya')}\n"
        f"Lokasyonlar: {json.dumps(state.get('kullanici_lokasyonlari', {}), ensure_ascii=False)}\n\n"
        f"Ara plan / araç çıktıları:\n{plan_metni}"
    )

    response = llm.invoke(
        [
            SystemMessage(content=REVIEW_SYSTEM_PROMPT),
            HumanMessage(content=review_input),
        ]
    )

    content = response.content or ""
    reddedildi = content.strip().upper().startswith("RED")
    onaylandi = not reddedildi and (
        "uygun" in content.lower() or "onay" in content.lower() or "nihai" in content.lower()
    )

    retries = state.get("review_retries", 0)
    if reddedildi:
        retries += 1

    return {
        "plan_taslagi": content,
        "onaylandi": onaylandi,
        "review_retries": retries,
        "messages": [response],
    }


def should_after_review(state: SeyahatState) -> str:
    if state.get("onaylandi"):
        return "end"
    if state.get("review_retries", 0) <= 1:
        return "planner"
    return "end"


def build_surprise_visit_graph(*, checkpointer=None):
    graph = StateGraph(SeyahatState)
    graph.add_node("calendar", calendar_node)
    graph.add_node("planner", planner_node)
    graph.add_node("tools", tool_node)
    graph.add_node("review", review_node)

    graph.add_edge(START, "calendar")
    graph.add_edge("calendar", "planner")
    graph.add_conditional_edges("planner", should_continue_planner, {"tools": "tools", "review": "review"})
    graph.add_edge("tools", "planner")
    graph.add_conditional_edges("review", should_after_review, {"planner": "planner", "end": END})

    return graph.compile(checkpointer=checkpointer or MemorySaver())


surprise_visit_agent = build_surprise_visit_graph()
