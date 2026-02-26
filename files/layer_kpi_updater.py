"""
layer_kpi_updater.py — Wire L2/L5/L6 Collectors into KPI Engine
================================================================
This module is the integration glue between the three new collectors
and your existing KPI engine / Streamlit dashboard.

It:
  1. Instantiates L2, L5, and L6 collectors from your config
  2. Runs them in parallel on a schedule
  3. Translates their snapshots into the format your existing
     KPI engine and database expect
  4. Exposes a simple LayerHealthSummary for the dashboard

Drop-in integration:
  In your existing pipeline/orchestrator.py, add:
    from src.ingestion.layer_kpi_updater import LayerKPIUpdater
    updater = LayerKPIUpdater(config)
    asyncio.create_task(updater.run())

  In your dashboard app.py, add:
    from src.ingestion.layer_kpi_updater import get_layer_health_summary
    summary = get_layer_health_summary()

File placement:
  Save as: src/ingestion/layer_kpi_updater.py
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Import the new collectors (adjust path if needed)
try:
    from l2_collector import L2Collector, L2CollectorManager, L2KPISnapshot
    from l5_collector import L5Collector, L5KPISnapshot
    from l6_collector import L6Collector, L6KPISnapshot
except ImportError:
    # When running from src/ingestion/ directory
    try:
        from src.ingestion.l2_collector import L2Collector, L2CollectorManager, L2KPISnapshot
        from src.ingestion.l5_collector import L5Collector, L5KPISnapshot
        from src.ingestion.l6_collector import L6Collector, L6KPISnapshot
    except ImportError:
        logger.error(
            "Could not import L2/L5/L6 collectors. "
            "Ensure l2_collector.py, l5_collector.py, l6_collector.py "
            "are in src/ingestion/"
        )
        raise


# ── Configuration Schema ──────────────────────────────────────────────────────

@dataclass
class LayerCollectorConfig:
    """
    Configuration for all three new layer collectors.

    Example usage in your existing config dict:
    -------------------------------------------
    config = LayerCollectorConfig(
        # L2: your Hirschmann switches
        switches=[
            {
                "host": "192.168.1.1",
                "device_id": "hirschmann-sw-floor1",
                "community": "public",
                "expected_vlans": [1, 10, 20, 30],
                "mac_capacity": 8192,
            }
        ],
        # L5: your PLCs and SCADA servers
        opcua_endpoints=[
            "opc.tcp://192.168.1.100:4840",
            "opc.tcp://192.168.1.101:4840",
        ],
        modbus_hosts=["192.168.1.110", "192.168.1.111"],
        opcua_session_baseline={
            "opc.tcp://192.168.1.100:4840": 5,
        },
        # L6: EAGLE router syslog + cert scanning
        syslog_port=5140,
        tls_hosts=[("192.168.1.1", 443), ("192.168.1.2", 8443)],
        log_files=["/var/log/eagle_router.log"],
    )
    """
    # L2
    switches: List[Dict[str, Any]] = field(default_factory=list)
    l2_poll_interval: int = 30

    # L5
    opcua_endpoints: List[str] = field(default_factory=list)
    modbus_hosts: List[str] = field(default_factory=list)
    opcua_username: Optional[str] = None
    opcua_password: Optional[str] = None
    opcua_session_baseline: Optional[Dict[str, int]] = None
    l5_poll_interval: int = 30

    # L6
    syslog_port: int = 5140
    tls_hosts: List = field(default_factory=list)
    log_files: List[str] = field(default_factory=list)
    l6_poll_interval: int = 60


# ── Layer Health Summary (for Dashboard) ─────────────────────────────────────

@dataclass
class LayerHealthSummary:
    """
    Aggregated health for ALL layers L1–L7.
    Your dashboard reads from this object to update the heatmap.
    """
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Scores (0–100) — existing layers come from your KPI engine
    l1_score: float = 100.0   # From your existing thermal/SNMP
    l2_score: float = 100.0   # NEW — from L2Collector
    l3_score: float = 100.0   # From existing SNMP (packet loss, ARP)
    l4_score: float = 100.0   # From existing NetFlow
    l5_score: float = 100.0   # NEW — from L5Collector
    l6_score: float = 100.0   # NEW — from L6Collector
    l7_score: float = 100.0   # From existing app probes

    # Anomalies per layer
    l2_anomalies: List[str] = field(default_factory=list)
    l5_anomalies: List[str] = field(default_factory=list)
    l6_anomalies: List[str] = field(default_factory=list)

    # Raw snapshots (access for detailed views)
    l2_snapshots: List[Any] = field(default_factory=list)   # List[L2KPISnapshot]
    l5_snapshot: Optional[Any] = None                         # L5KPISnapshot
    l6_snapshot: Optional[Any] = None                         # L6KPISnapshot

    # Composite ONE score (same weights as your PDF slide)
    one_score: float = 100.0

    def compute_one_score(self) -> "LayerHealthSummary":
        """
        Compute the weighted ONE score across all 7 layers.
        Weights match your presentation slide:
          L1: 20%  L2: 15%  L3: 20%  L4: 20%  L5: 10%  L6: 10%  L7: 5%
        """
        self.one_score = round(
            self.l1_score * 0.20
            + self.l2_score * 0.15
            + self.l3_score * 0.20
            + self.l4_score * 0.20
            + self.l5_score * 0.10
            + self.l6_score * 0.10
            + self.l7_score * 0.05,
            1,
        )
        return self

    def get_critical_layers(self) -> List[str]:
        """Returns list of layer names with score < 50."""
        critical = []
        for layer, score in [
            ("L1", self.l1_score), ("L2", self.l2_score),
            ("L3", self.l3_score), ("L4", self.l4_score),
            ("L5", self.l5_score), ("L6", self.l6_score),
            ("L7", self.l7_score),
        ]:
            if score < 50:
                critical.append(layer)
        return critical

    def get_all_anomalies(self) -> List[str]:
        """All anomalies across L2, L5, L6 in one list."""
        return self.l2_anomalies + self.l5_anomalies + self.l6_anomalies

    def to_dict(self) -> Dict:
        """Serialise for JSON/database storage."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "scores": {
                "L1": self.l1_score, "L2": self.l2_score, "L3": self.l3_score,
                "L4": self.l4_score, "L5": self.l5_score, "L6": self.l6_score,
                "L7": self.l7_score,
            },
            "one_score": self.one_score,
            "anomalies": {
                "L2": self.l2_anomalies,
                "L5": self.l5_anomalies,
                "L6": self.l6_anomalies,
            },
            "critical_layers": self.get_critical_layers(),
        }


# ── Main Updater ──────────────────────────────────────────────────────────────

class LayerKPIUpdater:
    """
    Orchestrates L2, L5, and L6 collectors and maintains a
    LayerHealthSummary that the dashboard can read at any time.

    Integration Pattern
    -------------------
    # In your orchestrator.py __init__:
    self.layer_updater = LayerKPIUpdater(config)

    # In your orchestrator.py run() method:
    asyncio.create_task(self.layer_updater.run())

    # To get current health in dashboard:
    summary = self.layer_updater.get_current_summary()
    """

    def __init__(self, config: Optional[LayerCollectorConfig] = None):
        self.config = config or LayerCollectorConfig()
        self._current_summary = LayerHealthSummary()
        self._last_update: Optional[datetime] = None

        # Initialise collectors
        self._l2_manager = self._init_l2()
        self._l5_collector = self._init_l5()
        self._l6_collector = self._init_l6()

        # External score injection (for L1/L3/L4/L7 from existing KPI engine)
        self._external_scores: Dict[str, float] = {}

    def _init_l2(self) -> L2CollectorManager:
        manager = L2CollectorManager()
        for sw in self.config.switches:
            manager.add_switch(
                host=sw["host"],
                device_id=sw.get("device_id", sw["host"]),
                community=sw.get("community", "public"),
                expected_vlans=sw.get("expected_vlans"),
                mac_table_capacity=sw.get("mac_capacity", 8192),
            )
        if not self.config.switches:
            # Default: add a simulated switch for demo
            manager.add_switch(
                host="192.168.1.1",
                device_id="demo-switch-01",
                expected_vlans=[1, 10, 20],
            )
            logger.info("L2: No switches configured — using demo switch.")
        return manager

    def _init_l5(self) -> L5Collector:
        return L5Collector(
            opcua_endpoints=self.config.opcua_endpoints,
            modbus_hosts=self.config.modbus_hosts,
            opcua_username=self.config.opcua_username,
            opcua_password=self.config.opcua_password,
            session_baseline=self.config.opcua_session_baseline,
            poll_interval_sec=self.config.l5_poll_interval,
        )

    def _init_l6(self) -> L6Collector:
        return L6Collector(
            syslog_port=self.config.syslog_port,
            tls_hosts=self.config.tls_hosts,
            log_files=self.config.log_files,
            poll_interval_sec=self.config.l6_poll_interval,
        )

    def inject_scores(self, l1: float = None, l3: float = None,
                      l4: float = None, l7: float = None):
        """
        Inject L1/L3/L4/L7 scores from your existing KPI engine.

        Call this from your existing KPI calculation code:
            updater.inject_scores(l1=kpi.l1_score, l3=kpi.l3_score, ...)
        """
        if l1 is not None:
            self._external_scores["l1"] = l1
        if l3 is not None:
            self._external_scores["l3"] = l3
        if l4 is not None:
            self._external_scores["l4"] = l4
        if l7 is not None:
            self._external_scores["l7"] = l7

    def get_current_summary(self) -> LayerHealthSummary:
        """Return the most recent LayerHealthSummary (thread-safe read)."""
        return self._current_summary

    async def _collect_once(self) -> LayerHealthSummary:
        """Run one full collection cycle across L2, L5, L6."""
        # Start L6 syslog listener on first call
        if not self._l6_collector._syslog_running and \
                not self._l6_collector._simulation_mode:
            asyncio.create_task(self._l6_collector.start_syslog_listener())

        # Collect L2, L5, L6 concurrently
        l2_snaps, l5_snap, l6_snap = await asyncio.gather(
            self._l2_manager.collect_all(),
            self._l5_collector.collect_all(),
            self._l6_collector.collect_all(),
            return_exceptions=True,
        )

        summary = LayerHealthSummary(timestamp=datetime.utcnow())

        # ── L2 ─────────────────────────────────────────────────────────────
        if isinstance(l2_snaps, list):
            summary.l2_snapshots = l2_snaps
            if l2_snaps:
                avg_l2 = sum(s.health_score for s in l2_snaps) / len(l2_snaps)
                summary.l2_score = round(avg_l2, 1)
                summary.l2_anomalies = [
                    a for s in l2_snaps for a in s.anomalies
                ]
        else:
            logger.error(f"L2 collection error: {l2_snaps}")

        # ── L5 ─────────────────────────────────────────────────────────────
        if isinstance(l5_snap, L5KPISnapshot):
            summary.l5_snapshot = l5_snap
            summary.l5_score = l5_snap.health_score
            summary.l5_anomalies = l5_snap.anomalies
        else:
            logger.error(f"L5 collection error: {l5_snap}")

        # ── L6 ─────────────────────────────────────────────────────────────
        if isinstance(l6_snap, L6KPISnapshot):
            summary.l6_snapshot = l6_snap
            summary.l6_score = l6_snap.health_score
            summary.l6_anomalies = l6_snap.anomalies
        else:
            logger.error(f"L6 collection error: {l6_snap}")

        # ── Inject external scores (L1/L3/L4/L7) ──────────────────────────
        summary.l1_score = self._external_scores.get("l1", self._current_summary.l1_score)
        summary.l3_score = self._external_scores.get("l3", self._current_summary.l3_score)
        summary.l4_score = self._external_scores.get("l4", self._current_summary.l4_score)
        summary.l7_score = self._external_scores.get("l7", self._current_summary.l7_score)

        summary.compute_one_score()
        return summary

    async def run(self, poll_interval: int = 30):
        """
        Main collection loop. Run as an asyncio task.

        Parameters
        ----------
        poll_interval : int
            Seconds between full L2+L5+L6 collection cycles.
        """
        logger.info("LayerKPIUpdater starting. Polling L2 + L5 + L6 layers.")
        while True:
            try:
                self._current_summary = await self._collect_once()
                self._last_update = datetime.utcnow()

                s = self._current_summary
                logger.info(
                    f"[LayerUpdate] ONE={s.one_score} | "
                    f"L2={s.l2_score} L5={s.l5_score} L6={s.l6_score} | "
                    f"Critical layers: {s.get_critical_layers()}"
                )
            except Exception as e:
                logger.error(f"LayerKPIUpdater error: {e}", exc_info=True)

            await asyncio.sleep(poll_interval)

    async def collect_once_now(self) -> LayerHealthSummary:
        """
        Trigger an immediate single collection.
        Useful for Streamlit's on-demand refresh button.
        """
        self._current_summary = await self._collect_once()
        return self._current_summary


# ── Dashboard Integration Helper ──────────────────────────────────────────────

# Global singleton — set by your orchestrator on startup
_global_updater: Optional[LayerKPIUpdater] = None


def init_layer_updater(config: Optional[LayerCollectorConfig] = None) -> LayerKPIUpdater:
    """
    Initialise the global LayerKPIUpdater.
    Call once from your app startup or orchestrator __init__.
    """
    global _global_updater
    _global_updater = LayerKPIUpdater(config)
    return _global_updater


def get_layer_health_summary() -> LayerHealthSummary:
    """
    Get the current layer health summary for the dashboard.
    Returns a default healthy summary if updater not yet initialised.
    """
    if _global_updater is None:
        logger.warning("LayerKPIUpdater not initialised. Returning default summary.")
        return LayerHealthSummary()
    return _global_updater.get_current_summary()


# ── Streamlit Dashboard Component ─────────────────────────────────────────────

def render_layer_heatmap(summary: LayerHealthSummary):
    """
    Render the L1–L7 health heatmap in Streamlit.
    Shows all 7 OSI layers with color-coded health scores.
    """
    try:
        import streamlit as st
    except ImportError:
        print("Streamlit not available — heatmap skipped.")
        return

    st.subheader("🌡️ L1–L7 Health Heatmap (Live)")

    cols = st.columns(7)
    layer_data = [
        ("L1\nPhysical",      summary.l1_score, "Cable / SFP / EMI / BER"),
        ("L2\nData Link",     summary.l2_score, "VLAN / STP / MAC overflow"),
        ("L3\nNetwork",       summary.l3_score, "Routing / ARP / Packet loss"),
        ("L4\nTransport",     summary.l4_score, "TCP retransmits / UDP congestion"),
        ("L5\nSession",       summary.l5_score, "OPC UA keepalive / Modbus sessions"),
        ("L6\nPresentation",  summary.l6_score, "TLS handshake / Certificate / Encoding"),
        ("L7\nApplication",   summary.l7_score, "SCADA / ERP response time"),
    ]

    for col, (label, score, tooltip) in zip(cols, layer_data):
        with col:
            if score >= 75:
                icon  = "✅"
                delta = "HEALTHY"
            elif score >= 50:
                icon  = "⚠️"
                delta = "WARNING"
            else:
                icon  = "🚨"
                delta = "CRITICAL"

            # st.metric shows the label, value, and delta
            st.metric(
                label=label.replace("\n", " "),
                value=f"{score:.0f}%",
                delta=f"{icon} {delta}",
                help=tooltip,
            )

    # ONE Score bar
    st.markdown("---")
    one = summary.one_score
    if one >= 75:
        one_color, one_icon = "green",  "✅ Healthy"
    elif one >= 50:
        one_color, one_icon = "orange", "⚠️ Warning"
    else:
        one_color, one_icon = "red",    "🚨 Critical"

    col_score, col_layers = st.columns([1, 3])
    with col_score:
        st.markdown(
            f"**ONE Score**  \n"
            f"<span style='color:{one_color};font-size:28px;font-weight:bold'>{one:.1f}%</span>  \n"
            f"{one_icon}",
            unsafe_allow_html=True,
        )
    with col_layers:
        critical = summary.get_critical_layers()
        if critical:
            st.error(f"🚨 **Critical layers:** {', '.join(critical)} — immediate action required")
        all_anomalies = summary.get_all_anomalies()
        if all_anomalies:
            with st.expander(f"⚠️ {len(all_anomalies)} Layer Anomalies (L2 / L5 / L6)"):
                for a in all_anomalies:
                    icon = "🔴" if "CRITICAL" in a.upper() else "🟡"
                    st.write(f"{icon} {a}")


# ── CLI / Quick Test ──────────────────────────────────────────────────────────

async def _demo():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = LayerCollectorConfig(
        switches=[
            {
                "host": "192.168.1.1",
                "device_id": "hirschmann-floor1",
                "expected_vlans": [1, 10, 20],
            }
        ],
        opcua_endpoints=["opc.tcp://192.168.1.100:4840"],
        modbus_hosts=["192.168.1.110", "192.168.1.111"],
        tls_hosts=[("google.com", 443)],
    )

    updater = LayerKPIUpdater(config)

    # Inject example L1/L3/L4/L7 scores (normally from your KPI engine)
    updater.inject_scores(l1=85.0, l3=92.0, l4=88.0, l7=95.0)

    print("\n=== LayerKPIUpdater Demo (Single Collection) ===")
    summary = await updater.collect_once_now()

    print(f"\nONE Score : {summary.one_score}/100")
    print(f"Timestamp : {summary.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    layer_names = ["L1 Physical", "L2 DataLink", "L3 Network",
                   "L4 Transport", "L5 Session", "L6 Presentation", "L7 Application"]
    scores = [
        summary.l1_score, summary.l2_score, summary.l3_score,
        summary.l4_score, summary.l5_score, summary.l6_score, summary.l7_score,
    ]

    for name, score in zip(layer_names, scores):
        bar_len = int(score / 5)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        status = "✅" if score >= 75 else "⚠️" if score >= 50 else "🚨"
        print(f"  {name:20s} [{bar}] {score:5.1f}% {status}")

    critical = summary.get_critical_layers()
    if critical:
        print(f"\n🚨 CRITICAL LAYERS: {', '.join(critical)}")

    all_anomalies = summary.get_all_anomalies()
    if all_anomalies:
        print(f"\n⚠ {len(all_anomalies)} Anomalies:")
        for a in all_anomalies:
            print(f"  {a}")
    else:
        print("\n✅ No anomalies detected.")

    print("\n--- JSON Output (for database/API) ---")
    import json
    print(json.dumps(summary.to_dict(), indent=2))


if __name__ == "__main__":
    asyncio.run(_demo())