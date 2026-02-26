"""
Live Data Bridge

Converts LiveNetworkCollector output into the format expected by
the Orchestrator pipeline:
  - Metrics CSV: timestamp, asset_id, metric_name, value, unit
  - Assets JSON:  id, name, type, role, parent_id, metadata

Also manages auto-saving so the Orchestrator can reload on each refresh.
"""

import json
import tempfile
import os
from datetime import datetime
from typing import List, Dict, Optional
import pandas as pd

LIVE_METRICS_CSV = "data/live/live_metrics.csv"
LIVE_ASSETS_JSON = "data/live/live_assets.json"


def ensure_live_dir():
    """Create data/live/ directory if it doesn't exist."""
    os.makedirs("data/live", exist_ok=True)


def devices_to_assets_json(devices: List[Dict]) -> List[Dict]:
    """
    Convert discovered device list to assets.json format.

    devices: [{"id": "router-1", "ip": "192.168.1.1", "type": "router",
               "name": "My Router", "hostname": "router.local"}]

    Thermal metadata is varied per device so the thermal simulator
    produces realistic, differentiated outputs instead of cloned values.
    """
    import random
    import hashlib

    assets = []
    device_list = list(devices)

    # Realistic thermal ranges by device type
    THERMAL_PROFILES = {
        "router":      {"cable_length_m": (5, 20),  "ambient_temp_c": (28, 38), "age_months": (12, 60), "gauge": "24AWG", "dissipation": (0.7, 0.9)},
        "switch":      {"cable_length_m": (3, 15),  "ambient_temp_c": (25, 35), "age_months": (6, 48),  "gauge": "24AWG", "dissipation": (0.8, 0.95)},
        "server":      {"cable_length_m": (2, 8),   "ambient_temp_c": (20, 28), "age_months": (6, 36),  "gauge": "22AWG", "dissipation": (0.9, 0.99)},
        "workstation": {"cable_length_m": (3, 10),  "ambient_temp_c": (22, 30), "age_months": (12, 72), "gauge": "26AWG", "dissipation": (0.75, 0.9)},
        "pc":          {"cable_length_m": (3, 10),  "ambient_temp_c": (22, 30), "age_months": (12, 72), "gauge": "26AWG", "dissipation": (0.75, 0.9)},
        "laptop":      {"cable_length_m": (1, 5),   "ambient_temp_c": (22, 30), "age_months": (6, 48),  "gauge": "26AWG", "dissipation": (0.8, 0.95)},
        "printer":     {"cable_length_m": (3, 8),   "ambient_temp_c": (25, 35), "age_months": (24, 96), "gauge": "26AWG", "dissipation": (0.6, 0.8)},
        "camera":      {"cable_length_m": (10, 50), "ambient_temp_c": (30, 45), "age_months": (24, 84), "gauge": "24AWG", "dissipation": (0.5, 0.75)},
        "iot":         {"cable_length_m": (5, 30),  "ambient_temp_c": (28, 42), "age_months": (12, 60), "gauge": "26AWG", "dissipation": (0.5, 0.7)},
        "unknown":     {"cable_length_m": (5, 20),  "ambient_temp_c": (25, 35), "age_months": (12, 60), "gauge": "24AWG", "dissipation": (0.7, 0.9)},
    }

    for i, dev in enumerate(device_list):
        device_id = dev.get("id", f"device-{i}")
        dev_type = dev.get("type", "unknown").lower()
        role = _infer_role(dev_type, i)

        # Parent topology: first device is root (usually router), rest connect to it
        parent_id = None
        if i > 0:
            parent_id = device_list[0].get("id", "device-0")

        # Use device_id as seed so values are stable across reruns
        # (same device always gets same thermal profile)
        seed = int(hashlib.md5(device_id.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)

        profile = THERMAL_PROFILES.get(dev_type, THERMAL_PROFILES["unknown"])
        cable_len  = round(rng.uniform(*profile["cable_length_m"]), 1)
        ambient    = round(rng.uniform(*profile["ambient_temp_c"]), 1)
        age        = rng.randint(*profile["age_months"])
        dissipation = round(rng.uniform(*profile["dissipation"]), 2)

        asset = {
            "id": device_id,
            "name": dev.get("name") or dev.get("hostname") or device_id,
            "type": dev_type,
            "role": role,
            "parent_id": parent_id,
            "metadata": {
                "ip_address": dev.get("ip", ""),
                "hostname": dev.get("hostname", ""),
                # Per-device varied thermal metadata for realistic physics simulation
                "cable_length_m": cable_len,
                "ambient_temp_c": ambient,
                "age_months": age,
                "cable_gauge": profile["gauge"],
                "heat_dissipation_factor": dissipation,
            },
        }
        assets.append(asset)

    return assets


def _infer_role(device_type: str, index: int) -> str:
    role_map = {
        "router": "gateway",
        "switch": "distribution",
        "server": "application",
        "workstation": "endpoint",
        "pc": "endpoint",
        "laptop": "endpoint",
        "phone": "endpoint",
        "printer": "peripheral",
        "camera": "iot",
        "iot": "iot",
        "unknown": "endpoint",
    }
    if index == 0:
        return "gateway"
    return role_map.get(device_type.lower(), "endpoint")


def bridge_to_pipeline(
    collector,
    assets_json_path: str = LIVE_ASSETS_JSON,
    metrics_csv_path: str = LIVE_METRICS_CSV,
) -> tuple:
    """
    Pull data from a LiveNetworkCollector, save to files,
    and return (metrics_csv_path, assets_json_path) for Orchestrator.load_data().
    """
    ensure_live_dir()

    # 1. Save assets JSON
    devices_list = list(collector.devices.values())
    assets = devices_to_assets_json(devices_list)
    with open(assets_json_path, "w") as f:
        json.dump(assets, f, indent=2)

    # 2. Save metrics CSV
    df = collector.get_data()
    if not df.empty:
        # Ensure correct column names for pipeline
        if "metric_name" not in df.columns and "metric" in df.columns:
            df = df.rename(columns={"metric": "metric_name"})
        df = df[["timestamp", "asset_id", "metric_name", "value", "unit"]]
        df.to_csv(metrics_csv_path, index=False)

    return metrics_csv_path, assets_json_path


def get_live_summary(collector) -> Dict:
    """
    Return per-device latest metric summary for the sidebar status widget.
    """
    df = collector.get_data()
    if df.empty:
        return {}

    summary = {}
    for asset_id, group in df.groupby("asset_id"):
        latest = group.sort_values("timestamp").groupby("metric_name").last()["value"].to_dict()
        summary[asset_id] = {
            "latency_ms": round(latest.get("latency", 0), 1),
            "packet_loss_pct": round(latest.get("packet_loss", 0), 1),
            "snr_db": round(latest.get("snr_db", 0), 1),
            "crc_errors": round(latest.get("crc_error", 0), 2),
            "status": _health_status(latest),
        }
    return summary


def get_collector_readiness(collector) -> dict:
    """
    Returns readiness state for the dashboard.
    Calls collector.get_readiness() if available, falls back gracefully.
    """
    if collector is None:
        return {"ready": False, "message": "Collector not initialised.", "wait_sec": 0}
    if hasattr(collector, "get_readiness"):
        return collector.get_readiness()
    # Fallback for older collector version
    is_ready = collector.poll_count >= 1 and collector.store.row_count() > 0
    return {
        "ready": is_ready,
        "poll_count": collector.poll_count,
        "row_count": collector.store.row_count(),
        "wait_sec": 10 if not is_ready else 0,
        "message": "Live data ready." if is_ready else "⏳ Waiting for first poll...",
    }


def _health_status(metrics: Dict) -> str:
    loss = metrics.get("packet_loss", 0)
    latency = metrics.get("latency", 0)
    if loss > 50 or latency > 500:
        return "critical"
    if loss > 20 or latency > 150:
        return "warning"
    if loss > 5 or latency > 80:
        return "degraded"
    return "healthy"