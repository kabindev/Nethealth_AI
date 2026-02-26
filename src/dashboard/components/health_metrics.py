import streamlit as st
import pandas as pd
from typing import Dict

def render_health_metrics(latest_kpis: Dict[str, Dict[str, float]]):
    st.subheader("Asset Health Metrics")
    
    if not latest_kpis:
        st.warning("No KPI data available.")
        return
        
    assets = list(latest_kpis.keys())
    selected_asset = st.selectbox("Select Asset to Inspect", assets)
    
    if selected_asset:
        scores = latest_kpis[selected_asset]
        
        # Prepare data for chart
        # Scores are: one_score, l1_score, l3_score, l4_score
        data = {
            "Layer": ["L1 (Physical)", "L3 (Network)", "L4 (Transport)", "L7 (Application)", "Overall (ONE)"],
            "Score": [scores.get('l1_score', 0), scores.get('l3_score', 0), scores.get('l4_score', 0), scores.get('l7_score', 0), scores.get('one_score', 0)]
        }
        df = pd.DataFrame(data)
        
        st.bar_chart(df, x="Layer", y="Score")
        
        # Display raw values table
        st.dataframe(df)
