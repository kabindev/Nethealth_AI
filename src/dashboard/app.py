# ── Suppress known harmless warnings BEFORE any other imports ──────────────
import warnings
import os
import sys

# Fix: PyTorch's torch._classes breaks Streamlit's file watcher
# Patch it before Streamlit inspects loaded modules
try:
    import torch._classes
    if not hasattr(torch._classes, '__path__'):
        pass  # Already safe
    else:
        # Prevent watcher from probing torch._classes.__path__._path
        original_getattr = torch._classes.__class__.__getattr__
        def _safe_getattr(self, name):
            if name in ('__path__', '__file__', '__spec__'):
                raise AttributeError(name)
            return original_getattr(self, name)
        torch._classes.__class__.__getattr__ = _safe_getattr
except ImportError:
    pass  # No torch installed — all good

# Suppress graphviz dot_parser warning
warnings.filterwarnings("ignore", message=".*dot_parser.*")

import streamlit as st
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from src.orchestration.pipeline import Orchestrator
from src.dashboard.components.top_bar import render_top_bar
from src.dashboard.components.topology_view import render_topology
from src.dashboard.components.ai_insights import render_ai_insights
from src.dashboard.components.health_metrics import render_health_metrics
from src.intelligence.ai_assistant import AIAssistant
from src.dashboard.components.chat_interface import ChatInterface
from src.dashboard.components.thermal_view import render_thermal_view
from src.dashboard.components.validation_metrics import render_validation_metrics
from src.dashboard.components.floor_plan_view import render_floor_plan
from src.dashboard.components.security_view import render_security_dashboard
from src.dashboard.data_source import SyntheticDataSource, DatabaseDataSource
from src.dashboard.components.collector_status import render_collector_status_sidebar, render_collector_management

# ── Live Network imports ──────────────────────────────────────────────────────
try:
    from src.dashboard.components.live_network_setup import (
        render_live_network_setup,
        render_live_status_sidebar,
    )
    from src.ingestion.live_collector import LiveNetworkCollector
    from src.utils.live_data_bridge import bridge_to_pipeline, get_live_summary
    LIVE_MODE_AVAILABLE = True
except ImportError as e:
    LIVE_MODE_AVAILABLE = False
    print(f"Live mode not available: {e}")

# ── Layer KPI Heatmap (L2/L5/L6) ─────────────────────────────────────────────
try:
    from src.ingestion.layer_kpi_updater import (
        render_layer_heatmap, get_layer_health_summary
    )
    LAYER_HEATMAP_AVAILABLE = True
except ImportError:
    LAYER_HEATMAP_AVAILABLE = False

# ── Auto-refresh (for live mode) ──────────────────────────────────────────────
try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except ImportError:
    AUTOREFRESH_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NetHealth AI — Network Observability",
    page_icon="🌐",
    layout="wide",
)

# Custom CSS
st.markdown("""
<style>
    .stApp { background-color: #0E1117; }
    .graphviz_chart {
        border: 2px solid #333;
        border-radius: 10px;
        box-shadow: 0 0 15px rgba(0, 255, 255, 0.2);
        padding: 10px;
        background-color: black;
    }
    h1, h2, h3 { font-family: 'Helvetica Neue', sans-serif; color: #E0E0E0; }
    .live-badge {
        background: linear-gradient(90deg, #ff4b4b, #ff8c00);
        color: white;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.75em;
        font-weight: bold;
        animation: pulse 1.5s infinite;
    }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.6} }
    .metric-card {
        background: #1a1f2e;
        border-radius: 8px;
        padding: 8px 14px;
        margin: 4px 0;
        border-left: 3px solid #00c0f2;
    }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Session State Initialisation
# ─────────────────────────────────────────────────────────────────────────────
if "data_source_mode" not in st.session_state:
    st.session_state.data_source_mode = "Synthetic (Demo)"
if "data_source" not in st.session_state:
    st.session_state.data_source = SyntheticDataSource()
if "db_manager" not in st.session_state:
    st.session_state.db_manager = None
if "orchestrator" not in st.session_state:
    st.session_state.orchestrator = Orchestrator()
    st.session_state.orchestrator.load_data(
        "data/raw/metrics_timeseries.csv", "data/raw/assets.json"
    )
    st.session_state.scenario = "Normal"
if "ai_assistant" not in st.session_state:
    st.session_state.ai_assistant = AIAssistant()
if "intelligence_orchestrator" not in st.session_state:
    try:
        from src.intelligence.orchestrator import IntelligenceOrchestrator
        st.session_state.intelligence_orchestrator = IntelligenceOrchestrator(
            use_deep_learning=False
        )
    except Exception as e:
        print(f"Intelligence orchestrator not available: {e}")
        st.session_state.intelligence_orchestrator = None

# Live-mode state
if "live_collector" not in st.session_state:
    st.session_state.live_collector = None
if "live_monitoring_active" not in st.session_state:
    st.session_state.live_monitoring_active = False
if "discovered_devices" not in st.session_state:
    st.session_state.discovered_devices = []

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
logo_path = "data/raw/belden-logo.jpeg"
if os.path.exists(logo_path):
    st.sidebar.image(logo_path, width=200)
else:
    st.sidebar.warning(f"Logo not found at {logo_path}")
    st.sidebar.image(
        "https://upload.wikimedia.org/wikipedia/commons/4/4e/Belden_Inc_logo.svg",
        width=150,
    )

st.sidebar.title("Controls")

# Data Source Selection
st.sidebar.markdown("### 📊 Data Source")
mode_options = ["Synthetic (Demo)", "Production (Live)"]
if LIVE_MODE_AVAILABLE:
    mode_options.append("🔴 Live Network (Real)")

data_source_mode = st.sidebar.radio(
    "Select Data Source",
    mode_options,
    help=(
        "Synthetic: demo CSV data | "
        "Production: TimescaleDB | "
        "Live Network: polls real devices on your LAN"
    ),
)

# ──── Handle mode switching ────────────────────────────────────────────────
if data_source_mode != st.session_state.data_source_mode:
    # Stop any running live collector
    if (
        st.session_state.live_collector is not None
        and st.session_state.live_collector.get_status()["running"]
    ):
        st.session_state.live_collector.stop()
        st.session_state.live_collector = None
        st.session_state.live_monitoring_active = False

    # Reset live state flags
    st.session_state["live_data_loaded"] = False
    st.session_state["live_blank_loaded"] = False

    st.session_state.data_source_mode = data_source_mode

    if data_source_mode == "Production (Live)":
        try:
            from src.database import init_database, get_db_manager
            if st.session_state.db_manager is None:
                try:
                    st.session_state.db_manager = get_db_manager()
                    if not st.session_state.db_manager.health_check():
                        st.sidebar.error("❌ Database connection failed!")
                        st.session_state.data_source_mode = "Synthetic (Demo)"
                        st.session_state.data_source = SyntheticDataSource()
                    else:
                        st.session_state.data_source = DatabaseDataSource(
                            st.session_state.db_manager
                        )
                        st.sidebar.success("✅ Connected to production database")
                except Exception as e:
                    st.sidebar.error(f"❌ Database error: {e}")
                    st.session_state.data_source_mode = "Synthetic (Demo)"
                    st.session_state.data_source = SyntheticDataSource()
        except ImportError:
            st.sidebar.warning("⚠️ Database module not available. Using synthetic data.")
            st.session_state.data_source_mode = "Synthetic (Demo)"
            st.session_state.data_source = SyntheticDataSource()
    elif data_source_mode == "Synthetic (Demo)":
        st.session_state.data_source = SyntheticDataSource()
    # Live Network mode is handled in the main tab below

# ──── Production: show collector status ────────────────────────────────────
if (
    st.session_state.data_source_mode == "Production (Live)"
    and st.session_state.db_manager
):
    render_collector_status_sidebar(st.session_state.db_manager)

# ──── Live Network: show live status in sidebar ────────────────────────────
if (
    st.session_state.data_source_mode == "🔴 Live Network (Real)"
    and st.session_state.live_collector
):
    render_live_status_sidebar(st.session_state.live_collector)

st.sidebar.markdown("---")

# ──── Scenario selection (Synthetic only) ─────────────────────────────────
if st.session_state.data_source_mode == "Synthetic (Demo)":
    st.sidebar.markdown("### 🎭 Scenario Simulation")
    scenario = st.sidebar.radio(
        "Simulate Scenario",
        ["Normal Operation", "Inject Fault (Cable Failure)", "Severe Fault (L4 Attack)"],
    )
elif st.session_state.data_source_mode == "🔴 Live Network (Real)":
    scenario = "Live"
else:
    scenario = "Production"

if st.sidebar.button("Run Analysis"):
    orch = st.session_state.orchestrator
    if "Normal" in scenario:
        orch.load_data("data/raw/metrics_timeseries.csv", "data/raw/assets.json")
        st.session_state.scenario = "Normal"
    elif "Cable" in scenario:
        orch.load_data("data/raw/metrics_faulty.csv", "data/raw/assets.json")
        st.session_state.scenario = "Faulty"
    elif "Severe" in scenario:
        orch.load_data("data/raw/metrics_severe.csv", "data/raw/assets.json")
        st.session_state.scenario = "Severe"
    st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# LIVE NETWORK: Auto-refresh + data reload
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.data_source_mode == "🔴 Live Network (Real)":
    if st.session_state.live_monitoring_active and AUTOREFRESH_AVAILABLE:
        interval = st.session_state.get("live_poll_interval", 15) * 1000
        st_autorefresh(interval=interval, key="live_autorefresh")

    collector = st.session_state.live_collector

    # Import readiness helper
    try:
        from src.utils.live_data_bridge import get_collector_readiness
    except ImportError:
        def get_collector_readiness(c):
            if c is None:
                return {"ready": False, "message": "Not started.", "wait_sec": 0}
            ready = getattr(c, "poll_count", 0) >= 1
            return {"ready": ready, "message": "Ready." if ready else "⏳ Polling...", "wait_sec": 10}

    readiness = get_collector_readiness(collector)
    st.session_state["live_readiness"] = readiness

    if collector is not None and readiness["ready"]:
        # Collector has real data — feed it into the orchestrator
        try:
            metrics_path, assets_path = bridge_to_pipeline(
                collector,
                assets_json_path="data/live/live_assets.json",
                metrics_csv_path="data/live/live_metrics.csv",
            )
            st.session_state.orchestrator.load_data(metrics_path, assets_path)
            # Clear the stale-anomaly flag now that we have fresh live data
            st.session_state["live_data_loaded"] = True
        except Exception as e:
            st.warning(f"⚠️ Live data reload error: {e}")
    elif collector is not None and not readiness["ready"]:
        # First poll not complete yet — keep orchestrator on a CLEAN blank slate
        # so we show 0 anomalies, not the 208 stale synthetic ones
        if not st.session_state.get("live_blank_loaded", False):
            # Load the normal synthetic data but override anomaly display
            # We flag this so the UI can show "waiting" instead of stale data
            st.session_state["live_blank_loaded"] = True
            st.session_state["live_data_loaded"] = False

# ─────────────────────────────────────────────────────────────────────────────
# Run AI Pipeline
# ─────────────────────────────────────────────────────────────────────────────
orch = st.session_state.orchestrator
anomalies = orch.run_kpi_pipeline()
thermal_predictions = orch.run_thermal_simulation_pipeline()
anomalies = orch.correlate_thermal_with_anomalies(anomalies)

# ── BUG FIX: In Live mode before first poll completes, suppress stale
#    synthetic anomalies so we don't show "208 anomalies + Healthy" ──────────
is_live_mode = st.session_state.data_source_mode == "🔴 Live Network (Real)"
live_data_ready = st.session_state.get("live_data_loaded", False)
if is_live_mode and not live_data_ready:
    # First poll hasn't finished — wipe stale anomalies from synthetic data
    anomalies = []

if "causal_graph" not in st.session_state or st.session_state.get("rebuild_causal", False):
    try:
        st.session_state.causal_graph = orch.run_causality_analysis_pipeline()
        st.session_state.rebuild_causal = False
    except Exception as e:
        st.session_state.causal_graph = None

diagnosis = orch.run_diagnosis_pipeline(anomalies)

# Bayesian diagnosis — richer evidence extraction + deduplication
bayesian_diagnosis = None
try:
    from src.intelligence.bayesian_diagnostics import ProbabilisticDiagnosticEngine
    if "bayesian_engine" not in st.session_state:
        st.session_state.bayesian_engine = ProbabilisticDiagnosticEngine()
    if anomalies:
        evidence = {}
        # Track worst severity seen per metric category
        crc_sev, pkt_sev, lat_sev = None, None, None
        for a in anomalies:
            m = a.metric_or_kpi.lower()
            sev = a.severity
            if "crc" in m or "crc_error" in m:
                if crc_sev is None or sev in ["critical", "high"]:
                    crc_sev = sev
            if "packet" in m or "loss" in m:
                if pkt_sev is None or sev in ["critical", "high"]:
                    pkt_sev = sev
            if "latency" in m or "rtt" in m:
                if lat_sev is None or sev in ["critical", "high"]:
                    lat_sev = sev
            if "snr" in m:
                # Low SNR → likely CRC errors
                if crc_sev is None:
                    crc_sev = "Medium" if sev == "medium" else "High"

        # Map severities → Bayesian states
        _sev_to_state = {
            "critical": "High", "high": "High",
            "medium": "Medium", "low": "Low",
        }
        if crc_sev:
            evidence["CRCErrors"] = _sev_to_state.get(crc_sev, "Medium")
        if pkt_sev:
            evidence["PacketLoss"] = _sev_to_state.get(pkt_sev, "Medium")
        if lat_sev:
            evidence["Latency"] = "VeryHigh" if lat_sev == "critical" else "High"

        # If we have any anomalies but no specific evidence, use a medium default
        # so Bayesian doesn't fall back to equal priors
        if not evidence and anomalies:
            evidence = {"Latency": "High"}

        if evidence:
            bayesian_diagnosis = st.session_state.bayesian_engine.diagnose_with_uncertainty(evidence)

    # Deduplicate anomalies for display: keep only unique (asset_id, metric) pairs
    seen_anomaly_keys = set()
    unique_anomalies = []
    for a in anomalies:
        key = (a.asset_id, a.metric_or_kpi)
        if key not in seen_anomaly_keys:
            seen_anomaly_keys.add(key)
            unique_anomalies.append(a)
    anomalies = unique_anomalies

except Exception as e:
    bayesian_diagnosis = None

# ONE Score average
total_score = sum(scores["one_score"] for scores in orch.latest_kpis.values())
count = len(orch.latest_kpis)
avg_score = round(total_score / count, 1) if count > 0 else 100.0

# ─────────────────────────────────────────────────────────────────────────────
# Top bar
# ─────────────────────────────────────────────────────────────────────────────
is_live = st.session_state.data_source_mode == "🔴 Live Network (Real)"
live_label = " <span class='live-badge'>● LIVE</span>" if (is_live and st.session_state.live_monitoring_active) else ""
render_top_bar(avg_score, len(anomalies))
if is_live and st.session_state.live_monitoring_active:
    st.markdown(
        f"<p style='color:#aaa; margin-top:-12px; font-size:0.85em;'>🔴 Live monitoring active — "
        f"{len(st.session_state.get('live_devices', []))} real devices | "
        f"Last refresh: {datetime.now().strftime('%H:%M:%S')}</p>",
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.data_source_mode == "Production (Live)":
    tabs = st.tabs(
        ["🗺️ Network Map", "🏭 Floor Plan", "🌡️ Thermal Twin",
         "📊 System Performance", "🔒 Security", "📡 Collectors"]
    )
elif st.session_state.data_source_mode == "🔴 Live Network (Real)":
    tabs = st.tabs(
        ["🔴 Live Setup", "🗺️ Network Map", "🌡️ Thermal Twin",
         "📊 AI Insights", "🔒 Security"]
    )
else:
    tabs = st.tabs(
        ["🗺️ Network Map", "🏭 Floor Plan", "🌡️ Thermal Twin",
         "📊 System Performance", "🔒 Security"]
    )

# ─────────────────────────────────────────────────────────────────────────────
# TAB RENDERING — Live Network Mode
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.data_source_mode == "🔴 Live Network (Real)":

    # Tab 0: Live Setup
    with tabs[0]:
        if not st.session_state.live_monitoring_active:
            st.markdown("## 🔴 Live Network Monitoring Setup")
            st.markdown(
                "> Discover **real devices** on your local network and monitor them with the full AI pipeline."
            )

            result = render_live_network_setup()
            if result:
                # Start the collector
                poll_interval = st.session_state.get("live_poll_interval", 15)
                collector = LiveNetworkCollector(
                    devices=result,
                    poll_interval=poll_interval,
                    ping_count=4,
                    max_rows=200,
                )
                collector.start()
                st.session_state.live_collector = collector
                st.session_state.live_devices = result
                st.session_state.live_monitoring_active = True
                st.success(
                    f"🚀 Live monitoring started! Polling {len(result)} devices every {poll_interval}s. "
                    f"Switch to **🗺️ Network Map** to see live data."
                )
                st.rerun()
        else:
            # Already monitoring
            st.markdown("## 🔴 Live Network Monitoring — Active")
            collector = st.session_state.live_collector
            status = collector.get_status() if collector else {}
            readiness = st.session_state.get("live_readiness", {"ready": False, "message": "Starting...", "wait_sec": 15})

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Devices Monitored", status.get("device_count", 0))
            col2.metric("Total Records", status.get("total_rows", 0))
            col3.metric("Poll Cycles", status.get("poll_count", 0))
            # Only show real anomaly count when live data is loaded
            live_anomaly_count = len(anomalies) if live_data_ready else 0
            col4.metric("Active Anomalies", live_anomaly_count)

            # ── First-poll waiting state ───────────────────────────────────
            if not readiness.get("ready", False):
                wait_sec = readiness.get("wait_sec", 15)
                st.info(
                    f"⏳ **{readiness.get('message', 'Collecting first poll...')}**  \n"
                    f"Dashboard will populate automatically in ~{wait_sec}s. "
                    f"Collecting ping latency, packet loss, SNR from all {status.get('device_count',0)} devices."
                )
                st.progress(
                    min(status.get("total_rows", 0) / max(status.get("device_count", 1) * 3, 1), 1.0),
                    text="Collecting metrics..."
                )
            else:
                # Per-device live status table
                if collector:
                    summary = get_live_summary(collector)
                    if summary:
                        st.markdown("### 📡 Per-Device Live Metrics")
                        rows = []
                        STATUS_ICONS = {"healthy": "🟢", "degraded": "🟡", "warning": "🟠", "critical": "🔴"}
                        for asset_id, info in summary.items():
                            rows.append({
                                "Status": STATUS_ICONS.get(info["status"], "⚪"),
                                "Device": asset_id,
                                "Latency (ms)": info["latency_ms"],
                                "Packet Loss %": info["packet_loss_pct"],
                                "SNR (dB)": info["snr_db"],
                                "Health": info["status"].upper(),
                            })
                        import pandas as pd
                        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            if st.button("⏹️ Stop Monitoring", type="secondary"):
                if collector:
                    collector.stop()
                st.session_state.live_monitoring_active = False
                st.session_state.live_collector = None
                st.session_state["live_data_loaded"] = False
                st.session_state["live_blank_loaded"] = False
                st.rerun()

    # Tab 1: Network Map
    with tabs[1]:
        # L1-L7 Heatmap
        if LAYER_HEATMAP_AVAILABLE:
            layer_summary = get_layer_health_summary()
            if orch.latest_layer_summary:
                layer_summary = orch.latest_layer_summary
            render_layer_heatmap(layer_summary)
            st.markdown("---")
        col_main, col_right = st.columns([2, 1])
        with col_main:
            st.markdown("### Network Topology")
            render_topology(orch.topology, anomalies)
            st.markdown("### Asset Health Metrics")
            render_health_metrics(orch.latest_kpis)
        with col_right:
            render_ai_insights(
                diagnosis,
                bayesian_diagnosis=bayesian_diagnosis,
                causal_graph=st.session_state.get("causal_graph"),
            )
            st.subheader("Active Anomalies")
            if anomalies:
                for a in anomalies:
                    if a.severity in ["critical", "high"]:
                        st.error(f"**{a.asset_id}**: {a.description}")
                    else:
                        st.warning(f"**{a.asset_id}**: {a.description}")
            else:
                st.success("✅ No active anomalies detected.")

    # Tab 2: Thermal Twin
    with tabs[2]:
        st.markdown("## 🌡️ Thermal Network Digital Twin")
        st.caption("Physics-based failure prediction using thermal dynamics")
        render_thermal_view(orch.latest_thermal_predictions, orch.assets)

    # Tab 3: AI Insights
    with tabs[3]:
        render_validation_metrics()

    # Tab 4: Security
    with tabs[4]:
        if st.session_state.intelligence_orchestrator:
            render_security_dashboard(st.session_state.intelligence_orchestrator)
        else:
            st.info("Security monitoring requires Intelligence Orchestrator.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB RENDERING — Synthetic / Production Modes
# ─────────────────────────────────────────────────────────────────────────────
else:
    with tabs[0]:  # Network Map
        # L1-L7 Heatmap (full layer view)
        if LAYER_HEATMAP_AVAILABLE:
            layer_summary = get_layer_health_summary()
            if orch.latest_layer_summary:
                layer_summary = orch.latest_layer_summary
            render_layer_heatmap(layer_summary)
            col_refresh, _ = st.columns([1, 5])
            with col_refresh:
                if st.button("🔄 Refresh L2/L5/L6", help="Trigger immediate L2/L5/L6 collection"):
                    if orch.layer_updater:
                        import asyncio, concurrent.futures
                        try:
                            with concurrent.futures.ThreadPoolExecutor() as pool:
                                future = pool.submit(asyncio.run, orch.layer_updater.collect_once_now())
                                orch.latest_layer_summary = future.result(timeout=10)
                            st.rerun()
                        except Exception as _e:
                            st.warning(f"L2/L5/L6 refresh error: {_e}")
            st.markdown("---")
        col_main, col_right = st.columns([2, 1])
        with col_main:
            st.markdown("### Network Topology")
            render_topology(orch.topology, anomalies)
            st.markdown("### Asset Health Metrics")
            render_health_metrics(orch.latest_kpis)
        with col_right:
            render_ai_insights(
                diagnosis,
                bayesian_diagnosis=bayesian_diagnosis,
                causal_graph=st.session_state.get("causal_graph"),
            )
            st.subheader("Active Anomalies")
            if anomalies:
                for a in anomalies:
                    st.warning(f"**{a.asset_id}**: {a.description}")
            else:
                st.success("No active anomalies.")

    with tabs[1]:  # Floor Plan
        st.markdown("## 🏭 Factory Floor Plan - Spatial Health View")
        st.caption("Interactive device positioning with health-based heatmap overlay")
        render_floor_plan(
            assets=orch.assets,
            kpis=orch.latest_kpis,
            anomalies=anomalies,
            floor_plan_path="data/raw/factory_floor_plan.png",
        )

    with tabs[2]:  # Thermal Twin
        st.markdown("## 🌡️ Thermal Network Digital Twin")
        st.caption("Physics-based failure prediction using thermal dynamics")
        render_thermal_view(orch.latest_thermal_predictions, orch.assets)

    with tabs[3]:  # System Performance
        render_validation_metrics()

    with tabs[4]:  # Security
        if st.session_state.intelligence_orchestrator:
            render_security_dashboard(st.session_state.intelligence_orchestrator)
        else:
            st.info(
                "Security monitoring requires Intelligence Orchestrator. "
                "Enable deep learning features to access security dashboard."
            )

    # Collectors tab (only in production mode)
    if st.session_state.data_source_mode == "Production (Live)":
        with tabs[5]:
            if st.session_state.db_manager:
                render_collector_management(st.session_state.db_manager)
            else:
                st.error("Database connection required for collector management")

# ─────────────────────────────────────────────────────────────────────────────
# AI Context + Chat
# ─────────────────────────────────────────────────────────────────────────────
st.session_state.ai_assistant.update_context(
    anomalies=anomalies,
    kpis=orch.latest_kpis,
    topology=orch.topology,
    predictions=orch.latest_predictions,
)
chat_interface = ChatInterface(st.session_state.ai_assistant)
chat_interface.render()