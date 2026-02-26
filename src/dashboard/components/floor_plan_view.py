"""
Floor Plan Heatmap Visualization Component

Displays network devices on an industrial floor plan with health-based color coding.
Shows fault severity as a heatmap overlay.
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from typing import List, Dict, Any, Optional
from pathlib import Path
import json


def render_floor_plan(
    assets: List[Dict[str, Any]],
    kpis: Dict[str, Dict[str, float]],
    anomalies: List[Any],
    floor_plan_path: Optional[str] = None
):
    """
    Render interactive floor plan with device health heatmap.
    
    Args:
        assets: List of asset dictionaries with floor_position data
        kpis: Dictionary of KPI scores by asset_id
        anomalies: List of active anomalies
        floor_plan_path: Path to floor plan image (optional)
    """
    
    st.markdown("### 🗺️ Factory Floor Plan - Device Health Map")
    
    # Check if floor plan image exists
    if floor_plan_path and Path(floor_plan_path).exists():
        # Display floor plan as background
        from PIL import Image
        floor_plan_img = Image.open(floor_plan_path)
        
        # Get image dimensions for scaling
        img_width, img_height = floor_plan_img.size
    else:
        # Use default dimensions if no floor plan
        img_width, img_height = 1000, 800
        st.info("💡 Floor plan image not found. Using simulated layout.")
    
    # Extract device positions and health scores
    device_data = []
    for asset in assets:
        # Asset is a Pydantic model, use attribute access
        asset_id = asset.id
        
        # Get floor position (x, y coordinates) - check if attribute exists
        floor_pos = getattr(asset, 'floor_position', None)
        if not floor_pos:
            # Generate simulated position if not provided
            floor_pos = _generate_simulated_position(asset_id, img_width, img_height)
        else:
            # Convert to dict if it's an object
            if hasattr(floor_pos, '__dict__'):
                floor_pos = floor_pos.__dict__
        
        x = floor_pos.get('x', 0) if isinstance(floor_pos, dict) else getattr(floor_pos, 'x', 0)
        y = floor_pos.get('y', 0) if isinstance(floor_pos, dict) else getattr(floor_pos, 'y', 0)
        
        # Get health score
        health_score = kpis.get(asset_id, {}).get('one_score', 100.0)
        
        # Check if device has active anomalies
        has_anomaly = any(a.asset_id == asset_id for a in anomalies)
        
        # Determine color based on health
        color = _get_health_color(health_score)
        
        device_data.append({
            'asset_id': asset_id,
            'x': x,
            'y': y,
            'health_score': health_score,
            'has_anomaly': has_anomaly,
            'color': color,
            'device_type': getattr(asset, 'type', 'Unknown'),
            'location': getattr(asset, 'location', 'Unknown')
        })
    
    # Create plotly figure
    fig = go.Figure()
    
    # Add floor plan image as background if available
    if floor_plan_path and Path(floor_plan_path).exists():
        fig.add_layout_image(
            dict(
                source=floor_plan_img,
                xref="x",
                yref="y",
                x=0,
                y=img_height,
                sizex=img_width,
                sizey=img_height,
                sizing="stretch",
                opacity=0.3,
                layer="below"
            )
        )
    
    # Add device markers
    for device in device_data:
        # Marker size based on anomaly status
        marker_size = 20 if device['has_anomaly'] else 15
        
        # Add scatter point for device
        fig.add_trace(go.Scatter(
            x=[device['x']],
            y=[device['y']],
            mode='markers+text',
            marker=dict(
                size=marker_size,
                color=device['color'],
                line=dict(width=2, color='white' if device['has_anomaly'] else 'gray'),
                symbol='circle'
            ),
            text=device['asset_id'],
            textposition='top center',
            textfont=dict(size=10, color='black'),
            name=device['asset_id'],
            hovertemplate=(
                f"<b>{device['asset_id']}</b><br>"
                f"Type: {device['device_type']}<br>"
                f"Location: {device['location']}<br>"
                f"Health Score: {device['health_score']:.1f}/100<br>"
                f"Status: {'⚠️ ANOMALY' if device['has_anomaly'] else '✅ Healthy'}<br>"
                "<extra></extra>"
            ),
            showlegend=False
        ))
    
    # Update layout
    fig.update_layout(
        title="Device Health Heatmap",
        xaxis=dict(
            range=[0, img_width],
            showgrid=True,
            gridcolor='lightgray',
            zeroline=False,
            title="X Position (meters)"
        ),
        yaxis=dict(
            range=[0, img_height],
            showgrid=True,
            gridcolor='lightgray',
            zeroline=False,
            title="Y Position (meters)",
            scaleanchor="x",
            scaleratio=1
        ),
        height=600,
        hovermode='closest',
        plot_bgcolor='rgba(240, 240, 240, 0.5)'
    )
    
    # Display the figure
    st.plotly_chart(fig, use_container_width=True)
    
    # Add legend
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("🟢 **Healthy** (90-100)")
    with col2:
        st.markdown("🟡 **Warning** (70-89)")
    with col3:
        st.markdown("🟠 **Degraded** (50-69)")
    with col4:
        st.markdown("🔴 **Critical** (<50)")
    
    # Device summary table
    st.markdown("#### Device Summary")
    
    # Create summary dataframe
    import pandas as pd
    summary_df = pd.DataFrame(device_data)
    summary_df = summary_df[['asset_id', 'device_type', 'health_score', 'has_anomaly']]
    summary_df.columns = ['Asset ID', 'Type', 'Health Score', 'Has Anomaly']
    summary_df = summary_df.sort_values('Health Score')
    
    st.dataframe(summary_df, use_container_width=True, hide_index=True)


def _get_health_color(health_score: float) -> str:
    """Get color based on health score."""
    if health_score >= 90:
        return 'green'
    elif health_score >= 70:
        return 'yellow'
    elif health_score >= 50:
        return 'orange'
    else:
        return 'red'


def _generate_simulated_position(asset_id: str, width: int, height: int) -> Dict[str, float]:
    """
    Generate simulated floor position for devices without coordinates.
    
    Uses asset type to determine logical placement zones.
    """
    import hashlib
    
    # Use hash of asset_id for consistent positioning
    hash_val = int(hashlib.md5(asset_id.encode()).hexdigest(), 16)
    
    # Determine zone based on asset type
    if 'switch' in asset_id.lower() or 'router' in asset_id.lower():
        # Network equipment in server room (top-right quadrant)
        x = width * 0.7 + (hash_val % 200)
        y = height * 0.7 + (hash_val % 150)
    elif 'plc' in asset_id.lower() or 'controller' in asset_id.lower():
        # PLCs in production zone (center-left)
        x = width * 0.3 + (hash_val % 250)
        y = height * 0.5 + (hash_val % 200)
    elif 'hmi' in asset_id.lower():
        # HMIs in control room (top-left)
        x = width * 0.2 + (hash_val % 150)
        y = height * 0.7 + (hash_val % 100)
    elif 'firewall' in asset_id.lower():
        # Firewalls in server room
        x = width * 0.75 + (hash_val % 100)
        y = height * 0.75 + (hash_val % 100)
    else:
        # Default: random position
        x = (hash_val % width)
        y = (hash_val % height)
    
    return {'x': x, 'y': y, 'floor': 'factory_floor_1'}
