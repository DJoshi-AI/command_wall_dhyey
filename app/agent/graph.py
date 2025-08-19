#graph.py
import os
import re
import operator
import json
from typing import TypedDict, List, Annotated, Dict, Any, Optional

from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from langchain_ollama import ChatOllama

from app.agent.agent_tools import all_tools
from app.services.mongo import (
    get_active_client_id,
    set_active_client_id,
    add_message,
    get_messages,
)


def prefer_new_nonempty(x: str, y: str) -> str:
    return y if (y and y.strip()) else x


class AgentState(TypedDict):
    messages: Annotated[List[AnyMessage], operator.add]
    client_id: Annotated[str, prefer_new_nonempty]


class GraphWrapper:
    def _init_(
        self,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.2,
        top_k: int = 30,
        top_p: float = 0.9,
        num_ctx: int = 8192,
    ):
        base_url = self._resolve_base_url(
            base_url
            or os.getenv("OLLAMA_BASE_URL")
            or os.getenv("OLLAMA_HOST")
            or "http://127.0.0.1:11434"
        )
        model_name = model_name or os.getenv("OLLAMA_MODEL_NAME", "qwen2.5:7b-instruct")

        print(f"[GraphWrapper] Using Ollama base_url: {base_url}")
        print(f"[GraphWrapper] Using model: {model_name}")

        if not self._preflight_ollama(base_url):
            raise ImportError(f"Cannot reach Ollama at {base_url}. Is it running?")

        if not self._model_exists(base_url, model_name):
            raise ImportError(
                f'Ollama model "{model_name}" not found on {base_url}. Run: ollama pull {model_name}'
            )

        self.llm = ChatOllama(
            model=model_name,
            base_url=base_url,
            temperature=temperature,
            top_k=top_k,
            top_p=top_p,
            num_ctx=num_ctx,
        )

        self.memory = MemorySaver()
        self.graph = self._build_graph()

    def _resolve_base_url(self, candidate: str) -> str:
        if not candidate.startswith(("http://", "https://")):
            candidate = "http://" + candidate
        parts = urlsplit(candidate)
        scheme = parts.scheme or "http"
        host = parts.hostname or "127.0.0.1"
        if host in {"0.0.0.0", "::", "[::]"}:
            host = "127.0.0.1"
        port = parts.port or 11434
        netloc = f"{host}:{port}"
        return urlunsplit((scheme, netloc, "", "", ""))

    def _preflight_ollama(self, base_url: str) -> bool:
        try:
            with urlopen(f"{base_url}/api/tags", timeout=3) as resp:
                return 200 <= resp.status < 300
        except Exception as e:
            print(f"[GraphWrapper] Ollama preflight failed for {base_url}: {e}")
            return False

    def _model_exists(self, base_url: str, model_name: str) -> bool:
        try:
            req = Request(
                f"{base_url}/api/show",
                data=json.dumps({"name": model_name}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(req, timeout=5) as resp:
                return 200 <= resp.status < 300
        except Exception:
            return False

    def _build_graph(self):
        system_prompt = """You are a helpful assistant for a SaaS company, designed to analyze business performance data.
- When a user asks for data (e.g., KPIs, churn, trends), you MUST provide a client_id to the tools.
- If a client_id is not known and the request requires one, ask the user for the client_id.
- Reuse the last active client_id for the session unless the user specifies a new one.
- If the provided client_id is invalid or unknown, inform the user and ask for a valid one.
- For general chit-chat, respond directly without using tools.
- Use the available tools to answer questions about KPI summaries, detailed data, anomalies, and KPI trends.
- Always include the client_id argument in tool calls that require it."""

        llm_with_tools = self.llm.bind_tools(all_tools)

        def agent_node(state: AgentState):
            messages_with_system_prompt = [SystemMessage(content=system_prompt)]
            if state.get("client_id"):
                messages_with_system_prompt.append(
                    SystemMessage(content=f"Active client_id for this session: {state['client_id']}")
                )
            messages_with_system_prompt += state["messages"]
            response = llm_with_tools.invoke(messages_with_system_prompt)
            return {"messages": [response]}

        tool_node = ToolNode(all_tools)

        def router(state: AgentState) -> str:
            last_message = state["messages"][-1]
            if getattr(last_message, "tool_calls", None):
                return "call_tools"
            return "end"

        graph = StateGraph(AgentState)
        graph.add_node("agent", agent_node)
        graph.add_node("tools", tool_node)
        graph.set_entry_point("agent")
        graph.add_conditional_edges("agent", router, {"call_tools": "tools", "end": END})
        graph.add_edge("tools", "agent")
        return graph.compile(checkpointer=self.memory)

    def _extract_client_id(self, text: str) -> Optional[str]:
        # Allow IDs like "client1" as well as hex-like IDs
        match = re.search(r"\b([A-Za-z0-9_\-]{4,})\b", text)
        return match.group(1) if match else None

    def invoke(
        self,
        query: str,
        history: List[Dict[str, Any]],
        client_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        session_key = session_id or "default_session"

        # Rebuild messages from provided history (backward compatible)
        messages: List[AnyMessage] = []
        for m in history:
            if m.get("type") == "human":
                messages.append(HumanMessage(content=m["content"]))
            elif m.get("type") == "ai":
                messages.append(AIMessage(content=m["content"]))
        messages.append(HumanMessage(content=query))
        messages = messages[-10:]

        # Determine effective client_id (param > stored session > inferred)
        effective_client_id = (
            (client_id or "").strip()
            or get_active_client_id(session_key)
            or self._extract_client_id(" ".join(str(m.content) for m in messages))
            or ""
        )

        # Persist active client_id if present
        if effective_client_id:
            set_active_client_id(session_key, effective_client_id)

        # Persist incoming human message in Mongo
        add_message(session_key, "human", query)

        # Invoke graph
        final_state = self.graph.invoke(
            {"messages": messages, "client_id": effective_client_id},
            config={"configurable": {"thread_id": session_key}},
        )

        final_messages = final_state.get("messages", [])
        answer = (
            final_messages[-1].content
            if final_messages and not getattr(final_messages[-1], "tool_calls", None)
            else "Sorry, I encountered an issue. Could you rephrase?"
        )

        # Persist AI reply
        add_message(session_key, "ai", answer)

        # Return updated history like before
        updated_history_dicts: List[Dict[str, str]] = []
        for msg in final_messages:
            if isinstance(msg, HumanMessage):
                updated_history_dicts.append({"type": "human", "content": msg.content})
            elif isinstance(msg, AIMessage):
                updated_history_dicts.append({"type": "ai", "content": msg.content})

        return answer, updated_history_dicts