#agent_tools.py
from langchain.tools import tool
from pydantic import BaseModel, Field
from app.services.dummy_services import DummyMonitorService, DummyAnomalyService
from typing import Dict, Any

monitor_service = DummyMonitorService()
anomaly_service = DummyAnomalyService()

class ClientIDInput(BaseModel):
    client_id: str = Field(description="The unique identifier for the client account, typically a hex string.")

class TrendAnalysisInput(BaseModel):
    client_id: str = Field(description="The unique identifier for the client account.")
    kpi_name: str = Field(description="The specific KPI to analyze (e.g., 'monthly_recurring_revenue', 'churn_rate').")

@tool("get_saas_kpi_summary", args_schema=ClientIDInput)
def get_saas_kpi_summary(client_id: str) -> dict:
    """Provides a high-level summary of key SaaS business metrics for a specific client account."""
    return monitor_service.get_monitoring_summary(client_id)

@tool("get_detailed_kpi_data", args_schema=ClientIDInput)
def get_detailed_kpi_data(client_id: str) -> Dict[str, Any]:
    """Fetches detailed, itemized KPI data for a client account."""
    data = monitor_service.get_client_monitoring_data(client_id)
    return {"data": [item.model_dump() for item in data]}

@tool("detect_business_anomalies", args_schema=ClientIDInput)
def detect_business_anomalies(client_id: str) -> dict:
    """Detects and reports any anomalies in business or operational KPIs."""
    return anomaly_service.detect_anomalies(client_id)

@tool("get_kpi_trend_analysis", args_schema=TrendAnalysisInput)
def get_kpi_trend_analysis(client_id: str, kpi_name: str) -> dict:
    """Analyzes and reports the performance trend and forecast for a single, specific KPI."""
    return anomaly_service.get_trend_analysis(client_id, kpi_name)

all_tools = [
    get_saas_kpi_summary,
    get_detailed_kpi_data,
    detect_business_anomalies,
    get_kpi_trend_analysis,
]