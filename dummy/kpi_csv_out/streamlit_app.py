# streamlit_app.py
import os
import re
import io
import json
import difflib
from typing import List, Dict, Any, Optional, Tuple

import pandas as pd
import streamlit as st
from dateutil.parser import parse as parse_date

from mcp_client import KPIDataMCPClient

st.set_page_config(page_title="KPI Chat (MCP)", page_icon="📊", layout="wide")

# ========= Helpers =========

def ensure_str_list(x) -> List[str]:
    """
    Coerce various MCP tool return shapes (list, dict, CallToolResult) into a list[str].
    """
    try:
        if isinstance(x, list):
            return [str(i) for i in x]
        if isinstance(x, dict):
            if "result" in x and isinstance(x["result"], list):
                return [str(i) for i in x["result"]]
            if "rows" in x and isinstance(x["rows"], list):
                return [str(i) for i in x["rows"]]
        content = getattr(x, "content", None)
        if isinstance(content, list):
            for item in content:
                t = getattr(item, "type", None) or getattr(item, "kind", None)
                if t in ("json", "object"):
                    data = getattr(item, "data", None) or getattr(item, "value", None)
                    if isinstance(data, list):
                        return [str(i) for i in data]
            for item in content:
                t = getattr(item, "type", None) or getattr(item, "kind", None)
                if t == "text":
                    txt = getattr(item, "text", None)
                    if isinstance(txt, str):
                        try:
                            dec = json.loads(txt)
                            if isinstance(dec, list):
                                return [str(i) for i in dec]
                            if isinstance(dec, dict) and "result" in dec and isinstance(dec["result"], list):
                                return [str(i) for i in dec["result"]]
                        except Exception:
                            pass
        if x is None:
            return []
        return [str(x)]
    except Exception:
        return []

def fallback_kpis_from_fs(kpi_dir: str) -> list[str]:
    import glob, csv
    names = set()
    for path in glob.glob(os.path.join(kpi_dir, "kpis_*.csv")):
        try:
            with open(path, "r", encoding="utf-8", newline="") as f:
                r = csv.DictReader(f)
                for row in r:
                    n = (row.get("kpi_name") or "").strip()
                    if n:
                        names.add(n)
        except Exception:
            continue
    return sorted(names)

def parse_query(text: str, known_kpis: List[str]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Parse free text for:
    - two dates (YYYY-MM-DD),
    - approximate KPI name,
    - client_id (client_id=2 or 'for client 2').
    """
    # Dates
    dates = re.findall(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    s, e = (dates[0], dates[1]) if len(dates) >= 2 else (None, None)

    # KPI guess (from known list; dropdown is reference only)
    guess = None
    tokens = re.split(r"[^a-zA-Z0-9_]+", text.lower())
    if known_kpis:
        normalized = {k.lower(): k for k in known_kpis}
        # Try per-token close match
        for t in tokens:
            m = difflib.get_close_matches(t, list(normalized.keys()), n=1, cutoff=0.88)
            if m:
                guess = normalized[m[0]]
                break
        if not guess:
            joined = "_".join([t for t in tokens if t])
            m = difflib.get_close_matches(joined, list(normalized.keys()), n=1, cutoff=0.6)
            if m:
                guess = normalized[m[0]]

    # client_id
    cid = None
    m = re.search(r"\bclient[_\s-]?id[:=]?\s*([A-Za-z0-9_-]+)\b", text, re.I)
    if m:
        cid = m.group(1)
    else:
        m2 = re.search(r"\bfor client\s+([A-Za-z0-9_-]+)\b", text, re.I)
        if m2:
            cid = m2.group(1)

    return s, e, guess, cid

def run_query(client: KPIDataMCPClient, start_date: str, end_date: str, kpi_name: Optional[str], client_id: Optional[str], limit: int) -> Tuple[Dict[str, Any], pd.DataFrame]:
    res = client.query_kpi_data(start_date, end_date, kpi_name=kpi_name, client_id=client_id, limit=limit)
    rows = []
    if isinstance(res, dict) and "rows" in res:
        rows = res["rows"]
    elif isinstance(res, list):
        rows = res
    else:
        rows = res.get("result", []) if isinstance(res, dict) else []
    df = pd.DataFrame(rows)
    return res if isinstance(res, dict) else {"count": len(df), "limit_reached": False}, df

def show_results(df: pd.DataFrame, filename: str):
    st.subheader("Results")
    if df.empty:
        st.info("No rows returned for this query.")
        return
    st.dataframe(df.head(500), use_container_width=True)
    csv_buf = io.StringIO()
    df.to_csv(csv_buf, index=False)
    st.download_button("Download CSV", data=csv_buf.getvalue(), file_name=filename, mime="text/csv")

# ========= Sidebar: MCP Connection =========

st.sidebar.header("MCP Connection")
default_python = os.getenv("PYTHON_EXE", "") or os.sys.executable
python_exe = st.sidebar.text_input("Python executable", value=default_python)
server_script = st.sidebar.text_input("MCP server script", value="C:/dummy/kpi_csv_out/mcp_kpi_server.py")
kpi_dir = st.sidebar.text_input("KPI_CSV_DIR", value=os.getenv("KPI_CSV_DIR", "C:/dummy/kpi_csv_out"))
limit = st.sidebar.number_input("Row limit per query", min_value=50, max_value=100000, value=500, step=50)

# Session state
if "client" not in st.session_state:
    st.session_state.client = None
if "kpi_names" not in st.session_state:
    st.session_state.kpi_names = []
if "months" not in st.session_state:
    st.session_state.months = []
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "text": "Hi! Provide a date range (YYYY-MM-DD .. YYYY-MM-DD) and optionally a KPI name and client_id (e.g., 'on_time_performance 2025-08-02 to 2025-08-15 client_id=2'). I'll fetch via MCP."}]
if "chat_input" not in st.session_state:
    st.session_state.chat_input = ""

def connect_and_cache():
    try:
        client = KPIDataMCPClient(python_exe, server_script, kpi_dir)

        # Months via MCP (for info)
        months = ensure_str_list(client.list_months() or [])

        # Ask MCP server to scan ALL CSVs for KPI names
        kpis = ensure_str_list(client.list_kpis(scan_all=True))

        # Fallback to filesystem if MCP returned empty/too small
        if not kpis or len(kpis) <= 1:
            kpis = fallback_kpis_from_fs(kpi_dir)

        st.session_state.client = client
        st.session_state.months = months
        st.session_state.kpi_names = sorted(set(kpis))

        st.success(
            f"Connected. Months: {', '.join(months) if months else '(none)'} | Loaded KPIs: {len(st.session_state.kpi_names)}"
        )
        if not st.session_state.kpi_names:
            st.info("No KPIs found. Check KPI_CSV_DIR and CSV headers (kpi_name column).")
    except Exception as e:
        st.session_state.client = None
        st.error(f"Connection failed: {e}")

if st.sidebar.button("Test connect & cache KPIs", use_container_width=True):
    connect_and_cache()

st.sidebar.divider()
st.sidebar.caption("Tip: The app launches the MCP server via stdio on each query using the paths above.")

# Auto-connect on first load if possible (optional)
if st.session_state.client is None and os.path.isdir(kpi_dir):
    try:
        connect_and_cache()
    except Exception:
        pass

# ========= Main (Reference-only KPI dropdown + Chat) =========

st.subheader("KPI (optional)")
kpi_options = [""] + ensure_str_list(st.session_state.kpi_names)
kpi_sel = st.selectbox(
    "Reference KPI (dropdown is not applied; use chat to specify KPI)",
    options=kpi_options,
    index=0,
)

# Optional helper: insert selected KPI into chat input (doesn't auto-apply)
ins_col1, ins_col2 = st.columns([1, 6])
with ins_col1:
    if st.button("For reference purpose only", disabled=not kpi_sel):
        prefix = (kpi_sel + " ") if kpi_sel else ""
        current = st.session_state.get("chat_input", "").strip()
        st.session_state.chat_input = (prefix + current).strip()

st.subheader("Chat")
for msg in st.session_state.messages:
    if msg["role"] == "assistant":
        st.markdown(f"🟦 {msg['text']}")
    else:
        st.markdown(f"🟩 {msg['text']}")

chat_val = st.text_input(
    "Ask me (e.g., 'on_time_performance 2025-08-02 to 2025-08-15 client_id=2')",
    key="chat_input",
    value=st.session_state.chat_input,
)
send_btn = st.button("Send")

# ========= Chat flow =========

if send_btn and st.session_state.chat_input.strip():
    user_input = st.session_state.chat_input
    st.session_state.messages.append({"role": "user", "text": user_input})
    if not st.session_state.client:
        connect_and_cache()

    reply = "Let me check that for you."
    try:
        # Use KPI ONLY from chat prompt (dropdown is reference-only)
        s, e, kguess, cid_from_text = parse_query(user_input, ensure_str_list(st.session_state.kpi_names))
        final_kpi = kguess  # dropdown is not applied
        final_cid = cid_from_text or None

        if not s or not e:
            reply = "Please include a start and end date in the format YYYY-MM-DD .. YYYY-MM-DD."
        else:
            _ = parse_date(s); _ = parse_date(e)
            res, df = run_query(st.session_state.client, s, e, final_kpi, final_cid, int(limit))
            count = res.get("count", len(df))
            lr = res.get("limit_reached", False)
            reply = f"Fetched {count} rows for {final_kpi or 'all KPIs'} between {s} and {e}. Limit reached: {lr}. Showing up to 500 rows below."
            show_results(df, f"kpi_{(final_kpi or 'all')}_{s}_to_{e}.csv")
    except Exception as e:
        reply = f"Sorry, the query failed: {e}"

    st.session_state.messages.append({"role": "assistant", "text": reply})