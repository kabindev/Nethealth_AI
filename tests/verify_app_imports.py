import sys
import os
import streamlit as st

# Add project root
sys.path.append(os.getcwd())

def test_imports():
    print("Testing Dashboard Imports...")
    try:
        from src.dashboard.components.top_bar import render_top_bar
        from src.dashboard.components.topology_view import render_topology
        from src.dashboard.components.ai_insights import render_ai_insights
        from src.dashboard.components.health_metrics import render_health_metrics
        from src.orchestration.pipeline import Orchestrator
        print("All components imported successfully.")
    except Exception as e:
        print(f"Import failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_imports()
