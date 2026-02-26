"""
l2_collector.py — Layer 2 Data Link KPI Collector
==================================================
Monitors L2 health via SNMP MIB polling:
  - VLAN mismatch detection  (dot1qVlanTable)
  - MAC table overflow        (dot1dTpFdbTable entry count vs capacity)
  - STP loop / topology change detection (dot1dStpTable)
  - Broadcast storm proxy     (ifInBroadcastPkts rate)

Integrates with your existing snmp_collector.py pattern:
  - Async polling via asyncio
  - Returns L2KPISnapshot dataclass ready for KPI engine ingestion
  - Each method can be called independently or via collect_all()

OID Reference:
  dot1dStpTimeSinceTopologyChange  : 1.3.6.1.2.1.17.2.1
  dot1dStpTopChanges               : 1.3.6.1.2.1.17.2.4
  dot1dTpFdbTable entries          : 1.3.6.1.2.1.17.4.3   (walk)
  dot1qVlanCurrentTable            : 1.3.6.1.2.1.17.7.1.4.2 (walk)
  ifInBroadcastPkts                : 1.3.6.1.2.1.31.1.1.1.9
  ifOutBroadcastPkts               : 1.3.6.1.2.1.31.1.1.1.13

Usage:
    collector = L2Collector(host="192.168.1.1", community="public")
    snapshot = await collector.collect_all()
    print(snapshot.health_score)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── KPI Thresholds (tunable per deployment) ──────────────────────────────────
THRESHOLDS = {
    # STP: if topology changed within last N seconds → warning/critical
    "stp_change_warning_sec": 300,    # 5 minutes
    "stp_change_critical_sec": 60,    # 1 minute  → active loop likely
    "stp_total_changes_warning": 5,   # >5 topo changes in window → unstable
    # MAC table: % of capacity used
    "mac_table_warning_pct": 70,
    "mac_table_critical_pct": 90,
    # Broadcast: packets/sec rate
    "broadcast_rate_warning": 1000,
    "broadcast_rate_critical": 5000,
    # VLAN: number of mismatched/unrecognized VLAN IDs vs expected set
    "vlan_mismatch_warning": 1,
    "vlan_mismatch_critical": 3,
}

# Typical Hirschmann RS20/RS30 MAC table capacity
DEFAULT_MAC_TABLE_CAPACITY = 8192


# ── Data Structures ───────────────────────────────────────────────────────────

@dataclass
class STPStatus:
    """Spanning Tree Protocol health snapshot."""
    time_since_last_change_sec: int = -1   # -1 = unknown
    total_topology_changes: int = 0
    root_bridge_id: str = "unknown"
    port_states: Dict[int, str] = field(default_factory=dict)  # port → state
    is_loop_suspected: bool = False
    severity: str = "healthy"              # healthy | warning | critical
    detail: str = ""


@dataclass
class MACTableStatus:
    """MAC address table health snapshot."""
    learned_entries: int = 0
    capacity: int = DEFAULT_MAC_TABLE_CAPACITY
    utilization_pct: float = 0.0
    flapping_macs: List[str] = field(default_factory=list)  # MACs moving ports
    severity: str = "healthy"
    detail: str = ""


@dataclass
class BroadcastStatus:
    """Broadcast storm proxy metrics."""
    broadcast_pps_per_port: Dict[int, float] = field(default_factory=dict)
    peak_broadcast_pps: float = 0.0
    storm_detected: bool = False
    severity: str = "healthy"
    detail: str = ""


@dataclass
class VLANStatus:
    """VLAN consistency health snapshot."""
    active_vlan_ids: List[int] = field(default_factory=list)
    expected_vlan_ids: List[int] = field(default_factory=list)
    missing_vlans: List[int] = field(default_factory=list)   # expected but absent
    unexpected_vlans: List[int] = field(default_factory=list) # present but not expected
    mismatch_count: int = 0
    severity: str = "healthy"
    detail: str = ""


@dataclass
class L2KPISnapshot:
    """
    Complete L2 health snapshot for one device at one point in time.
    Passed to KPIEngine.ingest_l2(snapshot) for scoring.
    """
    device_ip: str
    device_id: str
    timestamp: datetime

    stp: STPStatus = field(default_factory=STPStatus)
    mac_table: MACTableStatus = field(default_factory=MACTableStatus)
    broadcast: BroadcastStatus = field(default_factory=BroadcastStatus)
    vlan: VLANStatus = field(default_factory=VLANStatus)

    # Composite L2 health score 0–100 (computed by score())
    health_score: float = 100.0
    overall_severity: str = "healthy"
    anomalies: List[str] = field(default_factory=list)

    def score(self) -> "L2KPISnapshot":
        """
        Compute weighted composite L2 health score.

        Weights (sum = 1.0):
          STP loop risk   : 0.40  (highest — loop = total outage)
          MAC table        : 0.25
          Broadcast storm  : 0.25
          VLAN mismatch    : 0.10
        """
        severity_score = {"healthy": 100, "warning": 60, "critical": 20}

        weighted = (
            severity_score[self.stp.severity] * 0.40
            + severity_score[self.mac_table.severity] * 0.25
            + severity_score[self.broadcast.severity] * 0.25
            + severity_score[self.vlan.severity] * 0.10
        )
        self.health_score = round(weighted, 1)

        # Derive overall severity
        severities = [
            self.stp.severity,
            self.mac_table.severity,
            self.broadcast.severity,
            self.vlan.severity,
        ]
        if "critical" in severities:
            self.overall_severity = "critical"
        elif "warning" in severities:
            self.overall_severity = "warning"
        else:
            self.overall_severity = "healthy"

        # Collect human-readable anomaly descriptions
        self.anomalies = []
        if self.stp.severity != "healthy":
            self.anomalies.append(f"[L2-STP] {self.stp.detail}")
        if self.mac_table.severity != "healthy":
            self.anomalies.append(f"[L2-MAC] {self.mac_table.detail}")
        if self.broadcast.severity != "healthy":
            self.anomalies.append(f"[L2-BCast] {self.broadcast.detail}")
        if self.vlan.severity != "healthy":
            self.anomalies.append(f"[L2-VLAN] {self.vlan.detail}")

        return self


# ── Main Collector ────────────────────────────────────────────────────────────

class L2Collector:
    """
    Async L2 KPI collector for a single managed switch.

    Parameters
    ----------
    host : str
        IP address of the switch (Hirschmann, Cisco, etc.)
    community : str
        SNMP v2c community string (use v3 in production — see snmp_collector.py)
    expected_vlans : list[int]
        VLAN IDs that SHOULD be present on this switch (from your network config)
    mac_table_capacity : int
        Maximum MAC entries the switch supports (check datasheet)
    poll_interval_sec : int
        How often to poll (seconds). 30s recommended for factory networks.
    """

    def __init__(
        self,
        host: str,
        community: str = "public",
        expected_vlans: Optional[List[int]] = None,
        mac_table_capacity: int = DEFAULT_MAC_TABLE_CAPACITY,
        poll_interval_sec: int = 30,
    ):
        self.host = host
        self.community = community
        self.expected_vlans = expected_vlans or [1, 10, 20]  # default OT VLANs
        self.mac_table_capacity = mac_table_capacity
        self.poll_interval_sec = poll_interval_sec

        # For broadcast storm detection: stores previous counter values
        self._prev_broadcast_counters: Dict[int, Tuple[float, float]] = {}
        # For MAC flap detection: stores mac → (port, last_seen_time)
        self._mac_port_history: Dict[str, Tuple[int, float]] = {}

        self._snmp_available = self._check_pysnmp()

    def _check_pysnmp(self) -> bool:
        try:
            from pysnmp.hlapi.asyncio import getCmd, bulkCmd, SnmpEngine
            return True
        except ImportError:
            logger.warning(
                "pysnmp not installed. Running in SIMULATION mode. "
                "Install with: pip install pysnmp"
            )
            return False

    # ── SNMP Helpers ─────────────────────────────────────────────────────────

    async def _snmp_get(self, oid: str) -> Optional[str]:
        """Single OID GET. Returns string value or None on failure."""
        if not self._snmp_available:
            return None
        try:
            from pysnmp.hlapi.asyncio import (
                getCmd, SnmpEngine, CommunityData, UdpTransportTarget,
                ContextData, ObjectType, ObjectIdentity,
            )
            engine = SnmpEngine()
            result = await getCmd(
                engine,
                CommunityData(self.community),
                UdpTransportTarget((self.host, 161), timeout=2, retries=1),
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
            )
            error_indication, error_status, _, var_binds = result
            if error_indication or error_status:
                return None
            return str(var_binds[0][1])
        except Exception as e:
            logger.debug(f"SNMP GET {oid} failed: {e}")
            return None

    async def _snmp_walk(self, oid: str) -> List[Tuple[str, str]]:
        """SNMP WALK. Returns list of (oid_suffix, value) tuples."""
        if not self._snmp_available:
            return []
        try:
            from pysnmp.hlapi.asyncio import (
                bulkCmd, SnmpEngine, CommunityData, UdpTransportTarget,
                ContextData, ObjectType, ObjectIdentity,
            )
            results = []
            engine = SnmpEngine()
            async for (err_ind, err_stat, _, var_binds) in bulkCmd(
                engine,
                CommunityData(self.community),
                UdpTransportTarget((self.host, 161), timeout=3, retries=1),
                ContextData(),
                0, 50,  # non-repeaters=0, max-repetitions=50
                ObjectType(ObjectIdentity(oid)),
                lexicographicMode=False,
            ):
                if err_ind or err_stat:
                    break
                for var_bind in var_binds:
                    results.append((str(var_bind[0]), str(var_bind[1])))
            return results
        except Exception as e:
            logger.debug(f"SNMP WALK {oid} failed: {e}")
            return []

    # ── STP Collection ────────────────────────────────────────────────────────

    async def collect_stp(self) -> STPStatus:
        """
        Poll STP MIBs and assess loop risk.

        Key OIDs:
          1.3.6.1.2.1.17.2.1  dot1dStpTimeSinceTopologyChange (centiseconds)
          1.3.6.1.2.1.17.2.4  dot1dStpTopChanges (cumulative counter)
          1.3.6.1.2.1.17.2.7  dot1dStpRootCost
        """
        status = STPStatus()

        if not self._snmp_available:
            return self._simulate_stp()

        # Time since last topology change
        raw_time = await self._snmp_get("1.3.6.1.2.1.17.2.1.0")
        if raw_time:
            try:
                # Value is in centiseconds
                status.time_since_last_change_sec = int(raw_time) // 100
            except ValueError:
                pass

        # Total topology changes
        raw_changes = await self._snmp_get("1.3.6.1.2.1.17.2.4.0")
        if raw_changes:
            try:
                status.total_topology_changes = int(raw_changes)
            except ValueError:
                pass

        # Port states via dot1dStpPortTable (1.3.6.1.2.1.17.2.15.1.3)
        # STP Port State: 1=disabled 2=blocking 3=listening 4=learning 5=forwarding 6=broken
        stp_state_map = {
            "1": "disabled", "2": "blocking", "3": "listening",
            "4": "learning", "5": "forwarding", "6": "broken",
        }
        port_state_rows = await self._snmp_walk("1.3.6.1.2.1.17.2.15.1.3")
        for oid_str, val in port_state_rows:
            try:
                port_num = int(oid_str.split(".")[-1])
                status.port_states[port_num] = stp_state_map.get(val, f"unknown({val})")
            except (ValueError, IndexError):
                pass

        # Evaluate severity
        t = status.time_since_last_change_sec
        if t != -1 and t < THRESHOLDS["stp_change_critical_sec"]:
            status.is_loop_suspected = True
            status.severity = "critical"
            status.detail = (
                f"STP topology changed {t}s ago — LOOP LIKELY. "
                f"Total changes: {status.total_topology_changes}. "
                "ACTION: Check for duplex mismatch or rogue switch."
            )
        elif (t != -1 and t < THRESHOLDS["stp_change_warning_sec"]) or \
             status.total_topology_changes > THRESHOLDS["stp_total_changes_warning"]:
            status.severity = "warning"
            status.detail = (
                f"STP topology unstable — last change {t}s ago, "
                f"{status.total_topology_changes} total changes. Monitor closely."
            )
        else:
            status.severity = "healthy"
            status.detail = (
                f"STP stable. Last change {t}s ago, "
                f"{status.total_topology_changes} total changes."
            )

        return status

    def _simulate_stp(self) -> STPStatus:
        """Returns realistic simulated STP data when pysnmp unavailable."""
        import random
        t = random.choice([3600, 7200, 45, 15])  # mostly healthy, occasional issues
        s = STPStatus(
            time_since_last_change_sec=t,
            total_topology_changes=random.randint(0, 8),
            port_states={1: "forwarding", 2: "forwarding", 3: "blocking", 4: "forwarding"},
        )
        if t < 60:
            s.severity = "critical"
            s.is_loop_suspected = True
            s.detail = f"[SIM] STP topology changed {t}s ago — loop suspected."
        elif t < 300:
            s.severity = "warning"
            s.detail = f"[SIM] STP topology changed {t}s ago."
        else:
            s.severity = "healthy"
            s.detail = f"[SIM] STP stable. Last change {t}s ago."
        return s

    # ── MAC Table Collection ──────────────────────────────────────────────────

    async def collect_mac_table(self) -> MACTableStatus:
        """
        Count MAC table entries and detect flapping MACs.

        dot1dTpFdbTable: 1.3.6.1.2.1.17.4.3
          .1.1 = MAC address
          .1.2 = port number
          .1.3 = status (1=other 2=invalid 3=learned 4=self 5=mgmt)
        """
        status = MACTableStatus(capacity=self.mac_table_capacity)

        if not self._snmp_available:
            return self._simulate_mac_table()

        # Walk the FDB table: OID .1.2 = port index
        fdb_port_rows = await self._snmp_walk("1.3.6.1.2.1.17.4.3.1.2")
        # Walk status to filter only "learned" entries
        fdb_status_rows = await self._snmp_walk("1.3.6.1.2.1.17.4.3.1.3")

        status_dict = {oid: val for oid, val in fdb_status_rows}
        now = time.time()
        learned_count = 0
        current_mac_ports: Dict[str, int] = {}

        for oid_str, port_val in fdb_port_rows:
            # Derive matching status OID
            mac_key = oid_str.replace("1.3.6.1.2.1.17.4.3.1.2", "1.3.6.1.2.1.17.4.3.1.3")
            entry_status = status_dict.get(mac_key, "3")

            if entry_status == "3":  # learned
                learned_count += 1
                # Extract MAC from OID suffix (6 octets)
                try:
                    octets = oid_str.split(".")[-6:]
                    mac = ":".join(f"{int(o):02x}" for o in octets)
                    port = int(port_val)
                    current_mac_ports[mac] = port

                    # Flap detection: same MAC seen on different port
                    if mac in self._mac_port_history:
                        prev_port, _ = self._mac_port_history[mac]
                        if prev_port != port:
                            status.flapping_macs.append(mac)
                    self._mac_port_history[mac] = (port, now)
                except (ValueError, IndexError):
                    learned_count += 1  # still count even if MAC parse fails

        status.learned_entries = learned_count
        status.utilization_pct = round(
            (learned_count / self.mac_table_capacity) * 100, 1
        )

        if status.utilization_pct >= THRESHOLDS["mac_table_critical_pct"] or \
                len(status.flapping_macs) >= 3:
            status.severity = "critical"
            status.detail = (
                f"MAC table {status.utilization_pct}% full "
                f"({learned_count}/{self.mac_table_capacity}). "
                f"Flapping MACs: {status.flapping_macs[:3]}. "
                "Risk: new devices will be flooded (broadcast storm)."
            )
        elif status.utilization_pct >= THRESHOLDS["mac_table_warning_pct"] or \
                len(status.flapping_macs) >= 1:
            status.severity = "warning"
            status.detail = (
                f"MAC table {status.utilization_pct}% full. "
                f"{len(status.flapping_macs)} flapping MAC(s) detected."
            )
        else:
            status.severity = "healthy"
            status.detail = (
                f"MAC table healthy: {learned_count}/{self.mac_table_capacity} entries "
                f"({status.utilization_pct}%)."
            )

        return status

    def _simulate_mac_table(self) -> MACTableStatus:
        import random
        entries = random.randint(100, 9000)
        pct = round((entries / DEFAULT_MAC_TABLE_CAPACITY) * 100, 1)
        s = MACTableStatus(
            learned_entries=entries,
            capacity=DEFAULT_MAC_TABLE_CAPACITY,
            utilization_pct=pct,
        )
        if pct >= 90:
            s.severity = "critical"
            s.detail = f"[SIM] MAC table {pct}% full — overflow imminent."
        elif pct >= 70:
            s.severity = "warning"
            s.detail = f"[SIM] MAC table {pct}% full."
        else:
            s.severity = "healthy"
            s.detail = f"[SIM] MAC table {pct}% ({entries} entries)."
        return s

    # ── Broadcast Collection ──────────────────────────────────────────────────

    async def collect_broadcast(self) -> BroadcastStatus:
        """
        Measure broadcast packets-per-second per port.

        ifInBroadcastPkts  : 1.3.6.1.2.1.31.1.1.1.9
        """
        status = BroadcastStatus()

        if not self._snmp_available:
            return self._simulate_broadcast()

        now = time.time()
        rows = await self._snmp_walk("1.3.6.1.2.1.31.1.1.1.9")

        for oid_str, val in rows:
            try:
                if_index = int(oid_str.split(".")[-1])
                counter = int(val)
                if if_index in self._prev_broadcast_counters:
                    prev_counter, prev_time = self._prev_broadcast_counters[if_index]
                    dt = now - prev_time
                    if dt > 0:
                        pps = (counter - prev_counter) / dt
                        status.broadcast_pps_per_port[if_index] = round(pps, 1)
                self._prev_broadcast_counters[if_index] = (counter, now)
            except (ValueError, IndexError):
                pass

        if status.broadcast_pps_per_port:
            status.peak_broadcast_pps = max(status.broadcast_pps_per_port.values())

        if status.peak_broadcast_pps >= THRESHOLDS["broadcast_rate_critical"]:
            status.storm_detected = True
            status.severity = "critical"
            worst_port = max(
                status.broadcast_pps_per_port,
                key=status.broadcast_pps_per_port.get,
            )
            status.detail = (
                f"BROADCAST STORM on port {worst_port}: "
                f"{status.peak_broadcast_pps:.0f} pps. "
                "ACTION: Enable storm control, check for loop or NIC failure."
            )
        elif status.peak_broadcast_pps >= THRESHOLDS["broadcast_rate_warning"]:
            status.severity = "warning"
            status.detail = (
                f"High broadcast rate: {status.peak_broadcast_pps:.0f} pps. "
                "Monitor for escalation."
            )
        else:
            status.severity = "healthy"
            status.detail = (
                f"Broadcast rate normal: {status.peak_broadcast_pps:.0f} pps peak."
            )

        return status

    def _simulate_broadcast(self) -> BroadcastStatus:
        import random
        pps = random.choice([50, 200, 1200, 6000])
        s = BroadcastStatus(
            broadcast_pps_per_port={1: pps, 2: pps * 0.3},
            peak_broadcast_pps=pps,
            storm_detected=pps >= 5000,
        )
        if pps >= 5000:
            s.severity = "critical"
            s.detail = f"[SIM] Broadcast storm: {pps} pps."
        elif pps >= 1000:
            s.severity = "warning"
            s.detail = f"[SIM] High broadcast: {pps} pps."
        else:
            s.severity = "healthy"
            s.detail = f"[SIM] Broadcast normal: {pps} pps."
        return s

    # ── VLAN Collection ───────────────────────────────────────────────────────

    async def collect_vlans(self) -> VLANStatus:
        """
        Read active VLANs and compare against expected set.

        dot1qVlanCurrentTable: 1.3.6.1.2.1.17.7.1.4.2
          The last OID component encodes the VLAN ID.
        """
        status = VLANStatus(expected_vlan_ids=list(self.expected_vlans))

        if not self._snmp_available:
            return self._simulate_vlans()

        rows = await self._snmp_walk("1.3.6.1.2.1.17.7.1.4.2.1.3")  # dot1qVlanFdbId
        seen_vlans = set()
        for oid_str, _ in rows:
            try:
                # VLAN ID is the second-to-last component in the OID
                parts = oid_str.split(".")
                vlan_id = int(parts[-2])  # TimeFilter, vlanIndex
                if 1 <= vlan_id <= 4094:
                    seen_vlans.add(vlan_id)
            except (ValueError, IndexError):
                pass

        # Fallback: try simpler OID walk if above returns nothing
        if not seen_vlans:
            rows2 = await self._snmp_walk("1.3.6.1.2.1.17.7.1.4.2.1.4")
            for oid_str, _ in rows2:
                try:
                    vlan_id = int(oid_str.split(".")[-1])
                    if 1 <= vlan_id <= 4094:
                        seen_vlans.add(vlan_id)
                except (ValueError, IndexError):
                    pass

        status.active_vlan_ids = sorted(seen_vlans)
        expected_set = set(self.expected_vlans)

        status.missing_vlans = sorted(expected_set - seen_vlans)
        status.unexpected_vlans = sorted(seen_vlans - expected_set - {1})  # VLAN1 always present
        status.mismatch_count = len(status.missing_vlans) + len(status.unexpected_vlans)

        if status.mismatch_count >= THRESHOLDS["vlan_mismatch_critical"]:
            status.severity = "critical"
            status.detail = (
                f"VLAN mismatch: missing={status.missing_vlans}, "
                f"unexpected={status.unexpected_vlans}. "
                "ACTION: Check trunk port config — PLCs may be unreachable."
            )
        elif status.mismatch_count >= THRESHOLDS["vlan_mismatch_warning"]:
            status.severity = "warning"
            status.detail = (
                f"VLAN inconsistency: missing={status.missing_vlans}, "
                f"unexpected={status.unexpected_vlans}."
            )
        else:
            status.severity = "healthy"
            status.detail = (
                f"VLANs consistent. Active: {status.active_vlan_ids}"
            )

        return status

    def _simulate_vlans(self) -> VLANStatus:
        import random
        active = list(self.expected_vlans)
        if random.random() < 0.2:
            active = active[:-1]  # simulate missing VLAN
        if random.random() < 0.1:
            active.append(999)    # simulate rogue VLAN
        s = VLANStatus(
            active_vlan_ids=sorted(active),
            expected_vlan_ids=list(self.expected_vlans),
            missing_vlans=[v for v in self.expected_vlans if v not in active],
            unexpected_vlans=[v for v in active if v not in self.expected_vlans],
        )
        s.mismatch_count = len(s.missing_vlans) + len(s.unexpected_vlans)
        if s.mismatch_count >= 3:
            s.severity = "critical"
            s.detail = f"[SIM] VLAN mismatch: missing={s.missing_vlans}"
        elif s.mismatch_count >= 1:
            s.severity = "warning"
            s.detail = f"[SIM] VLAN inconsistency: missing={s.missing_vlans}"
        else:
            s.severity = "healthy"
            s.detail = f"[SIM] VLANs OK: {s.active_vlan_ids}"
        return s

    # ── Master Collect ────────────────────────────────────────────────────────

    async def collect_all(self, device_id: Optional[str] = None) -> L2KPISnapshot:
        """
        Run all L2 collectors in parallel and return a scored snapshot.

        Parameters
        ----------
        device_id : str, optional
            Asset ID from your database (Asset.id). Defaults to host IP.
        """
        stp, mac, bcast, vlan = await asyncio.gather(
            self.collect_stp(),
            self.collect_mac_table(),
            self.collect_broadcast(),
            self.collect_vlans(),
        )

        snapshot = L2KPISnapshot(
            device_ip=self.host,
            device_id=device_id or self.host,
            timestamp=datetime.utcnow(),
            stp=stp,
            mac_table=mac,
            broadcast=bcast,
            vlan=vlan,
        )
        return snapshot.score()

    async def run_continuous(
        self,
        device_id: Optional[str] = None,
        callback=None,
    ):
        """
        Poll continuously at self.poll_interval_sec.

        Parameters
        ----------
        callback : coroutine function, optional
            async def callback(snapshot: L2KPISnapshot) — called after each poll.
            Use this to push data into your KPI engine / database.

        Example
        -------
        async def on_snapshot(snap):
            await kpi_engine.ingest_l2(snap)

        collector = L2Collector("192.168.1.1", expected_vlans=[1, 10, 20, 30])
        await collector.run_continuous(device_id="hirschmann-sw-01", callback=on_snapshot)
        """
        logger.info(
            f"L2Collector starting continuous poll: host={self.host}, "
            f"interval={self.poll_interval_sec}s"
        )
        while True:
            try:
                snapshot = await self.collect_all(device_id=device_id)
                logger.info(
                    f"[L2] {self.host} score={snapshot.health_score} "
                    f"severity={snapshot.overall_severity} "
                    f"anomalies={snapshot.anomalies}"
                )
                if callback:
                    await callback(snapshot)
            except Exception as e:
                logger.error(f"L2Collector poll error for {self.host}: {e}")
            await asyncio.sleep(self.poll_interval_sec)


# ── Multi-Device Manager ──────────────────────────────────────────────────────

class L2CollectorManager:
    """
    Manages L2 collection across multiple switches simultaneously.

    Usage
    -----
    manager = L2CollectorManager()
    manager.add_switch("192.168.1.1", device_id="sw-floor1", expected_vlans=[1,10,20])
    manager.add_switch("192.168.1.2", device_id="sw-floor2", expected_vlans=[1,10,30])
    snapshots = await manager.collect_all()
    """

    def __init__(self):
        self._collectors: List[Tuple[L2Collector, str]] = []

    def add_switch(
        self,
        host: str,
        device_id: str,
        community: str = "public",
        expected_vlans: Optional[List[int]] = None,
        mac_table_capacity: int = DEFAULT_MAC_TABLE_CAPACITY,
    ):
        collector = L2Collector(
            host=host,
            community=community,
            expected_vlans=expected_vlans,
            mac_table_capacity=mac_table_capacity,
        )
        self._collectors.append((collector, device_id))
        logger.info(f"Registered L2 collector: {host} ({device_id})")

    async def collect_all(self) -> List[L2KPISnapshot]:
        """Poll all switches concurrently."""
        tasks = [
            collector.collect_all(device_id=dev_id)
            for collector, dev_id in self._collectors
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        snapshots = []
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"L2 collection failed: {r}")
            else:
                snapshots.append(r)
        return snapshots

    def get_critical_devices(
        self, snapshots: List[L2KPISnapshot]
    ) -> List[L2KPISnapshot]:
        return [s for s in snapshots if s.overall_severity == "critical"]


# ── CLI / Quick Test ──────────────────────────────────────────────────────────

async def _demo():
    """Quick smoke-test — runs in simulation mode if pysnmp not installed."""
    logging.basicConfig(level=logging.INFO)

    manager = L2CollectorManager()
    manager.add_switch(
        "192.168.1.1",
        device_id="hirschmann-sw-01",
        expected_vlans=[1, 10, 20, 30],
    )
    manager.add_switch(
        "192.168.1.2",
        device_id="hirschmann-sw-02",
        expected_vlans=[1, 10, 40],
    )

    print("\n=== L2 KPI Collection Demo ===")
    snapshots = await manager.collect_all()
    for snap in snapshots:
        print(f"\nDevice: {snap.device_id} ({snap.device_ip})")
        print(f"  L2 Health Score : {snap.health_score}/100  [{snap.overall_severity.upper()}]")
        print(f"  STP             : {snap.stp.severity:8s}  {snap.stp.detail}")
        print(f"  MAC Table       : {snap.mac_table.severity:8s}  {snap.mac_table.detail}")
        print(f"  Broadcast       : {snap.broadcast.severity:8s}  {snap.broadcast.detail}")
        print(f"  VLAN            : {snap.vlan.severity:8s}  {snap.vlan.detail}")
        if snap.anomalies:
            print(f"  ⚠ Anomalies:")
            for a in snap.anomalies:
                print(f"      {a}")


if __name__ == "__main__":
    asyncio.run(_demo())
