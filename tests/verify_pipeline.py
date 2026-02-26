import sys
import os

# Add project root
sys.path.append(os.getcwd())

from src.orchestration.pipeline import Orchestrator

def test_pipeline():
    print("\n--- Testing Orchestration Pipeline ---")
    
    # 1. Initialize
    orch = Orchestrator()
    
    # 2. Load Data (Phase 1)
    print("Loading data...")
    # Using relative paths from project root
    orch.load_data('data/raw/metrics_timeseries.csv', 'data/raw/assets.json')
    print(f"Loaded {len(orch.assets)} assets.")
    
    # 3. Run KPI Pipeline (Phase 2 & 4)
    print("Running KPI & Anomaly Pipeline...")
    anomalies = orch.run_kpi_pipeline()
    print(f"Detected {len(anomalies)} anomalies.")
    
    if anomalies:
        for a in anomalies:
            print(f" - Anomaly: {a.description} (Score: {a.score})")
            
    # 4. Run Diagnosis Pipeline (Phase 5 & 6)
    print("Running Diagnosis Pipeline...")
    results = orch.run_diagnosis_pipeline(anomalies)
    
    print(f"Diagnosed {len(results)} root causes.")
    for res in results:
        print("\n[Diagnosis Result]")
        print(res['explanation'])
        
    print("\nPipeline verification complete!")

if __name__ == "__main__":
    test_pipeline()
