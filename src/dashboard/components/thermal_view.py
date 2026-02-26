"""
Thermal View Component for Dashboard

Displays thermal network state, failure predictions, and what-if scenarios.
"""

import streamlit as st
import pandas as pd
from typing import Dict, Any, Optional


def render_thermal_metrics(thermal_predictions: Dict[str, Any]):
    """
    Render thermal metrics for all assets with predictions.
    
    Args:
        thermal_predictions: Dictionary of thermal predictions by asset_id
    """
    if not thermal_predictions:
        st.info("No thermal predictions available. Ensure assets have thermal metadata.")
        return
    
    st.markdown("### 🌡️ Thermal Network State")
    
    # Create metrics grid
    cols = st.columns(4)
    
    # Count critical assets
    critical_count = sum(
        1 for pred in thermal_predictions.values()
        if pred.get('days_remaining') and pred['days_remaining'] < 30
    )
    
    warning_count = sum(
        1 for pred in thermal_predictions.values()
        if pred.get('days_remaining') and 30 <= pred['days_remaining'] < 90
    )
    
    avg_temp = sum(
        pred.get('thermal_state', {}).get('operating_temp_c', 0)
        for pred in thermal_predictions.values()
    ) / len(thermal_predictions) if thermal_predictions else 0
    
    total_monitored = len(thermal_predictions)
    
    with cols[0]:
        st.metric("Assets Monitored", total_monitored, help="Assets with thermal simulation")
    
    with cols[1]:
        st.metric("Critical Failures", critical_count, delta=f"-{critical_count}" if critical_count > 0 else None, delta_color="inverse")
    
    with cols[2]:
        st.metric("Warnings", warning_count, help="Failures predicted in 30-90 days")
    
    with cols[3]:
        st.metric("Avg Operating Temp", f"{avg_temp:.1f}°C", help="Average cable operating temperature")


def render_failure_timeline(thermal_predictions: Dict[str, Any]):
    """
    Render timeline of predicted failures.
    
    Args:
        thermal_predictions: Dictionary of thermal predictions by asset_id
    """
    st.markdown("### 📅 Failure Prediction Timeline")
    
    # Filter predictions with failure dates
    failures = [
        {
            "asset_id": asset_id,
            "days_remaining": pred['days_remaining'],
            "confidence": pred['confidence'],
            "action": pred['recommended_action']
        }
        for asset_id, pred in thermal_predictions.items()
        if pred.get('days_remaining') is not None
    ]
    
    if not failures:
        st.success("✅ No failures predicted in the next 90 days!")
        return
    
    # Sort by days remaining
    failures.sort(key=lambda x: x['days_remaining'])
    
    # Display as timeline
    for failure in failures:
        days = int(failure['days_remaining'])
        
        if days < 30:
            color = "🔴"
            urgency = "CRITICAL"
        elif days < 60:
            color = "🟠"
            urgency = "HIGH"
        else:
            color = "🟡"
            urgency = "MEDIUM"
        
        with st.expander(f"{color} **{failure['asset_id']}** - {days} days remaining ({urgency})"):
            st.write(f"**Confidence:** {failure['confidence']*100:.0f}%")
            st.write(f"**Recommended Action:** {failure['action']}")
            
            # Progress bar showing time remaining
            progress = max(0, min(1, days / 90))
            st.progress(progress, text=f"{days} days until predicted failure")


def render_thermal_details_table(thermal_predictions: Dict[str, Any]):
    """
    Render detailed thermal state table.
    
    Args:
        thermal_predictions: Dictionary of thermal predictions by asset_id
    """
    st.markdown("### 📊 Detailed Thermal State")
    
    if not thermal_predictions:
        return
    
    # Build table data
    table_data = []
    for asset_id, pred in thermal_predictions.items():
        thermal_state = pred.get('thermal_state', {})
        
        table_data.append({
            "Asset ID": asset_id,
            "Operating Temp (°C)": f"{thermal_state.get('operating_temp_c', 0):.1f}",
            "SNR (dB)": f"{thermal_state.get('snr_db', 0):.1f}",
            "BER": f"{thermal_state.get('ber', 0):.2e}",
            "Resistance (Ω)": f"{thermal_state.get('resistance_ohm', 0):.3f}",
            "Failure Risk": f"{pred.get('failure_probability', 0)*100:.1f}%",
            "Days Remaining": int(pred['days_remaining']) if pred.get('days_remaining') else "N/A"
        })
    
    df = pd.DataFrame(table_data)
    
    # Style the dataframe
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )


def render_what_if_simulator(thermal_predictions: Dict[str, Any], assets: list):
    """
    Render interactive what-if scenario simulator.
    
    Args:
        thermal_predictions: Current thermal predictions
        assets: List of assets
    """
    st.markdown("### 🔮 What-If Scenario Simulator")
    st.caption("Simulate network changes and see predicted thermal impact")
    
    # Select asset to simulate
    asset_ids = [asset.id for asset in assets if hasattr(asset, 'metadata') and asset.metadata.get('cable_length_m')]
    
    if not asset_ids:
        st.warning("No assets with thermal metadata available for simulation")
        return
    
    selected_asset = st.selectbox("Select Asset", asset_ids)
    
    # Get current asset data
    asset = next((a for a in assets if a.id == selected_asset), None)
    if not asset:
        return
    
    metadata = asset.metadata
    current_pred = thermal_predictions.get(selected_asset, {})
    current_thermal = current_pred.get('thermal_state', {})
    
    st.markdown("#### Current State")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Operating Temp", f"{current_thermal.get('operating_temp_c', 0):.1f}°C")
    with col2:
        st.metric("Failure Risk", f"{current_pred.get('failure_probability', 0)*100:.1f}%")
    with col3:
        days_rem = current_pred.get('days_remaining')
        st.metric("Days to Failure", int(days_rem) if days_rem else "N/A")
    
    st.markdown("#### Scenario Adjustments")
    
    col1, col2 = st.columns(2)
    
    with col1:
        ambient_delta = st.slider(
            "Ambient Temperature Change (°C)",
            min_value=-10.0,
            max_value=20.0,
            value=0.0,
            step=1.0,
            help="Simulate temperature increase/decrease"
        )
        
        traffic_multiplier = st.slider(
            "Traffic Load Multiplier",
            min_value=0.5,
            max_value=2.0,
            value=1.0,
            step=0.1,
            help="Simulate increased network load"
        )
    
    with col2:
        age_delta = st.slider(
            "Age Change (months)",
            min_value=0,
            max_value=36,
            value=0,
            step=6,
            help="Simulate cable aging"
        )
        
        ventilation_improvement = st.slider(
            "Ventilation Improvement (%)",
            min_value=0,
            max_value=50,
            value=0,
            step=10,
            help="Simulate improved heat dissipation"
        )
    
    # Calculate scenario impact
    if st.button("🚀 Run Simulation", type="primary"):
        with st.spinner("Running thermal physics simulation..."):
            try:
                from src.intelligence.thermal_simulator import ThermalNetworkSimulator
                simulator = ThermalNetworkSimulator()
                
                # Prepare scenario parameters
                new_ambient = metadata.get('ambient_temp_c', 25) + ambient_delta
                new_traffic = current_thermal.get('traffic_load_mbps', 100) * traffic_multiplier
                new_age = metadata.get('age_months', 12) + age_delta
                new_dissipation = min(1.0, metadata.get('heat_dissipation_factor', 0.8) * (1 + ventilation_improvement / 100))
                
                # Run simulation
                scenario_pred = simulator.simulate_cable_degradation(
                    asset_id=selected_asset,
                    ambient_temp=new_ambient,
                    cable_length=metadata.get('cable_length_m', 50),
                    traffic_load=new_traffic,
                    age_months=new_age,
                    cable_gauge=metadata.get('cable_gauge', '24AWG'),
                    heat_dissipation_factor=new_dissipation
                )
                
                # Display results
                st.markdown("#### 📈 Scenario Results")
                
                col1, col2, col3 = st.columns(3)
                
                current_temp = current_thermal.get('operating_temp_c', 0)
                scenario_temp = scenario_pred.thermal_state.operating_temp_c
                temp_delta = scenario_temp - current_temp
                
                with col1:
                    st.metric(
                        "Operating Temp",
                        f"{scenario_temp:.1f}°C",
                        delta=f"{temp_delta:+.1f}°C",
                        delta_color="inverse"
                    )
                
                current_risk = current_pred.get('failure_probability', 0)
                scenario_risk = scenario_pred.failure_probability
                risk_delta = scenario_risk - current_risk
                
                with col2:
                    st.metric(
                        "Failure Risk",
                        f"{scenario_risk*100:.1f}%",
                        delta=f"{risk_delta*100:+.1f}%",
                        delta_color="inverse"
                    )
                
                with col3:
                    scenario_days = scenario_pred.days_remaining
                    current_days = current_pred.get('days_remaining')
                    
                    if scenario_days and current_days:
                        days_delta = scenario_days - current_days
                        st.metric(
                            "Days to Failure",
                            int(scenario_days),
                            delta=f"{days_delta:+.0f} days",
                            delta_color="normal"
                        )
                    else:
                        st.metric("Days to Failure", int(scenario_days) if scenario_days else "N/A")
                
                # Recommendation
                if scenario_risk < current_risk:
                    st.success(f"✅ **Improvement:** {scenario_pred.recommended_action}")
                elif scenario_risk > current_risk:
                    st.error(f"⚠️ **Degradation:** {scenario_pred.recommended_action}")
                else:
                    st.info(f"ℹ️ **No Change:** {scenario_pred.recommended_action}")
                
            except Exception as e:
                st.error(f"Simulation failed: {e}")


def render_thermal_view(thermal_predictions: Dict[str, Any], assets: list):
    """
    Main thermal view component.
    
    Args:
        thermal_predictions: Dictionary of thermal predictions
        assets: List of assets
    """
    # Render all thermal components
    render_thermal_metrics(thermal_predictions)
    
    st.markdown("---")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        render_failure_timeline(thermal_predictions)
    
    with col2:
        render_thermal_details_table(thermal_predictions)
    
    st.markdown("---")
    
    render_what_if_simulator(thermal_predictions, assets)
