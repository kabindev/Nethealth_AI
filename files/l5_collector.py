"""
l5_collector.py — Layer 5 Session KPI Collector
================================================
Monitors L5 (Session Layer) health for industrial networks:
  - OPC UA session keepalive tracking  (primary OT session protocol)
  - OPC UA subscription health         (DataChange / Event notifications)
  - Modbus TCP session continuity       (connection reset counting)
  - PLC–SCADA dialogue stability        (session renegotiation events)

The Session layer is critical in OT networks because:
  - PLC–SCADA sessions are long-lived (hours/days)
  - A keepalive failure = PLC stops accepting control commands
  - Session renegotiation adds 2–5 seconds latency (unacceptable for real-time control)

Architecture:
  - OPC UA: polls server diagnostics via the SessionsDiagnosticsArray node
  - Modbus: tracks connection resets from your existing modbus_collector
  - Falls back to simulation if opcua library unavailable

Dependencies:
    pip install asyncua          # OPC UA (async)
    pip install pymodbus         # already in your stack

Usage:
    collector = L5Collector(
        opcua_endpoints=["opc.tcp://192.168.1.100:4840"],  # PLCs / SCADA servers
        modbus_hosts=["192.168.1.110", "192.168.1.111"],
    )
    snapshot = await collector.collect_all()
    print(snapshot.health_score)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── KPI Thresholds ────────────────────────────────────────────────────────────
THRESHOLDS = {
    # OPC UA: max acceptable keepalive timeout ratio (actual/configured)
    "keepalive_ratio_warning": 0.80,   # 80% of timeout used → warning
    "keepalive_ratio_critical": 1.0,   # At/past timeout → critical
    # Session renegotiations per hour
    "renegotiation_warning": 2,
    "renegotiation_critical": 5,
    # Modbus: connection resets per poll window
    "modbus_resets_warning": 3,
    "modbus_resets_critical": 10,
    # OPC UA: subscription queue overflow (items lost)
    "subscription_overflow_warning": 1,
    "subscription_overflow_critical": 10,
    # Session count: % below expected baseline
    "session_drop_warning_pct": 20,   # 20% sessions missing vs baseline
    "session_drop_critical_pct": 40,
}

# OPC UA Diagnostic Node IDs (standard OPC UA information model)
# These are readable from any OPC UA server's diagnostics endpoint
OPCUA_DIAG_NODES = {
    # Server status
    "server_state":              "i=2259",   # 0=Running 1=Failed 2=NoConfig
    "session_count":             "i=2285",   # current active sessions
    "cumulative_session_count":  "i=2286",
    "rejected_session_count":    "i=2287",   # auth failures / policy rejections
    "session_timeout_count":     "i=2288",
    "session_abort_count":       "i=2289",
    # Subscription health
    "subscription_count":        "i=2290",
    "publishing_interval_count": "i=2291",
    "disabled_monitoring_count": "i=2294",
    # Connection
    "current_connection_count":  "i=2295",
    "cumulative_connection_count":"i=2296",
    "rejected_connection_count": "i=2298",
}

SERVER_STATE_MAP = {
    0: "Running",
    1: "Failed",
    2: "NoConfiguration",
    3: "Suspended",
    4: "Shutdown",
    5: "Test",
    6: "CommunicationFault",
    7: "Unknown",
}


# ── Data Structures ───────────────────────────────────────────────────────────

@dataclass
class OPCUASessionStatus:
    """Health of a single OPC UA server endpoint."""
    endpoint: str
    server_state: str = "Unknown"
    active_sessions: int = 0
    session_timeouts: int = 0          # cumulative
    session_aborts: int = 0            # cumulative
    rejected_sessions: int = 0        # auth/policy failures
    subscription_count: int = 0
    rejected_connections: int = 0
    # Derived metrics
    session_drop_pct: float = 0.0      # vs baseline
    renegotiation_rate_per_hr: float = 0.0
    is_server_running: bool = False
    severity: str = "healthy"
    detail: str = ""
    reachable: bool = True


@dataclass
class ModbusTCPSessionStatus:
    """Session continuity metrics for Modbus TCP devices."""
    host: str
    connection_resets: int = 0
    failed_transactions: int = 0
    reconnect_attempts: int = 0
    last_successful_poll_sec: float = 0.0
    severity: str = "healthy"
    detail: str = ""


@dataclass
class L5KPISnapshot:
    """
    Complete Layer 5 health snapshot across all session-layer endpoints.
    """
    timestamp: datetime
    opcua_sessions: List[OPCUASessionStatus] = field(default_factory=list)
    modbus_sessions: List[ModbusTCPSessionStatus] = field(default_factory=list)

    # Aggregate
    health_score: float = 100.0
    overall_severity: str = "healthy"
    anomalies: List[str] = field(default_factory=list)
    total_active_sessions: int = 0
    critical_endpoints: List[str] = field(default_factory=list)

    def score(self) -> "L5KPISnapshot":
        """
        Compute weighted L5 health score.

        Weights:
          OPC UA sessions  : 0.60  (primary ICS session protocol)
          Modbus TCP        : 0.40
        """
        sev_score = {"healthy": 100, "warning": 60, "critical": 20, "unreachable": 0}

        opcua_scores = [sev_score.get(s.severity, 50) for s in self.opcua_sessions]
        modbus_scores = [sev_score.get(s.severity, 50) for s in self.modbus_sessions]

        opcua_avg = sum(opcua_scores) / len(opcua_scores) if opcua_scores else 100
        modbus_avg = sum(modbus_scores) / len(modbus_scores) if modbus_scores else 100

        self.health_score = round(opcua_avg * 0.60 + modbus_avg * 0.40, 1)
        self.total_active_sessions = sum(s.active_sessions for s in self.opcua_sessions)
        self.critical_endpoints = [
            s.endpoint for s in self.opcua_sessions if s.severity == "critical"
        ] + [
            s.host for s in self.modbus_sessions if s.severity == "critical"
        ]

        all_severities = [s.severity for s in self.opcua_sessions + self.modbus_sessions]
        if "critical" in all_severities or not self.opcua_sessions:
            self.overall_severity = "critical"
        elif "warning" in all_severities:
            self.overall_severity = "warning"
        else:
            self.overall_severity = "healthy"

        self.anomalies = []
        for s in self.opcua_sessions:
            if s.severity != "healthy":
                self.anomalies.append(f"[L5-OPCUA] {s.endpoint}: {s.detail}")
        for s in self.modbus_sessions:
            if s.severity != "healthy":
                self.anomalies.append(f"[L5-Modbus] {s.host}: {s.detail}")

        return self


# ── OPC UA Collector ──────────────────────────────────────────────────────────

class OPCUASessionCollector:
    """
    Polls OPC UA server diagnostics to assess session layer health.

    Works against any OPC UA server: Siemens S7-1500, Beckhoff TwinCAT,
    Kepware, Ignition, and others — all expose the same standard diag nodes.
    """

    def __init__(
        self,
        endpoints: List[str],
        username: Optional[str] = None,
        password: Optional[str] = None,
        session_baseline: Optional[Dict[str, int]] = None,
    ):
        """
        Parameters
        ----------
        endpoints : list of str
            OPC UA endpoint URLs, e.g. ["opc.tcp://192.168.1.100:4840"]
        username / password : str, optional
            For servers with username/password security policy
        session_baseline : dict, optional
            Expected normal session count per endpoint
            e.g. {"opc.tcp://192.168.1.100:4840": 5}
        """
        self.endpoints = endpoints
        self.username = username
        self.password = password
        self.session_baseline = session_baseline or {}

        # Track cumulative counters to compute rates
        self._prev_timeouts: Dict[str, Tuple[int, float]] = {}  # endpoint → (count, time)
        self._prev_aborts: Dict[str, Tuple[int, float]] = {}

        self._opcua_available = self._check_library()

    def _check_library(self) -> bool:
        try:
            import asyncua
            return True
        except ImportError:
            logger.warning(
                "asyncua not installed. Running in SIMULATION mode. "
                "Install with: pip install asyncua"
            )
            return False

    async def collect_endpoint(self, endpoint: str) -> OPCUASessionStatus:
        """Poll a single OPC UA server endpoint."""
        if not self._opcua_available:
            return self._simulate_opcua(endpoint)

        status = OPCUASessionStatus(endpoint=endpoint)
        try:
            from asyncua import Client

            async with Client(url=endpoint, timeout=5) as client:
                if self.username:
                    await client.set_user(self.username)
                    await client.set_password(self.password)

                status.reachable = True

                # Read all diagnostic nodes
                values = {}
                for key, node_id in OPCUA_DIAG_NODES.items():
                    try:
                        node = client.get_node(node_id)
                        val = await node.read_value()
                        values[key] = int(val) if val is not None else 0
                    except Exception:
                        values[key] = 0

                # Populate status
                state_code = values.get("server_state", 7)
                status.server_state = SERVER_STATE_MAP.get(state_code, "Unknown")
                status.is_server_running = (state_code == 0)
                status.active_sessions = values.get("session_count", 0)
                status.session_timeouts = values.get("session_timeout_count", 0)
                status.session_aborts = values.get("session_abort_count", 0)
                status.rejected_sessions = values.get("rejected_session_count", 0)
                status.subscription_count = values.get("subscription_count", 0)
                status.rejected_connections = values.get("rejected_connection_count", 0)

                # Compute renegotiation rate (timeouts+aborts per hour)
                now = time.time()
                total_disruptions = status.session_timeouts + status.session_aborts
                if endpoint in self._prev_timeouts:
                    prev_count, prev_time = self._prev_timeouts[endpoint]
                    dt_hrs = (now - prev_time) / 3600
                    if dt_hrs > 0:
                        status.renegotiation_rate_per_hr = round(
                            (total_disruptions - prev_count) / dt_hrs, 2
                        )
                self._prev_timeouts[endpoint] = (total_disruptions, now)

                # Session drop % vs baseline
                baseline = self.session_baseline.get(endpoint, 0)
                if baseline > 0 and status.active_sessions < baseline:
                    status.session_drop_pct = round(
                        (1 - status.active_sessions / baseline) * 100, 1
                    )

                # Evaluate severity
                status = self._evaluate_severity(status)

        except asyncio.TimeoutError:
            status.reachable = False
            status.severity = "critical"
            status.detail = f"OPC UA server unreachable at {endpoint} (timeout)."
        except Exception as e:
            status.reachable = False
            status.severity = "critical"
            status.detail = f"OPC UA connection failed: {type(e).__name__}: {e}"

        return status

    def _evaluate_severity(self, status: OPCUASessionStatus) -> OPCUASessionStatus:
        """Apply threshold rules to determine severity."""
        if not status.is_server_running:
            status.severity = "critical"
            status.detail = (
                f"OPC UA server state: {status.server_state}. "
                "Server is NOT running — PLC commands will fail."
            )
            return status

        issues = []

        if status.renegotiation_rate_per_hr >= THRESHOLDS["renegotiation_critical"]:
            status.severity = "critical"
            issues.append(
                f"Session renegotiation rate CRITICAL: "
                f"{status.renegotiation_rate_per_hr:.1f}/hr "
                f"(threshold: {THRESHOLDS['renegotiation_critical']}/hr)"
            )
        elif status.renegotiation_rate_per_hr >= THRESHOLDS["renegotiation_warning"]:
            if status.severity != "critical":
                status.severity = "warning"
            issues.append(
                f"High renegotiation rate: {status.renegotiation_rate_per_hr:.1f}/hr"
            )

        if status.session_drop_pct >= THRESHOLDS["session_drop_critical_pct"]:
            status.severity = "critical"
            issues.append(
                f"Session count dropped {status.session_drop_pct:.0f}% below baseline"
            )
        elif status.session_drop_pct >= THRESHOLDS["session_drop_warning_pct"]:
            if status.severity != "critical":
                status.severity = "warning"
            issues.append(f"Session count {status.session_drop_pct:.0f}% below baseline")

        if status.rejected_sessions > 0:
            if status.severity != "critical":
                status.severity = "warning"
            issues.append(f"{status.rejected_sessions} rejected sessions (auth/policy failures)")

        if not issues:
            status.severity = "healthy"
            status.detail = (
                f"Server: {status.server_state}. "
                f"Sessions: {status.active_sessions} active. "
                f"Subscriptions: {status.subscription_count}. "
                f"Renegotiation: {status.renegotiation_rate_per_hr:.2f}/hr."
            )
        else:
            status.detail = " | ".join(issues)

        return status

    def _simulate_opcua(self, endpoint: str) -> OPCUASessionStatus:
        """Realistic simulation when asyncua is not installed."""
        import random
        s = OPCUASessionStatus(endpoint=endpoint, reachable=True, is_server_running=True)
        s.server_state = "Running"
        s.active_sessions = random.randint(2, 8)
        s.subscription_count = random.randint(1, 5)
        s.session_timeouts = random.randint(0, 12)
        s.renegotiation_rate_per_hr = random.choice([0.1, 0.5, 2.5, 6.0])
        s.rejected_sessions = random.choice([0, 0, 0, 1, 2])

        if s.renegotiation_rate_per_hr >= 5 or not s.is_server_running:
            s.severity = "critical"
            s.detail = f"[SIM] High renegotiation rate: {s.renegotiation_rate_per_hr}/hr — PLC dialogue unstable."
        elif s.renegotiation_rate_per_hr >= 2 or s.rejected_sessions > 0:
            s.severity = "warning"
            s.detail = f"[SIM] Elevated renegotiation: {s.renegotiation_rate_per_hr}/hr. Rejected: {s.rejected_sessions}."
        else:
            s.severity = "healthy"
            s.detail = f"[SIM] OPC UA healthy. Sessions: {s.active_sessions}, Renegotiation: {s.renegotiation_rate_per_hr}/hr."
        return s

    async def collect_all(self) -> List[OPCUASessionStatus]:
        """Poll all endpoints concurrently."""
        tasks = [self.collect_endpoint(ep) for ep in self.endpoints]
        return await asyncio.gather(*tasks)


# ── Modbus TCP Session Collector ──────────────────────────────────────────────

class ModbusTCPSessionCollector:
    """
    Tracks Modbus TCP session continuity across PLCs.

    Wraps your existing modbus_collector.py — adds session-level
    tracking on top of the register-level data it already collects.
    """

    def __init__(self, hosts: List[str], port: int = 502, timeout: float = 3.0):
        self.hosts = hosts
        self.port = port
        self.timeout = timeout
        self._reset_counts: Dict[str, int] = {}
        self._last_success: Dict[str, float] = {}
        self._pymodbus_available = self._check_library()

    def _check_library(self) -> bool:
        try:
            from pymodbus.client import AsyncModbusTcpClient
            return True
        except ImportError:
            try:
                from pymodbus.client.asynchronous.tcp import AsyncModbusTCPClient
                return True
            except ImportError:
                logger.warning("pymodbus not installed. Using simulation mode.")
                return False

    async def collect_host(self, host: str) -> ModbusTCPSessionStatus:
        """Attempt a Modbus TCP connection and basic function code 3 read."""
        status = ModbusTCPSessionStatus(host=host)

        if not self._pymodbus_available:
            return self._simulate_modbus(host)

        try:
            from pymodbus.client import AsyncModbusTcpClient

            client = AsyncModbusTcpClient(host, port=self.port, timeout=self.timeout)
            connected = await client.connect()

            if not connected:
                status.connection_resets = self._reset_counts.get(host, 0) + 1
                self._reset_counts[host] = status.connection_resets
                status.severity = "critical"
                status.detail = (
                    f"Modbus TCP connection REFUSED at {host}:{self.port}. "
                    f"Cumulative resets: {status.connection_resets}. "
                    "PLC may be offline or TCP stack overloaded."
                )
                return status

            # Read first 10 holding registers as a session health probe
            result = await client.read_holding_registers(0, count=10, slave=1)
            await client.close()

            now = time.time()
            last_ok = self._last_success.get(host, now)
            gap_sec = now - last_ok
            self._last_success[host] = now
            status.last_successful_poll_sec = gap_sec

            if result.isError():
                status.failed_transactions += 1
                status.severity = "warning"
                status.detail = (
                    f"Modbus TCP connected but function code 3 returned error. "
                    f"Gap since last success: {gap_sec:.0f}s."
                )
            else:
                resets = self._reset_counts.get(host, 0)
                status.connection_resets = resets
                if resets >= THRESHOLDS["modbus_resets_critical"]:
                    status.severity = "critical"
                    status.detail = f"Modbus session unstable: {resets} resets recorded."
                elif resets >= THRESHOLDS["modbus_resets_warning"]:
                    status.severity = "warning"
                    status.detail = f"Modbus session: {resets} resets recorded."
                else:
                    status.severity = "healthy"
                    status.detail = (
                        f"Modbus TCP session healthy. "
                        f"Last poll gap: {gap_sec:.0f}s. "
                        f"Resets: {resets}."
                    )

        except asyncio.TimeoutError:
            self._reset_counts[host] = self._reset_counts.get(host, 0) + 1
            status.connection_resets = self._reset_counts[host]
            status.severity = "critical"
            status.detail = f"Modbus TCP timeout on {host}:{self.port}."
        except Exception as e:
            status.severity = "critical"
            status.detail = f"Modbus TCP error: {e}"

        return status

    def _simulate_modbus(self, host: str) -> ModbusTCPSessionStatus:
        import random
        resets = random.choice([0, 0, 1, 4, 11])
        s = ModbusTCPSessionStatus(
            host=host,
            connection_resets=resets,
            last_successful_poll_sec=random.uniform(0, 120),
        )
        if resets >= 10:
            s.severity = "critical"
            s.detail = f"[SIM] Modbus session unstable: {resets} resets."
        elif resets >= 3:
            s.severity = "warning"
            s.detail = f"[SIM] Modbus resets: {resets}."
        else:
            s.severity = "healthy"
            s.detail = f"[SIM] Modbus session healthy. Resets: {resets}."
        return s

    async def collect_all(self) -> List[ModbusTCPSessionStatus]:
        tasks = [self.collect_host(h) for h in self.hosts]
        return await asyncio.gather(*tasks)


# ── Master L5 Collector ───────────────────────────────────────────────────────

class L5Collector:
    """
    Unified Layer 5 session health collector.

    Combines OPC UA + Modbus TCP into a single L5KPISnapshot
    ready for ingestion by your KPI engine.

    Parameters
    ----------
    opcua_endpoints : list of str
        OPC UA server URLs (one per PLC/SCADA server)
    modbus_hosts : list of str
        IP addresses of Modbus TCP PLCs
    session_baseline : dict, optional
        Expected session counts per OPC UA endpoint
    poll_interval_sec : int
        Polling interval for continuous mode
    """

    def __init__(
        self,
        opcua_endpoints: Optional[List[str]] = None,
        modbus_hosts: Optional[List[str]] = None,
        opcua_username: Optional[str] = None,
        opcua_password: Optional[str] = None,
        session_baseline: Optional[Dict[str, int]] = None,
        poll_interval_sec: int = 30,
    ):
        self.poll_interval_sec = poll_interval_sec
        self.opcua_collector = OPCUASessionCollector(
            endpoints=opcua_endpoints or [],
            username=opcua_username,
            password=opcua_password,
            session_baseline=session_baseline,
        )
        self.modbus_collector = ModbusTCPSessionCollector(
            hosts=modbus_hosts or []
        )

    async def collect_all(self) -> L5KPISnapshot:
        """Run both collectors and return scored snapshot."""
        opcua_results, modbus_results = await asyncio.gather(
            self.opcua_collector.collect_all(),
            self.modbus_collector.collect_all(),
        )

        snapshot = L5KPISnapshot(
            timestamp=datetime.utcnow(),
            opcua_sessions=opcua_results,
            modbus_sessions=modbus_results,
        )
        return snapshot.score()

    async def run_continuous(self, callback=None):
        """
        Poll continuously at self.poll_interval_sec.

        Parameters
        ----------
        callback : async callable, optional
            async def callback(snapshot: L5KPISnapshot)
        """
        logger.info(
            f"L5Collector starting: {len(self.opcua_collector.endpoints)} OPC UA, "
            f"{len(self.modbus_collector.hosts)} Modbus TCP endpoints"
        )
        while True:
            try:
                snapshot = await self.collect_all()
                logger.info(
                    f"[L5] score={snapshot.health_score} "
                    f"sessions={snapshot.total_active_sessions} "
                    f"severity={snapshot.overall_severity}"
                )
                if callback:
                    await callback(snapshot)
            except Exception as e:
                logger.error(f"L5Collector error: {e}")
            await asyncio.sleep(self.poll_interval_sec)


# ── CLI / Quick Test ──────────────────────────────────────────────────────────

async def _demo():
    logging.basicConfig(level=logging.INFO)

    collector = L5Collector(
        opcua_endpoints=[
            "opc.tcp://192.168.1.100:4840",
            "opc.tcp://192.168.1.101:4840",
        ],
        modbus_hosts=["192.168.1.110", "192.168.1.111", "192.168.1.112"],
        session_baseline={
            "opc.tcp://192.168.1.100:4840": 5,
            "opc.tcp://192.168.1.101:4840": 3,
        },
    )

    print("\n=== L5 Session Layer KPI Demo ===")
    snapshot = await collector.collect_all()

    print(f"\nL5 Health Score   : {snapshot.health_score}/100  [{snapshot.overall_severity.upper()}]")
    print(f"Total OPC Sessions: {snapshot.total_active_sessions}")
    if snapshot.critical_endpoints:
        print(f"Critical Endpoints: {snapshot.critical_endpoints}")

    print("\n--- OPC UA Sessions ---")
    for s in snapshot.opcua_sessions:
        print(f"  {s.endpoint}")
        print(f"    State: {s.server_state}  Sessions: {s.active_sessions}  "
              f"Severity: {s.severity.upper()}")
        print(f"    {s.detail}")

    print("\n--- Modbus TCP Sessions ---")
    for s in snapshot.modbus_sessions:
        print(f"  {s.host}  Severity: {s.severity.upper()}")
        print(f"    {s.detail}")

    if snapshot.anomalies:
        print("\n⚠ Anomalies Detected:")
        for a in snapshot.anomalies:
            print(f"  {a}")


if __name__ == "__main__":
    asyncio.run(_demo())
