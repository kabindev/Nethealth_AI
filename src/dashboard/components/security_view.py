"""
Security Dashboard Component

Visualizes rogue device alerts and configuration drift.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
from typing import Dict, List


def render_security_dashboard(orchestrator):
    """
    Render security monitoring dashboard
    
    Args:
        orchestrator: IntelligenceOrchestrator instance
    """
    st.header("🔒 Security Monitoring")
    
    # Security score overview
    col1, col2, col3, col4 = st.columns(4)
    
    # Mock data for demonstration
    security_data = _get_mock_security_data(orchestrator)
    
    with col1:
        score = security_data['security_score']
        score_color = "green" if score >= 80 else "orange" if score >= 60 else "red"
        st.metric(
            "Security Score",
            f"{score:.0f}/100",
            delta=f"{security_data['score_change']:+.0f}",
            delta_color="normal"
        )
    
    with col2:
        st.metric(
            "Rogue Devices",
            security_data['rogue_count'],
            delta=f"{security_data['rogue_change']:+d}",
            delta_color="inverse"
        )
    
    with col3:
        st.metric(
            "Config Drifts",
            security_data['drift_count'],
            delta=f"{security_data['drift_change']:+d}",
            delta_color="inverse"
        )
    
    with col4:
        st.metric(
            "Critical Alerts",
            security_data['critical_count'],
            delta=f"{security_data['critical_change']:+d}",
            delta_color="inverse"
        )
    
    st.divider()
    
    # Tabs for different security views
    tab1, tab2, tab3 = st.tabs(["🚨 Rogue Devices", "⚙️ Configuration Drift", "📊 Security Timeline"])
    
    with tab1:
        render_rogue_devices(security_data['rogue_devices'])
    
    with tab2:
        render_config_drift(security_data['config_drift'])
    
    with tab3:
        render_security_timeline(security_data['timeline'])


def render_rogue_devices(rogue_devices: List[Dict]):
    """Render rogue device alerts"""
    st.subheader("Unauthorized Device Detection")
    
    if not rogue_devices:
        st.success("✅ No rogue devices detected")
        return
    
    # Alert summary
    st.warning(f"⚠️ {len(rogue_devices)} unauthorized device(s) detected")
    
    # Severity breakdown
    severity_counts = pd.DataFrame(rogue_devices)['severity'].value_counts()
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        # Severity pie chart
        fig = go.Figure(data=[go.Pie(
            labels=severity_counts.index,
            values=severity_counts.values,
            marker=dict(colors=['#ff4444', '#ffaa00', '#4444ff']),
            hole=0.4
        )])
        fig.update_layout(
            title="Alerts by Severity",
            height=300,
            showlegend=True
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Reason breakdown
        reason_counts = pd.DataFrame(rogue_devices)['reason'].value_counts()
        fig = px.bar(
            x=reason_counts.index,
            y=reason_counts.values,
            labels={'x': 'Detection Reason', 'y': 'Count'},
            title="Detection Reasons",
            color=reason_counts.values,
            color_continuous_scale='Reds'
        )
        fig.update_layout(height=300, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    
    # Detailed alert table
    st.subheader("Alert Details")
    
    df = pd.DataFrame(rogue_devices)
    
    # Color code by severity
    def highlight_severity(row):
        if row['severity'] == 'CRITICAL':
            return ['background-color: #ffcccc'] * len(row)
        elif row['severity'] == 'WARNING':
            return ['background-color: #fff4cc'] * len(row)
        else:
            return ['background-color: #ccf4ff'] * len(row)
    
    styled_df = df.style.apply(highlight_severity, axis=1)
    st.dataframe(styled_df, use_container_width=True)
    
    # Remediation actions
    st.subheader("Recommended Actions")
    for device in rogue_devices:
        if device['severity'] == 'CRITICAL':
            with st.expander(f"🔴 {device['device_id']} - {device['mac_address']}"):
                st.write(f"**Reason:** {device['reason']}")
                st.write(f"**Confidence:** {device['confidence']:.1%}")
                st.write("**Recommended Actions:**")
                st.write("1. Isolate device from network immediately")
                st.write("2. Investigate device origin and purpose")
                st.write("3. Review access logs for suspicious activity")
                st.write("4. Add to blacklist if confirmed malicious")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button(f"Quarantine {device['device_id']}", key=f"quarantine_{device['device_id']}"):
                        st.success(f"Quarantined {device['device_id']}")
                with col2:
                    if st.button(f"Whitelist {device['device_id']}", key=f"whitelist_{device['device_id']}"):
                        st.info(f"Added {device['device_id']} to whitelist")
                with col3:
                    if st.button(f"Investigate {device['device_id']}", key=f"investigate_{device['device_id']}"):
                        st.info(f"Investigation started for {device['device_id']}")


def render_config_drift(config_drift: List[Dict]):
    """Render configuration drift alerts"""
    st.subheader("Configuration Change Detection")
    
    if not config_drift:
        st.success("✅ No unauthorized configuration changes detected")
        return
    
    st.warning(f"⚠️ {len(config_drift)} configuration change(s) detected")
    
    # Change type breakdown
    col1, col2 = st.columns(2)
    
    with col1:
        change_types = pd.DataFrame(config_drift)['change_type'].value_counts()
        fig = px.bar(
            x=change_types.index,
            y=change_types.values,
            labels={'x': 'Change Type', 'y': 'Count'},
            title="Changes by Type",
            color=change_types.values,
            color_continuous_scale='Oranges'
        )
        fig.update_layout(height=300, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        severity_counts = pd.DataFrame(config_drift)['severity'].value_counts()
        fig = go.Figure(data=[go.Pie(
            labels=severity_counts.index,
            values=severity_counts.values,
            marker=dict(colors=['#ff4444', '#ffaa00', '#4444ff']),
            hole=0.4
        )])
        fig.update_layout(
            title="Changes by Severity",
            height=300,
            showlegend=True
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Detailed drift table
    st.subheader("Change Details")
    
    for drift in config_drift:
        severity_icon = "🔴" if drift['severity'] == 'CRITICAL' else "🟡" if drift['severity'] == 'WARNING' else "🔵"
        
        with st.expander(f"{severity_icon} {drift['device_id']} - {drift['change_type']}"):
            st.write(f"**Severity:** {drift['severity']}")
            st.write(f"**Change Type:** {drift['change_type']}")
            
            if 'changes' in drift and drift['changes']:
                st.write("**Detected Changes:**")
                
                changes = drift['changes']
                
                if 'added' in changes and changes['added']:
                    st.write("**Added:**")
                    st.json(changes['added'])
                
                if 'removed' in changes and changes['removed']:
                    st.write("**Removed:**")
                    st.json(changes['removed'])
                
                if 'modified' in changes and changes['modified']:
                    st.write("**Modified:**")
                    for key, change in changes['modified'].items():
                        st.write(f"- `{key}`: {change['old']} → {change['new']}")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"Approve Changes", key=f"approve_{drift['device_id']}"):
                    st.success(f"Changes approved for {drift['device_id']}")
            with col2:
                if st.button(f"Revert Changes", key=f"revert_{drift['device_id']}"):
                    st.warning(f"Reverting changes for {drift['device_id']}")


def render_security_timeline(timeline_data: List[Dict]):
    """Render security event timeline"""
    st.subheader("Security Event Timeline")
    
    if not timeline_data:
        st.info("No recent security events")
        return
    
    # Create timeline chart
    df = pd.DataFrame(timeline_data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Color map for event types
    color_map = {
        'rogue_device': '#ff4444',
        'config_drift': '#ffaa00',
        'security_scan': '#4444ff',
        'remediation': '#44ff44'
    }
    
    fig = px.scatter(
        df,
        x='timestamp',
        y='event_type',
        color='severity',
        size='impact',
        hover_data=['description'],
        title="Security Events Over Time",
        color_discrete_map={'CRITICAL': '#ff4444', 'WARNING': '#ffaa00', 'INFO': '#4444ff'}
    )
    
    fig.update_layout(
        height=400,
        xaxis_title="Time",
        yaxis_title="Event Type",
        showlegend=True
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Event log
    st.subheader("Event Log")
    
    for event in sorted(timeline_data, key=lambda x: x['timestamp'], reverse=True)[:10]:
        severity_icon = "🔴" if event['severity'] == 'CRITICAL' else "🟡" if event['severity'] == 'WARNING' else "🔵"
        st.write(f"{severity_icon} **{event['timestamp']}** - {event['event_type']}: {event['description']}")


def _get_mock_security_data(orchestrator) -> Dict:
    """Generate mock security data for demonstration"""
    
    # Mock rogue devices
    rogue_devices = [
        {
            'device_id': 'unknown_device_001',
            'mac_address': '00:1A:2B:3C:4D:5E',
            'ip_address': '192.168.1.250',
            'reason': 'unknown_mac',
            'severity': 'CRITICAL',
            'confidence': 0.95,
            'first_seen': datetime.now() - timedelta(hours=2)
        },
        {
            'device_id': 'plc_003',
            'mac_address': '00:1A:2B:3C:4D:5F',
            'ip_address': '192.168.1.103',
            'reason': 'abnormal_behavior',
            'severity': 'WARNING',
            'confidence': 0.72,
            'first_seen': datetime.now() - timedelta(hours=6)
        }
    ]
    
    # Mock config drift
    config_drift = [
        {
            'device_id': 'firewall_001',
            'change_type': 'CRITICAL_CHANGE',
            'severity': 'CRITICAL',
            'changes': {
                'modified': {
                    'firewall_rules': {
                        'old': 'deny_all_external',
                        'new': 'allow_all'
                    }
                }
            }
        },
        {
            'device_id': 'switch_002',
            'change_type': 'MODIFIED',
            'severity': 'WARNING',
            'changes': {
                'modified': {
                    'vlan_config': {
                        'old': 'vlan_10',
                        'new': 'vlan_20'
                    }
                }
            }
        }
    ]
    
    # Mock timeline
    timeline = [
        {
            'timestamp': datetime.now() - timedelta(hours=2),
            'event_type': 'rogue_device',
            'severity': 'CRITICAL',
            'impact': 10,
            'description': 'Unknown device detected on network'
        },
        {
            'timestamp': datetime.now() - timedelta(hours=4),
            'event_type': 'config_drift',
            'severity': 'CRITICAL',
            'impact': 8,
            'description': 'Firewall rules modified'
        },
        {
            'timestamp': datetime.now() - timedelta(hours=6),
            'event_type': 'rogue_device',
            'severity': 'WARNING',
            'impact': 5,
            'description': 'Abnormal traffic pattern detected'
        },
        {
            'timestamp': datetime.now() - timedelta(hours=8),
            'event_type': 'security_scan',
            'severity': 'INFO',
            'impact': 2,
            'description': 'Scheduled security scan completed'
        }
    ]
    
    return {
        'security_score': 72.0,
        'score_change': -8.0,
        'rogue_count': len(rogue_devices),
        'rogue_change': 1,
        'drift_count': len(config_drift),
        'drift_change': 1,
        'critical_count': 2,
        'critical_change': 2,
        'rogue_devices': rogue_devices,
        'config_drift': config_drift,
        'timeline': timeline
    }
