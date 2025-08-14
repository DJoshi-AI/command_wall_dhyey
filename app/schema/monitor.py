from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class MonitoringItem(BaseModel):
    """Data model for a single KPI monitoring data point."""
    date: str
    kpi_name: str
    value: float
    status: str
    updated_at: Optional[datetime] = Field(default_factory=datetime.now)

