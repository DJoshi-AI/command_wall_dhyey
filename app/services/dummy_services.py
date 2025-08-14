from typing import List
from app.schema.monitor import MonitoringItem

VALID_CLIENT_ID = "a7c3e1b0d9f2a8b1c4d5e6f7"

class DummyMonitorService:
    """Dummy monitoring service with hardcoded responses for a SaaS company."""

    def get_client_monitoring_data(self, client_id: str) -> List[MonitoringItem]:
        if client_id != VALID_CLIENT_ID:
            return []
        return [
            MonitoringItem(date="2025-08-11", kpi_name="user_acquisition_cost", value=150.75, status='green'),
            MonitoringItem(date="2025-08-11", kpi_name="churn_rate", value=2.1, status='yellow'),
            MonitoringItem(date="2025-08-12", kpi_name="api_uptime", value=99.99, status='green'),
            MonitoringItem(date="2025-08-12", kpi_name="monthly_recurring_revenue", value=55000.00, status='green'),
            MonitoringItem(date="2025-08-13", kpi_name="customer_lifetime_value", value=1250.00, status='green'),
            MonitoringItem(date="2025-08-13", kpi_name="churn_rate", value=3.5, status='red'),
        ]

    def get_monitoring_summary(self, client_id: str) -> dict:
        if client_id != VALID_CLIENT_ID:
            return {}
        return {
            "total_kpis_tracked": 5,
            "kpis_in_red_zone": 1,
            "key_insight": "While revenue and uptime are strong, the recent spike in the churn rate requires immediate attention.",
            "client_id": client_id,
        }

class DummyAnomalyService:
    """Dummy anomaly detection service for a SaaS company."""

    def detect_anomalies(self, client_id: str) -> dict:
        if client_id != VALID_CLIENT_ID:
            return {}
        return {
            "anomalies_found": 2,
            "critical_kpis": ["churn_rate", "api_p95_latency"],
            "anomaly_score": 0.82,
            "recommendations": [
                "Investigate the cohort of users who churned this month to find a root cause.",
                "Review API performance logs; latency is approaching the SLA threshold."
            ]
        }

    def get_trend_analysis(self, client_id: str, kpi_name: str) -> dict:
        if client_id != VALID_CLIENT_ID:
            return {"error": "Invalid client ID provided."}
        
        if kpi_name == "monthly_recurring_revenue":
            return {
                "kpi_name": kpi_name,
                "trend": "positive_growth",
                "change_percentage": 7.5,
                "forecast": "MRR is projected to grow by 8-10% next quarter if the current user acquisition rate is maintained."
            }
        elif kpi_name == "churn_rate":
             return {
                "kpi_name": kpi_name,
                "trend": "negative",
                "change_percentage": 25.1,
                "forecast": "Churn rate is accelerating and poses a significant risk to Q4 revenue targets. Needs immediate intervention."
            }
        else:
            return {"error": f"Trend analysis for KPI '{kpi_name}' is not available."}