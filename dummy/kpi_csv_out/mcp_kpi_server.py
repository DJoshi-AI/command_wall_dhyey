# mcp_kpi_server.py
# MCP server to query dummy KPI CSVs by date range, kpi_name, and client_id.

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Iterator, List, Dict, Any, Optional, Tuple
from datetime import datetime, date

from mcp.server.fastmcp import FastMCP

# Directory where monthly CSVs live, e.g., kpi_csv_out/kpis_2025_07.csv
BASE_DIR = Path(os.getenv("KPI_CSV_DIR", "./kpi_csv_out")).resolve()

# File pattern: kpis_YYYY_MM.csv (as generated earlier)
FILENAME_TEMPLATE = "kpis_{year}_{month:02d}.csv"

mcp = FastMCP("kpi-dummy-data")


def _parse_date(d: str) -> date:
    return datetime.strptime(d, "%Y-%m-%d").date()


def _months_range(start: date, end: date) -> Iterator[Tuple[int, int]]:
    y, m = start.year, start.month
    while (y < end.year) or (y == end.year and m <= end.month):
        yield y, m
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1


def _normalize_kpi_name(name: str) -> str:
    # Normalize case and common typos (e.g., "on_time_perfomance" -> "on_time_performance")
    n = (name or "").strip().lower().replace(" ", "_").replace("-", "_")
    n = n.replace("perfomance", "performance")
    return n


def _iter_csv_rows_for_month(year: int, month: int) -> Iterator[Dict[str, Any]]:
    path = BASE_DIR / FILENAME_TEMPLATE.format(year=year, month=month)
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row


@mcp.tool()
def list_months() -> List[str]:
    """
    Return the months (YYYY-MM) for which CSV files are found.
    """
    if not BASE_DIR.exists():
        return []
    out = []
    for p in sorted(BASE_DIR.glob("kpis_*.csv")):
        try:
            stem = p.stem  # kpis_YYYY_MM
            _, y, m = stem.split("_")
            out.append(f"{y}-{m}")
        except Exception:
            continue
    return out


@mcp.tool()
def list_kpis(sample_month: Optional[str] = None) -> List[str]:
    """
    List distinct KPI names found. If sample_month is provided (YYYY-MM),
    only that month is scanned; otherwise the first available CSV is used.
    """
    # Pick a sample file to scan
    if sample_month:
        try:
            y, m = [int(x) for x in sample_month.split("-")]
            files = [BASE_DIR / FILENAME_TEMPLATE.format(year=y, month=m)]
        except Exception:
            files = []
    else:
        files = sorted(BASE_DIR.glob("kpis_*.csv"))[:1]

    names = set()
    for p in files:
        if not p.exists():
            continue
        with p.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "kpi_name" in row and row["kpi_name"]:
                    names.add(row["kpi_name"])
    return sorted(names)


@mcp.tool()
def query_kpi_data(
    start_date: str,
    end_date: str,
    kpi_name: Optional[str] = None,
    client_id: Optional[str] = None,
    limit: int = 10000,
) -> Dict[str, Any]:
    """
    Fetch rows between start_date and end_date (inclusive).
    Optional filters: kpi_name (case/underscore-insensitive), client_id.
    Returns at most 'limit' rows.
    """
    if not BASE_DIR.exists():
        return {"error": f"Data directory not found: {str(BASE_DIR)}", "rows": []}

    try:
        start = _parse_date(start_date)
        end = _parse_date(end_date)
    except Exception as e:
        return {"error": f"Invalid date format. Use YYYY-MM-DD. Details: {e}", "rows": []}

    if end < start:
        return {"error": "end_date must be on or after start_date", "rows": []}

    want_kpi = _normalize_kpi_name(kpi_name) if kpi_name else None
    want_client = str(client_id) if client_id is not None else None

    out: List[Dict[str, Any]] = []
    # Iterate only months that overlap the window
    for (y, m) in _months_range(start, end):
        for row in _iter_csv_rows_for_month(y, m) or []:
            d = row.get("date", "")
            if not d:
                continue

            # ISO date string comparison is OK because it's YYYY-MM-DD
            if d < start_date or d > end_date:
                continue

            if want_kpi:
                row_kpi = _normalize_kpi_name(row.get("kpi_name", ""))
                if row_kpi != want_kpi:
                    continue

            if want_client is not None:
                if str(row.get("client_id", "")).strip() != want_client:
                    continue

            out.append(row)

            if len(out) >= limit:
                return {
                    "count": len(out),
                    "limit_reached": True,
                    "rows": out,
                }

    return {
        "count": len(out),
        "limit_reached": False,
        "rows": out,
    }


if __name__ == "__main__":
    print(f"[MCP] Serving KPI CSVs from: {BASE_DIR}")
    mcp.run()