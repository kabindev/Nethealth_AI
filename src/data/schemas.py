from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field

class MetricRecord(BaseModel):
    timestamp: datetime
    asset_id: str
    metric_name: str
    value: float
    unit: Optional[str] = None

class Asset(BaseModel):
    id: str
    name: str
    type: str  # e.g., 'switch', 'plc', 'sensor'
    role: Optional[str] = None
    parent_id: Optional[str] = None # For topology
    metadata: Dict[str, Any] = Field(default_factory=dict)

class KPIRecord(BaseModel):
    timestamp: datetime
    asset_id: str
    kpi_name: str
    value: float
    baseline_mean: Optional[float] = None
    baseline_std: Optional[float] = None
    is_anomaly: bool = False

class Anomaly(BaseModel):
    id: str
    timestamp: datetime
    asset_id: str
    metric_or_kpi: str
    severity: str  # 'low', 'medium', 'high', 'critical'
    description: str
    score: float

class RootCause(BaseModel):
    anomaly_id: str
    root_cause_asset_id: str
    probability: float
    description: str
    recommended_action: str

class ThermalState(BaseModel):
    """Real-time thermal state of a network component"""
    asset_id: str
    timestamp: datetime
    ambient_temp_c: float
    operating_temp_c: float
    resistance_ohm: float
    snr_db: float
    ber: float
    traffic_load_mbps: float

class FailurePrediction(BaseModel):
    """Physics-based failure prediction"""
    asset_id: str
    timestamp: datetime
    confidence: float  # 0-1
    days_remaining: Optional[float]
    failure_probability: float
    recommended_action: str
    thermal_state: Optional[Dict[str, Any]] = None  # ThermalState as dict
    prediction_type: str = "thermal_physics"
