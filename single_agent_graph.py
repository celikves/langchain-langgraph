"""Tek ajan: bootstrap (JSON/state enjeksiyonu) → ReAct döngüsü (araçlar)."""

from __future__ import annotations

from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from prompts import build_prompt_template
from session_config import DEFAULT_SESSION_PATH, build_session_context
from state import AsistanState
from tools import agent_tools

load_dotenv()

llm = ChatOllama(model="qwen2.5:7b", temperature=0)
llm_with_tools = llm.bind_tools(agent_tools)
tool_node = ToolNode(agent_tools)
prompt_template = build_prompt_template()


def bootstrap_node(state: AsistanState) -> dict:
    """JSON oturum + profiller + takvim → state ve prompt alanları."""
    if state.get("bootstrapped"):
        return {}

    session_path = state.get("session_config_path") or str(DEFAULT_SESSION_PATH)
    ctx = build_session_context(session_path)

    return {
        "bootstrapped": True,
        "session_config_path": session_path,
        **{k: ctx[k] for k in ctx if k != "session_id"},
    }


def agent_node(state: AsistanState) -> dict:
    """State'teki değişkenlerle ChatPromptTemplate render → LLM."""
    formatted = prompt_template.format_messages(
        ana_gorev=state.get("ana_gorev", ""),
        kullanici_baglami=state.get("kullanici_baglami", ""),
        zaman_kisitlamalari=state.get("zaman_kisitlamalari", ""),
        ortak_kisitlamalar=state.get("ortak_kisitlamalar", ""),
        is_akis_adimlari=state.get("is_akis_adimlari", ""),
        ozel_kurallar=state.get("ozel_kurallar", ""),
        messages=state.get("messages", []),
    )
    response = llm_with_tools.invoke(formatted)
    return {"messages": [response]}


def route_after_start(state: AsistanState) -> str:
    return "agent" if state.get("bootstrapped") else "bootstrap"


def route_after_agent(state: AsistanState) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return END


def build_single_agent_graph(*, checkpointer=None):
    graph = StateGraph(AsistanState)
    graph.add_node("bootstrap", bootstrap_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    graph.add_conditional_edges(
        START,
        route_after_start,
        {"bootstrap": "bootstrap", "agent": "agent"},
    )
    graph.add_edge("bootstrap", "agent")
    graph.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile(checkpointer=checkpointer or MemorySaver())


single_agent = build_single_agent_graph()
