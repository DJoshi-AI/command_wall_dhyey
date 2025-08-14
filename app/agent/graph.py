import os
import re
import operator
import json
from typing import TypedDict, List, Annotated, Dict, Any

from urllib.parse import urlsplit, urlunsplit
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from langchain_core.messages import AnyMessage, SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from langchain_ollama import ChatOllama

from app.services.dummy_services import VALID_CLIENT_ID
from app.agent.agent_tools import all_tools


class AgentState(TypedDict):
    messages: Annotated[List[AnyMessage], operator.add]
    client_id: str


class GraphWrapper:
    def __init__(
        self,
        model_name: str | None = None,
        base_url: str | None = None,
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
        # Default to a tool-capable model
        model_name = model_name or os.getenv("OLLAMA_MODEL_NAME", "qwen2.5:7b-instruct")

        print(f"[GraphWrapper] Using Ollama base_url: {base_url}")
        print(f"[GraphWrapper] Using model: {model_name}")

        if not self._preflight_ollama(base_url):
            raise ImportError(f"Cannot reach Ollama at {base_url}. Is it running?")

        if not self._model_exists(base_url, model_name):
            raise ImportError(
                f'Ollama model "{model_name}" not found on {base_url}. '
                f'Run: ollama pull {model_name}'
            )

        try:
            self.llm = ChatOllama(
                model=model_name,
                base_url=base_url,
                temperature=temperature,
                top_k=top_k,
                top_p=top_p,
                num_ctx=num_ctx,
            )
        except Exception as e:
            print(f"Error initializing ChatOllama at {base_url}: {e}")
            raise ImportError("Failed to initialize ChatOllama.")

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
        except URLError as e:
            print(f"[GraphWrapper] Ollama preflight failed for {base_url}: {e}")
            return False
        except Exception as e:
            print(f"[GraphWrapper] Unexpected preflight error for {base_url}: {e}")
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
        except HTTPError as e:
            if e.code == 404:
                return False
            print(f"[GraphWrapper] /api/show error ({e.code}) for {model_name}: {e}")
            return False
        except Exception as e:
            print(f"[GraphWrapper] Model check failed for {model_name}: {e}")
            return False

    def _build_graph(self):
        system_prompt = f"""You are a helpful assistant for a SaaS company, designed to analyze business performance data. Your goal is to provide accurate information based on the user's query about a client account.

- When a user asks a question that requires data (e.g., "show me KPIs" or "what's our churn trend?"), you MUST have a client_id to use the tools.
- The client_id is a hex string. The only valid one for this demo is {VALID_CLIENT_ID}.
- If the user provides a client ID, use it for the tool calls.
- If the client_id is NOT in the conversation history and the user's query requires it, you MUST ask the user for the client_id. Do NOT try to guess or use a placeholder.
- If the user provides an invalid client_id, the tools will return an empty response. You must inform the user that the data is not available for that ID.
- For general conversation (e.g., "hello", "what can you do?"), respond directly without using tools.
- Use the available tools to answer questions about SaaS KPI summaries, detailed data, business anomalies, and KPI trends."""
        
        llm_with_tools = self.llm.bind_tools(all_tools)

        def agent_node(state: AgentState):
            messages_with_system_prompt = [SystemMessage(content=system_prompt)] + state['messages']
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

    def _extract_client_id(self, text: str) -> str | None:
        match = re.search(r'\b([a-fA-F0-9]{8,})\b', text)
        return match.group(1) if match else None

    def invoke(self, query: str, history: List[Dict[str, Any]]):
        messages = [
            HumanMessage(content=m["content"]) if m["type"] == "human" else AIMessage(content=m["content"])
            for m in history
        ]
        messages.append(HumanMessage(content=query))
        messages = messages[-10:]

        client_id = ""
        for msg in reversed(messages):
            extracted_id = self._extract_client_id(str(msg.content))
            if extracted_id:
                client_id = extracted_id
                break

        thread_id = "user_session_123"
        config = {"configurable": {"thread_id": thread_id}}
        
        final_state = self.graph.invoke({"messages": messages, "client_id": client_id}, config=config)

        final_messages = final_state.get("messages", [])
        answer = (
            final_messages[-1].content
            if final_messages and not getattr(final_messages[-1], "tool_calls", None)
            else "Sorry, I encountered an issue. Could you rephrase?"
        )

        updated_history_dicts = []
        for msg in final_messages:
            if isinstance(msg, HumanMessage):
                updated_history_dicts.append({"type": "human", "content": msg.content})
            elif isinstance(msg, AIMessage):
                updated_history_dicts.append({"type": "ai", "content": msg.content})
        return answer, updated_history_dicts