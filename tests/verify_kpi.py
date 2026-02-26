import sys
import os

# Add project root to python path
project_root = os.getcwd()
if project_root not in sys.path:
    sys.path.append(project_root)

from src.core.kpi_engine.one_score import OneScoreCalculator
from src.core.kpi_engine.baseline import BaselineCalculator
import pandas as pd

def test_kpi():
    print("\n--- Testing KPI Engine ---")
    
    # 1. Test Baseline
    print("1. Baseline Calculation")
    data = pd.Series([10, 12, 11, 13, 11, 100]) # 100 is anomaly
    bl = BaselineCalculator(window_size=3)
    mean, std = bl.calculate_baseline(data)
    print("Mean:\n", mean.tolist())
    print("Std:\n", std.tolist())
    
    # Check last value (100) against baseline of prev window (approx 12)
    # Actually rolling includes current, so 100 affects mean.
    # Usually we use PREVIOUS baseline for anomaly, but here just testing calculation.
    is_anomaly = not bl.is_in_band(100, mean.iloc[4], std.iloc[4]) # compare new value to prev mean
    # Wait, simple test: 
    print(f"Is 100 in band of {mean.iloc[4]} +/- 3*{std.iloc[4]}? {bl.is_in_band(100, mean.iloc[4], std.iloc[4])}")

    # 2. Test ONE Score
    print("\n2. ONE Health Score")
    osc = OneScoreCalculator()
    
    # Scenario 1: Healthy
    metrics_healthy = {
        "crc_error": 0, "link_flaps": 0, "rssi": -50,
        "packet_loss": 0, "latency": 20, "reachability": 1,
        "retransmissions": 0, "connection_resets": 0
    }
    score1 = osc.calculate_one_score(metrics_healthy)
    print("Healthy Scenario:", score1)
    
    # Scenario 2: L1 Critical (Cable cut-ish / bad interference)
    metrics_bad_l1 = {
        "crc_error": 500, "link_flaps": 20, "rssi": -90,
        "packet_loss": 50, "latency": 1000, "reachability": 1, # L3 also affected
        "retransmissions": 100, "connection_resets": 10
    }
    score2 = osc.calculate_one_score(metrics_bad_l1)
    print("Bad L1 Scenario:", score2)

if __name__ == "__main__":
    test_kpi()
