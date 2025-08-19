#monitor.py
from pydantic import BaseModel

class MonitoringItem(BaseModel):
    date: str
    kpi_name: str  # "monthly_recurring_revenue" | "churn_rate" | "active_users"
    value: float
    status: str    # "green" | "yellow" | "red"