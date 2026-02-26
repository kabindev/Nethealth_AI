import os
import sys
sys.path.append(os.getcwd())

import pytest
from src.orchestration.pipeline import Orchestrator

def test_full_pipeline_execution():
    # Setup paths
    base_dir = os.getcwd()
    metrics_path = os.path.join(base_dir, 'data/raw/metrics_timeseries.csv')
    assets_path = os.path.join(base_dir, 'data/raw/assets.json')
    
    # Init
    orch = Orchestrator()
    orch.load_data(metrics_path, assets_path)
    
    # Run
    anomalies = orch.run_kpi_pipeline()
    # Expect some results (or empty if healthy), but function should run.
    assert isinstance(anomalies, list)
    
    # Diagnosis
    results = orch.run_diagnosis_pipeline(anomalies)
    assert isinstance(results, list)

if __name__ == "__main__":
    test_full_pipeline_execution()
    print("SUCCESS")
