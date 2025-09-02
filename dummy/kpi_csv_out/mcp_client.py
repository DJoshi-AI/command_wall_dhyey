# mcp_client.py
import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional

# Try multiple MCP client APIs (different versions expose different names)
try:
    from mcp.client.stdio import StdioServerParameters
except Exception as e:
    raise ImportError(f"Could not import StdioServerParameters from mcp.client.stdio: {e}")

_STDIO_CONNECT = None

# Newer API (some versions)
try:
    from mcp.client.stdio import connect as _STDIO_CONNECT  # type: ignore
except Exception:
    pass

# Alternate API name (some versions)
if _STDIO_CONNECT is None:
    try:
        from mcp.client.stdio import connect_stdio_server as _STDIO_CONNECT  # type: ignore
    except Exception:
        pass

# Older/simpler API (some versions)
if _STDIO_CONNECT is None:
    try:
        from mcp.client.stdio import stdio_client as _STDIO_CONNECT  # type: ignore
    except Exception:
        pass

if _STDIO_CONNECT is None:
    raise ImportError(
        "Could not find a stdio connect function in mcp.client.stdio. Try: pip install -U mcp"
    )

from mcp.client.session import ClientSession


def _extract_structured_content(tool_result: Any) -> Any:
    # Best-effort: pull JSON/object content from FastMCP results
    try:
        content = getattr(tool_result, "content", None)
        if isinstance(content, list):
            for item in content:
                t = getattr(item, "type", None) or getattr(item, "kind", None)
                if t in ("json", "object"):
                    data = getattr(item, "data", None) or getattr(item, "value", None)
                    if data is not None:
                        return data
            for item in content:
                t = getattr(item, "type", None) or getattr(item, "kind", None)
                if t == "text":
                    txt = getattr(item, "text", None)
                    if isinstance(txt, str):
                        try:
                            return json.loads(txt)
                        except Exception:
                            return txt
    except Exception:
        pass
    if isinstance(tool_result, (dict, list)):
        return tool_result
    return {"result": tool_result}


async def _with_session(python_exe: str, server_script: str, env: Optional[Dict[str, str]], coro_cb):
    params = StdioServerParameters(command=python_exe, args=[server_script], env=env or {})
    try:
        async with _STDIO_CONNECT(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await coro_cb(session)
    except TypeError:
        # Some old versions accept (command, args, env) directly
        async with _STDIO_CONNECT(params.command, params.args, params.env or {}) as (read, write):  # type: ignore
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await coro_cb(session)


def _run(coro):
    return asyncio.run(coro)


class KPIDataMCPClient:
    def __init__(self, python_exe: Optional[str] = None, server_script: Optional[str] = None, kpi_csv_dir: Optional[str] = None):
        self.python_exe = python_exe or sys.executable
        self.server_script = server_script or os.path.join(os.getcwd(), "mcp_kpi_server.py")
        self.env = {"KPI_CSV_DIR": (kpi_csv_dir or os.getenv("KPI_CSV_DIR", ""))}

    def list_months(self) -> List[str]:
        async def _go(session: ClientSession):
            res = await session.call_tool("list_months", {})
            return _extract_structured_content(res)
        return _run(_with_session(self.python_exe, self.server_script, self.env, _go))

    def list_kpis(self, sample_month: Optional[str] = None, scan_all: bool = True) -> List[str]:
        async def _go(session: ClientSession):
            args: Dict[str, Any] = {"scan_all": bool(scan_all)}
            if sample_month:
                args["sample_month"] = sample_month
            res = await session.call_tool("list_kpis", args)
            return _extract_structured_content(res)
        return _run(_with_session(self.python_exe, self.server_script, self.env, _go))

    def query_kpi_data(self, start_date: str, end_date: str, kpi_name: Optional[str] = None, client_id: Optional[str] = None, limit: int = 1000) -> Dict[str, Any]:
        async def _go(session: ClientSession):
            args: Dict[str, Any] = {"start_date": start_date, "end_date": end_date, "limit": int(limit)}
            if kpi_name:
                args["kpi_name"] = kpi_name
            if client_id:
                args["client_id"] = str(client_id)
            res = await session.call_tool("query_kpi_data", args)
            return _extract_structured_content(res)
        return _run(_with_session(self.python_exe, self.server_script, self.env, _go))