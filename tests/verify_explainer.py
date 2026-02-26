import sys
import os

# Add project root
sys.path.append(os.getcwd())

from src.data.schemas import RootCause
from src.intelligence.explainer import Explainer

def test_explainer():
    print("\n--- Testing AI Explainer ---")
    
    rc = RootCause(
        anomaly_id="a1",
        root_cause_asset_id="switch-core",
        probability=0.95,
        description="Physical layer issue (CRC Errors).",
        recommended_action="Replace the uplink cable."
    )
    
    explainer = Explainer()
    text = explainer.explain(rc)
    
    print("Generated Explanation:")
    print(text)
    
    assert "switch-core" in text
    assert "Very High" in text
    assert "Replace the uplink cable" in text
    
    print("\nExplainer verified!")

if __name__ == "__main__":
    test_explainer()
