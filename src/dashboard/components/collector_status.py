"""
Collector Status Component

Displays status of data collectors (SNMP, Modbus, Profinet).
"""

import streamlit as st
from datetime import datetime, timedelta
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


def get_collector_status(db_manager) -> Dict[str, Dict[str, Any]]:
    """
    Get status of all collectors
    
    Args:
        db_manager: Database manager instance
    
    Returns:
        Dictionary with collector status
    """
    status = {
        'snmp': {'running': False, 'device_count': 0, 'last_update': None, 'metrics_count': 0},
        'modbus': {'running': False, 'device_count': 0, 'last_update': None, 'metrics_count': 0},
        'profinet': {'running': False, 'device_count': 0, 'last_update': None, 'metrics_count': 0}
    }
    
    try:
        from src.database.repository import AssetRepository, MetricsRepository
        
        with db_manager.get_session() as session:
            asset_repo = AssetRepository(session)
            metrics_repo = MetricsRepository(session)
            
            # Check each protocol
            for protocol in ['snmp', 'modbus', 'profinet']:
                # Count devices with this protocol in metadata
                all_assets = asset_repo.get_all(status='active')
                protocol_devices = [
                    a for a in all_assets
                    if a.meta_data and a.meta_data.get('protocol') == protocol
                ]
                
                status[protocol]['device_count'] = len(protocol_devices)
                
                # Check for recent metrics (last 5 minutes)
                recent_time = datetime.utcnow() - timedelta(minutes=5)
                
                # Query recent metrics with this protocol tag
                recent_metrics = session.execute(
                    """
                    SELECT COUNT(*), MAX(time)
                    FROM metrics
                    WHERE tags->>'source' = :protocol
                      AND time >= :recent_time
                    """,
                    {'protocol': protocol, 'recent_time': recent_time}
                ).fetchone()
                
                if recent_metrics and recent_metrics[0] > 0:
                    status[protocol]['running'] = True
                    status[protocol]['metrics_count'] = recent_metrics[0]
                    status[protocol]['last_update'] = recent_metrics[1]
    
    except Exception as e:
        logger.error(f"Error getting collector status: {e}")
    
    return status


def render_collector_status_sidebar(db_manager):
    """
    Render collector status in sidebar
    
    Args:
        db_manager: Database manager instance
    """
    st.sidebar.markdown("### 📡 Collector Status")
    
    status = get_collector_status(db_manager)
    
    for protocol, info in status.items():
        protocol_name = protocol.upper()
        
        if info['running']:
            st.sidebar.success(
                f"✅ {protocol_name}: {info['device_count']} devices"
            )
            if info['last_update']:
                time_ago = (datetime.utcnow() - info['last_update']).seconds
                st.sidebar.caption(f"   Last update: {time_ago}s ago")
        else:
            if info['device_count'] > 0:
                st.sidebar.warning(
                    f"⚠️ {protocol_name}: {info['device_count']} devices (no data)"
                )
            else:
                st.sidebar.info(f"ℹ️ {protocol_name}: No devices")


def render_collector_management(db_manager):
    """
    Render full collector management interface
    
    Args:
        db_manager: Database manager instance
    """
    st.markdown("## 📡 Data Collector Management")
    st.caption("Monitor and manage data collection from industrial devices")
    
    # Get status
    status = get_collector_status(db_manager)
    
    # Overview metrics
    col1, col2, col3, col4 = st.columns(4)
    
    total_devices = sum(s['device_count'] for s in status.values())
    active_collectors = sum(1 for s in status.values() if s['running'])
    total_metrics = sum(s['metrics_count'] for s in status.values())
    
    col1.metric("Total Devices", total_devices)
    col2.metric("Active Collectors", f"{active_collectors}/3")
    col3.metric("Metrics (5min)", total_metrics)
    col4.metric("Health", "Good" if active_collectors > 0 else "Offline")
    
    st.markdown("---")
    
    # Tabs for each protocol
    tabs = st.tabs(["SNMP v3", "Modbus TCP", "Profinet DCP"])
    
    with tabs[0]:  # SNMP
        render_snmp_status(db_manager, status['snmp'])
    
    with tabs[1]:  # Modbus
        render_modbus_status(db_manager, status['modbus'])
    
    with tabs[2]:  # Profinet
        render_profinet_status(db_manager, status['profinet'])


def render_snmp_status(db_manager, status: Dict[str, Any]):
    """Render SNMP collector status"""
    st.markdown("### SNMP v3 Collector")
    
    # Status indicator
    if status['running']:
        st.success("✅ Collector is running")
    else:
        st.error("❌ Collector is offline")
    
    # Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Devices", status['device_count'])
    col2.metric("Metrics (5min)", status['metrics_count'])
    
    if status['last_update']:
        time_ago = (datetime.utcnow() - status['last_update']).seconds
        col3.metric("Last Update", f"{time_ago}s ago")
    else:
        col3.metric("Last Update", "Never")
    
    # Device list
    st.markdown("#### Configured Devices")
    
    try:
        from src.database.repository import AssetRepository
        
        with db_manager.get_session() as session:
            repo = AssetRepository(session)
            all_assets = repo.get_all(status='active')
            snmp_devices = [
                a for a in all_assets
                if a.meta_data and a.meta_data.get('protocol') == 'snmp'
            ]
            
            if snmp_devices:
                device_data = []
                for device in snmp_devices:
                    device_data.append({
                        'Device ID': device.asset_id,
                        'Name': device.name,
                        'IP Address': str(device.ip_address) if device.ip_address else 'N/A',
                        'Type': device.type,
                        'Status': device.status
                    })
                
                st.dataframe(device_data, use_container_width=True)
            else:
                st.info("No SNMP devices configured")
    
    except Exception as e:
        st.error(f"Error loading devices: {e}")


def render_modbus_status(db_manager, status: Dict[str, Any]):
    """Render Modbus collector status"""
    st.markdown("### Modbus TCP Collector")
    
    # Status indicator
    if status['running']:
        st.success("✅ Collector is running")
    else:
        st.error("❌ Collector is offline")
    
    # Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Devices", status['device_count'])
    col2.metric("Metrics (5min)", status['metrics_count'])
    
    if status['last_update']:
        time_ago = (datetime.utcnow() - status['last_update']).seconds
        col3.metric("Last Update", f"{time_ago}s ago")
    else:
        col3.metric("Last Update", "Never")
    
    # Device list
    st.markdown("#### Configured Devices")
    
    try:
        from src.database.repository import AssetRepository
        
        with db_manager.get_session() as session:
            repo = AssetRepository(session)
            all_assets = repo.get_all(status='active')
            modbus_devices = [
                a for a in all_assets
                if a.meta_data and a.meta_data.get('protocol') == 'modbus'
            ]
            
            if modbus_devices:
                device_data = []
                for device in modbus_devices:
                    device_data.append({
                        'Device ID': device.asset_id,
                        'Name': device.name,
                        'IP Address': str(device.ip_address) if device.ip_address else 'N/A',
                        'Type': device.type,
                        'Status': device.status
                    })
                
                st.dataframe(device_data, use_container_width=True)
            else:
                st.info("No Modbus devices configured")
    
    except Exception as e:
        st.error(f"Error loading devices: {e}")


def render_profinet_status(db_manager, status: Dict[str, Any]):
    """Render Profinet collector status"""
    st.markdown("### Profinet DCP Collector")
    
    # Status indicator
    if status['running']:
        st.success("✅ Collector is running")
    else:
        st.error("❌ Collector is offline")
    
    # Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Devices", status['device_count'])
    col2.metric("Metrics (5min)", status['metrics_count'])
    
    if status['last_update']:
        time_ago = (datetime.utcnow() - status['last_update']).seconds
        col3.metric("Last Update", f"{time_ago}s ago")
    else:
        col3.metric("Last Update", "Never")
    
    # Device list
    st.markdown("#### Discovered Devices")
    
    try:
        from src.database.repository import AssetRepository
        
        with db_manager.get_session() as session:
            repo = AssetRepository(session)
            all_assets = repo.get_all(status='active')
            profinet_devices = [
                a for a in all_assets
                if a.meta_data and a.meta_data.get('protocol') == 'profinet'
            ]
            
            if profinet_devices:
                device_data = []
                for device in profinet_devices:
                    device_data.append({
                        'Device ID': device.asset_id,
                        'Name': device.name,
                        'MAC Address': str(device.mac_address) if device.mac_address else 'N/A',
                        'IP Address': str(device.ip_address) if device.ip_address else 'N/A',
                        'Type': device.type,
                        'Status': device.status
                    })
                
                st.dataframe(device_data, use_container_width=True)
            else:
                st.info("No Profinet devices discovered")
    
    except Exception as e:
        st.error(f"Error loading devices: {e}")
