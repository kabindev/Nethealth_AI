"""
Live Network Setup UI Component

Streamlit component for discovering and configuring real network devices
for the competition demo.
"""

import streamlit as st
from typing import List, Dict
import socket


DEVICE_TYPES = ["router", "switch", "server", "workstation", "pc", "laptop", "phone", "printer", "camera", "iot", "unknown"]

STATUS_COLORS = {
    "healthy": "🟢",
    "degraded": "🟡",
    "warning": "🟠",
    "critical": "🔴",
}


def render_live_network_setup() -> List[Dict]:
    """
    Renders the device discovery and setup UI.
    Returns list of configured devices when user clicks Start Monitoring.
    Returns None if not yet started.
    """
    st.markdown("### 🔍 Discover Devices on Your Network")

    # Subnet input
    col1, col2 = st.columns([2, 1])
    with col1:
        # Try to auto-detect local subnet
        default_subnet = _detect_local_subnet()
        subnet = st.text_input(
            "Network Subnet (CIDR)",
            value=default_subnet,
            help="e.g. 192.168.1.0/24 — scans this range for live devices",
            key="live_subnet_input",
        )
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        scan_btn = st.button("🔎 Discover Devices", type="primary", key="live_scan_btn")

    if scan_btn:
        with st.spinner(f"Scanning {subnet} — this may take 15-30 seconds..."):
            from src.ingestion.live_collector import scan_subnet, resolve_hostname
            live_ips = scan_subnet(subnet, timeout=1.0, max_workers=50)

        if not live_ips:
            st.error("No live devices found. Check the subnet and try again.")
            return None

        # Build initial device list with hostnames
        discovered = []
        with st.spinner("Resolving hostnames..."):
            for i, ip in enumerate(live_ips):
                hostname = resolve_hostname(ip)
                guessed_type = _guess_device_type(hostname, ip, i)
                device_id = f"device-{i+1}" if i > 0 else "gateway-1"
                discovered.append({
                    "id": device_id,
                    "ip": ip,
                    "hostname": hostname,
                    "type": guessed_type,
                    "name": hostname if hostname != ip else f"{guessed_type}-{i+1}",
                })

        st.session_state["discovered_devices"] = discovered
        st.success(f"✅ Found **{len(live_ips)}** live devices!")

    # Show discovered devices table for editing
    if "discovered_devices" in st.session_state and st.session_state["discovered_devices"]:
        devices = st.session_state["discovered_devices"]

        st.markdown("#### 🖥️ Configure Discovered Devices")
        st.caption("Edit device names and types, then click **Start Live Monitoring**.")

        updated_devices = []
        for i, dev in enumerate(devices):
            with st.expander(
                f"{STATUS_COLORS.get('healthy', '⚪')} {dev['ip']} — {dev.get('hostname', dev['ip'])}",
                expanded=(i < 5),  # Expand first 5 by default
            ):
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    dev_name = st.text_input(
                        "Device Name", value=dev["name"], key=f"live_name_{i}"
                    )
                with col2:
                    dev_type = st.selectbox(
                        "Device Type",
                        DEVICE_TYPES,
                        index=DEVICE_TYPES.index(dev["type"]) if dev["type"] in DEVICE_TYPES else 0,
                        key=f"live_type_{i}",
                    )
                with col3:
                    st.markdown(f"**IP:** `{dev['ip']}`")
                    if dev.get("hostname") != dev["ip"]:
                        st.caption(dev.get("hostname", ""))

                updated_devices.append({
                    "id": dev["id"],
                    "ip": dev["ip"],
                    "hostname": dev.get("hostname", dev["ip"]),
                    "type": dev_type,
                    "name": dev_name,
                })

        st.markdown("---")
        col1, col2 = st.columns([1, 2])
        with col1:
            poll_interval = st.select_slider(
                "Polling Interval",
                options=[10, 15, 20, 30, 60],
                value=15,
                format_func=lambda x: f"{x}s",
                help="How often to poll each device",
            )
        with col2:
            st.info(
                f"📡 Will monitor **{len(updated_devices)} devices** "
                f"every **{poll_interval}s** — data feeds directly into the AI pipeline."
            )

        if st.button("🚀 Start Live Monitoring", type="primary", key="live_start_btn"):
            st.session_state["live_devices"] = updated_devices
            st.session_state["live_poll_interval"] = poll_interval
            return updated_devices

    return None


def render_live_status_sidebar(collector=None):
    """Render compact live monitoring status in the sidebar."""
    if collector is None:
        return

    status = collector.get_status()
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📡 Live Monitor")

    if status["running"]:
        st.sidebar.success(f"🟢 Active — {status['device_count']} devices")
    else:
        st.sidebar.error("🔴 Stopped")

    st.sidebar.caption(
        f"Polls: {status['poll_count']} | "
        f"Records: {status['total_rows']}"
    )
    if status["last_poll"]:
        from datetime import datetime
        last = datetime.fromisoformat(status["last_poll"])
        st.sidebar.caption(f"Last poll: {last.strftime('%H:%M:%S')}")

    # Per-device mini-status
    try:
        from src.utils.live_data_bridge import get_live_summary
        summary = get_live_summary(collector)
        if summary:
            for asset_id, info in list(summary.items())[:6]:  # Show max 6
                icon = STATUS_COLORS.get(info["status"], "⚪")
                st.sidebar.markdown(
                    f"{icon} `{asset_id}` — {info['latency_ms']}ms / {info['packet_loss_pct']}% loss"
                )
    except Exception:
        pass


# ---- Helpers ----

def _detect_local_subnet() -> str:
    """Try to detect the local network subnet automatically."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        # Replace last octet with 0/24
        parts = local_ip.split(".")
        parts[-1] = "0"
        return ".".join(parts) + "/24"
    except Exception:
        return "192.168.1.0/24"


def _guess_device_type(hostname: str, ip: str, index: int) -> str:
    """Heuristically guess device type from hostname or IP position."""
    h = hostname.lower()
    if index == 0 or any(k in h for k in ["router", "gateway", "gw", "modem", "dsl", "fiber"]):
        return "router"
    if any(k in h for k in ["switch", "sw-", "sw_"]):
        return "switch"
    if any(k in h for k in ["server", "srv", "nas", "storage", "pi", "ubuntu", "debian"]):
        return "server"
    if any(k in h for k in ["print", "hp", "canon", "epson", "brother"]):
        return "printer"
    if any(k in h for k in ["cam", "ipcam", "dvr", "nvr"]):
        return "camera"
    if any(k in h for k in ["iphone", "android", "pixel", "samsung", "oneplus", "mi-", "redmi"]):
        return "phone"
    if any(k in h for k in ["macbook", "imac", "mac-"]):
        return "laptop"
    if any(k in h for k in ["desktop", "workstation", "pc-"]):
        return "workstation"
    return "pc"
