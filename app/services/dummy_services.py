#dummy_services.py
from typing import List, Dict, Any
from math import isfinite

from app.schema.monitor import MonitoringItem
from app.services.mongo import get_db

# Backward-compat constant (not enforced)
VALID_CLIENT_ID = "a7c3e1b0d9f2a8b1c4d5e6f7"


def _fetch_kpis(client_id: str, days: int = 30) -> List[Dict[str, Any]]:
    db = get_db()
    pipeline = [
        {"$match": {"client_id": client_id}},
        {"$sort": {"date": -1}},
        {"$limit": int(days)},
        {"$sort": {"date": 1}},  # chronological
    ]
    return list(db.kpis.aggregate(pipeline))


def _status_mrr(prev_mrr: float, curr_mrr: float) -> str:
    if prev_mrr is None or prev_mrr <= 0:
        return "green"
    change = (curr_mrr - prev_mrr) / prev_mrr
    if change < -0.10:
        return "red"
    if change < -0.03:
        return "yellow"
    return "green"


def _status_churn(churn: float) -> str:
    if churn > 0.05:
        return "red"
    if churn > 0.03:
        return "yellow"
    return "green"


def _status_active_users(users: int) -> str:
    if users < 650:
        return "red"
    if users < 750:
        return "yellow"
    return "green"


def _pct_change(first: float, last: float) -> float:
    if first and isfinite(first) and first != 0:
        return ((last - first) / first) * 100.0
    return 0.0


def _linear_slope(values: List[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    denom = sum((x - mean_x) ** 2 for x in xs) or 1.0
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
    return num / denom


class DummyMonitorService:
    """Mongo-backed monitoring service (same interface)."""

    def get_client_monitoring_data(self, client_id: str) -> List[MonitoringItem]:
        # 5 recent days to produce 5 points per metric
        docs = _fetch_kpis(client_id, days=5)
        if not docs:
            return []

        items: List[MonitoringItem] = []
        prev_mrr = None
        for d in docs:
            date = d.get("date")
            mrr = float(d.get("mrr", 0.0))
            churn = float(d.get("churn_rate", 0.0))
            users = int(d.get("active_users", 0))

            items.append(MonitoringItem(date=date, kpi_name="monthly_recurring_revenue", value=mrr, status=_status_mrr(prev_mrr, mrr)))
            items.append(MonitoringItem(date=date, kpi_name="churn_rate", value=churn, status=_status_churn(churn)))
            items.append(MonitoringItem(date=date, kpi_name="active_users", value=users, status=_status_active_users(users)))

            prev_mrr = mrr
        return items

    def get_monitoring_summary(self, client_id: str) -> dict:
        docs = _fetch_kpis(client_id, days=5)
        if not docs:
            return {}
        total_kpis_tracked = 3
        latest = docs[-1]
        latest_mrr = float(latest.get("mrr", 0.0))
        latest_churn = float(latest.get("churn_rate", 0.0))
        latest_users = int(latest.get("active_users", 0))

        red = 0
        if len(docs) >= 2 and _status_mrr(float(docs[-2].get("mrr", 0.0)), latest_mrr) == "red":
            red += 1
        if _status_churn(latest_churn) == "red":
            red += 1
        if _status_active_users(latest_users) == "red":
            red += 1

        insights = []
        if _status_churn(latest_churn) != "green":
            insights.append("Churn is elevated and needs attention")
        if len(docs) >= 2 and _status_mrr(float(docs[-2].get("mrr", 0.0)), latest_mrr) != "green":
            insights.append("MRR dropped recently")
        if _status_active_users(latest_users) != "green":
            insights.append("Active users are below target")
        key_insight = "; ".join(insights) if insights else "Overall health looks stable across recent days."

        return {
            "total_kpis_tracked": total_kpis_tracked,
            "kpis_in_red_zone": red,
            "key_insight": key_insight,
            "client_id": client_id,
        }


class DummyAnomalyService:
    """Mongo-backed anomaly detection (same interface)."""

    def detect_anomalies(self, client_id: str) -> dict:
        docs = _fetch_kpis(client_id, days=5)
        if not docs:
            return {}

        anomalies_found = 0
        critical_kpis = set()
        recommendations: List[str] = []

        prev = None
        for d in docs:
            churn = float(d.get("churn_rate", 0.0))
            mrr = float(d.get("mrr", 0.0))
            users = int(d.get("active_users", 0))

            if churn > 0.05:
                anomalies_found += 1
                critical_kpis.add("churn_rate")

            if prev:
                prev_mrr = float(prev.get("mrr", 0.0))
                if prev_mrr > 0:
                    drop = (mrr - prev_mrr) / prev_mrr
                    if drop < -0.10:
                        anomalies_found += 1
                        critical_kpis.add("monthly_recurring_revenue")

            if users < 650:
                anomalies_found += 1
                critical_kpis.add("active_users")

            prev = d

        anomaly_score = min(1.0, anomalies_found / 10.0)

        if "churn_rate" in critical_kpis:
            recommendations.append("Investigate churn cohorts and run win-back campaigns.")
        if "monthly_recurring_revenue" in critical_kpis:
            recommendations.append("Analyze revenue segments; review pricing/discount changes.")
        if "active_users" in critical_kpis:
            recommendations.append("Re-engage inactive users; launch in-app prompts.")
        if not recommendations:
            recommendations.append("No critical anomalies detected; continue to monitor KPIs.")

        return {
            "anomalies_found": anomalies_found,
            "critical_kpis": sorted(list(critical_kpis)),
            "anomaly_score": round(anomaly_score, 2),
            "recommendations": recommendations,
        }

    def get_trend_analysis(self, client_id: str, kpi_name: str) -> dict:
        aliases = {
            "monthly_recurring_revenue": "mrr",
            "churn_rate": "churn_rate",
            "active_users": "active_users",
            "mrr": "mrr",
        }
        if kpi_name not in aliases:
            return {"error": f"Trend analysis for KPI '{kpi_name}' is not available."}

        metric = aliases[kpi_name]
        docs = _fetch_kpis(client_id, days=5)
        if not docs:
            return {"error": f"No KPI data found for client '{client_id}'."}

        ys = [float(d.get(metric, 0.0)) for d in docs]
        if len(ys) < 2:
            return {"error": "Not enough data points to calculate a trend."}

        slope = _linear_slope(ys)
        change_pct = _pct_change(ys[0], ys[-1])

        if metric == "mrr":
            trend = "positive_growth" if slope > 0 else "negative" if slope < 0 else "flat"
            forecast = (
                "MRR is projected to grow if current momentum continues."
                if slope > 0
                else "MRR may decline without intervention."
                if slope < 0
                else "MRR is stable; expect similar performance near-term."
            )
        elif metric == "churn_rate":
            trend = "negative" if slope > 0 else "improving" if slope < 0 else "flat"
            forecast = (
                "Churn is accelerating and may impact revenue targets."
                if slope > 0
                else "Churn is improving; maintain retention efforts."
                if slope < 0
                else "Churn is steady; monitor for shifts."
            )
        else:
            trend = "up" if slope > 0 else "down" if slope < 0 else "flat"
            forecast = (
                "Metric trending up." if slope > 0 else "Metric trending down." if slope < 0 else "Metric appears stable."
            )

        return {
            "kpi_name": kpi_name,
            "trend": trend,
            "change_percentage": round(change_pct, 2),
            "forecast": forecast,
        }