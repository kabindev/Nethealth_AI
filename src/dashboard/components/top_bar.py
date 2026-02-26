import streamlit as st

def render_top_bar(one_score: float, anomaly_count: int):
    st.title("Belden Network Health Dashboard")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("ONE Health Score", f"{one_score}/100", delta=None)
        
    with col2:
        st.metric("Active Anomalies", anomaly_count, delta_color="inverse")
        
    with col3:
        status = "Healthy" if one_score > 90 else "Critical" if one_score < 60 else "Warning"
        color = "green" if status == "Healthy" else "red" if status == "Critical" else "orange"
        st.markdown(f"**System Status**: :{color}[{status}]")
    
    st.divider()
