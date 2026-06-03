"""LangSmith izleme — multi-agent graf ve araç çağrıları için bağlam yayılımı."""

from __future__ import annotations

import os
from typing import Any

from langchain_core.runnables.config import ensure_config
from langchain_core.tools import BaseTool


def setup_langsmith() -> None:
    """LANGSMITH_* değişkenlerini LangChain tracer ile senkronize eder."""
    if os.getenv("LANGSMITH_TRACING", "").lower() in ("true", "1", "yes"):
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")

    for src, dst in (
        ("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"),
        ("LANGSMITH_ENDPOINT", "LANGCHAIN_ENDPOINT"),
        ("LANGSMITH_PROJECT", "LANGCHAIN_PROJECT"),
    ):
        val = (os.getenv(src) or "").strip().strip('"').strip("'")
        if val and not os.getenv(dst):
            os.environ[dst] = val


def invoke_tool(tool: BaseTool, args: dict[str, Any], config: Any | None = None) -> Any:
    """Araç çağrısını aktif LangGraph/LangSmith bağlamına bağlar."""
    return tool.invoke(args, config=ensure_config(config))


def trace_config(
    thread_id: str,
    *,
    run_name: str = "Multi-Agent Seyahat",
    session_path: str = "",
) -> dict[str, Any]:
    """app.invoke için LangSmith metadata içeren config."""
    return {
        "configurable": {"thread_id": thread_id},
        "run_name": run_name,
        "tags": ["multi-agent", "seyahat"],
        "metadata": {
            "pipeline": "multi_agent",
            "session_path": session_path,
        },
    }
