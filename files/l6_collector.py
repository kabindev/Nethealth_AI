"""
l6_collector.py — Layer 6 Presentation KPI Collector
=====================================================
Monitors L6 (Presentation Layer) health by parsing syslog streams
and log files from Belden EAGLE routers and Hirschmann switches:

  - TLS handshake failures   (TLS alert codes from EAGLE firewall logs)
  - Certificate expiry        (days until cert expires — predictive)
  - Encoding/encoding errors  (Modbus frame errors, OPC UA data type faults)
  - Protocol translation faults (Modbus-to-OPC-UA bridge errors)
  - SSH authentication issues  (brute force / config errors)

Why L6 matters in OT:
  - EAGLE routers terminate TLS for SCADA-to-cloud tunnels
  - TLS handshake fail = no remote monitoring, no historian data
  - Certificate expiry is the #1 cause of unplanned outages in OT (operators forget)
  - Modbus frame encoding errors cause silent data corruption in PLCs

Data Sources:
  - Syslog UDP listener (port 514) — receives from EAGLE routers + Hirschmann
  - Log file parser    — for offline/file-based log analysis
  - Certificate scanner — probes HTTPS/TLS ports for cert expiry

Dependencies:
    pip install cryptography    # for certificate parsing
    (syslog listener uses only stdlib)

Usage:
    # Real-time syslog mode
    collector = L6Collector(syslog_port=514)
    await collector.start_syslog_listener()
    snapshot = collector.get_snapshot()

    # File-based log parsing
    collector = L6Collector()
    snapshot = await collector.parse_log_file("/var/log/eagle_router.log")
"""

import asyncio
import logging
import re
import socket
import ssl
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── KPI Thresholds ────────────────────────────────────────────────────────────
THRESHOLDS = {
    # TLS handshake failures per hour
    "tls_failure_warning": 3,
    "tls_failure_critical": 10,
    # Certificate expiry days remaining
    "cert_expiry_warning_days": 30,
    "cert_expiry_critical_days": 7,
    # Encoding errors per hour
    "encoding_error_warning": 5,
    "encoding_error_critical": 20,
    # Protocol translation errors per hour
    "proto_trans_error_warning": 2,
    "proto_trans_error_critical": 8,
}

# ── Syslog Pattern Library ────────────────────────────────────────────────────
# Patterns are ordered by specificity. Each dict has:
#   pattern   : compiled regex
#   category  : L6 fault category
#   severity  : critical | warning | info
#   action    : human-readable remediation
SYSLOG_PATTERNS = [
    # ── TLS Handshake Failures ────────────────────────────────────────────────
    {
        "pattern": re.compile(
            r"(TLS|SSL).*(handshake|HANDSHAKE).*(fail|error|alert|timeout)",
            re.IGNORECASE,
        ),
        "category": "tls_handshake_failure",
        "severity": "critical",
        "action": "Check certificate validity and cipher suite compatibility on EAGLE router.",
    },
    {
        "pattern": re.compile(
            r"SSL_ERROR|ssl_error|TLS alert received|alert number (\d+)",
            re.IGNORECASE,
        ),
        "category": "tls_handshake_failure",
        "severity": "critical",
        "action": "TLS alert received. Check peer certificate and supported TLS version (min TLS 1.2 for ICS).",
    },
    {
        "pattern": re.compile(
            r"(certificate|cert).*(expire|expir|invalid|revoked|self.signed)",
            re.IGNORECASE,
        ),
        "category": "certificate_issue",
        "severity": "critical",
        "action": "Renew certificate immediately. Check CA chain. Expired cert = no TLS sessions.",
    },
    {
        "pattern": re.compile(
            r"certificate.*(warning|expire).{0,30}(\d+) day",
            re.IGNORECASE,
        ),
        "category": "certificate_expiry_warning",
        "severity": "warning",
        "action": "Certificate expiring soon. Schedule renewal to avoid outage.",
    },
    # ── Encoding / Data Format Errors ─────────────────────────────────────────
    {
        "pattern": re.compile(
            r"(encoding|decoding|decode|encode).*(error|fail|invalid|exception)",
            re.IGNORECASE,
        ),
        "category": "encoding_error",
        "severity": "warning",
        "action": "Data encoding error. Check Modbus data type mapping or OPC UA variant type config.",
    },
    {
        "pattern": re.compile(
            r"(Modbus|modbus).*(CRC|frame|pdu|illegal.function|exception code)",
            re.IGNORECASE,
        ),
        "category": "modbus_frame_error",
        "severity": "warning",
        "action": "Modbus frame error. Check register address mapping and function code support on PLC.",
    },
    {
        "pattern": re.compile(
            r"OPC.UA.*(BadEncodingError|BadDecodingError|BadDataTypeIdUnknown|BadTypeMismatch)",
            re.IGNORECASE,
        ),
        "category": "opcua_encoding_error",
        "severity": "warning",
        "action": "OPC UA data type mismatch. Verify NodeId mapping and variant types in your OPC UA server config.",
    },
    # ── Protocol Translation (Modbus ↔ OPC UA bridge) ─────────────────────────
    {
        "pattern": re.compile(
            r"(protocol.translat|gateway|bridge).*(error|fail|timeout|mismatch)",
            re.IGNORECASE,
        ),
        "category": "protocol_translation_error",
        "severity": "warning",
        "action": "Protocol translation fault. Check Modbus-to-OPC UA mapping config in EAGLE gateway.",
    },
    # ── SSH / Auth Issues ─────────────────────────────────────────────────────
    {
        "pattern": re.compile(
            r"(SSH|ssh).*(authentication|auth).*(fail|error|invalid)",
            re.IGNORECASE,
        ),
        "category": "ssh_auth_failure",
        "severity": "warning",
        "action": "SSH auth failure. Check key/credentials. Repeated failures may indicate brute force.",
    },
    {
        "pattern": re.compile(
            r"(Failed password|authentication failure|Invalid user)",
            re.IGNORECASE,
        ),
        "category": "auth_failure",
        "severity": "warning",
        "action": "Authentication failure. Review access credentials and consider IP allowlisting.",
    },
    # ── Cipher/Protocol Version ───────────────────────────────────────────────
    {
        "pattern": re.compile(
            r"(unsupported|unknown|no shared).*(cipher|protocol|version|ciphersuite)",
            re.IGNORECASE,
        ),
        "category": "cipher_mismatch",
        "severity": "critical",
        "action": "Cipher/protocol mismatch. Update TLS config on EAGLE router to match peer capabilities.",
    },
    # ── General L6 Errors ─────────────────────────────────────────────────────
    {
        "pattern": re.compile(
            r"(compression|decompression).*(error|fail)",
            re.IGNORECASE,
        ),
        "category": "compression_error",
        "severity": "warning",
        "action": "Data compression error. Check SCADA historian data compression settings.",
    },
]

# ── Data Structures ───────────────────────────────────────────────────────────

@dataclass
class ParsedSyslogEvent:
    """A single parsed syslog event with L6 classification."""
    raw_line: str
    timestamp: datetime
    source_ip: str
    category: str
    severity: str
    action: str
    matched_pattern: str = ""
    device_hostname: str = ""
    facility: str = ""
    priority: int = 0


@dataclass
class TLSStatus:
    """TLS/SSL health summary."""
    failures_last_hour: int = 0
    failure_rate_per_hr: float = 0.0
    recent_failures: List[ParsedSyslogEvent] = field(default_factory=list)
    cipher_mismatches: int = 0
    severity: str = "healthy"
    detail: str = ""


@dataclass
class CertificateStatus:
    """Certificate health for all monitored TLS endpoints."""
    certs_checked: List[Dict] = field(default_factory=list)
    # Each dict: {host, port, days_remaining, subject, expires}
    expiring_soon: List[Dict] = field(default_factory=list)
    expired: List[Dict] = field(default_factory=list)
    severity: str = "healthy"
    detail: str = ""


@dataclass
class EncodingStatus:
    """Data encoding / protocol translation health."""
    encoding_errors_last_hour: int = 0
    modbus_frame_errors: int = 0
    opcua_type_errors: int = 0
    protocol_translation_errors: int = 0
    severity: str = "healthy"
    detail: str = ""


@dataclass
class L6KPISnapshot:
    """Complete Layer 6 health snapshot."""
    timestamp: datetime
    tls: TLSStatus = field(default_factory=TLSStatus)
    certificates: CertificateStatus = field(default_factory=CertificateStatus)
    encoding: EncodingStatus = field(default_factory=EncodingStatus)

    health_score: float = 100.0
    overall_severity: str = "healthy"
    anomalies: List[str] = field(default_factory=list)
    raw_event_count: int = 0

    def score(self) -> "L6KPISnapshot":
        """
        Weighted L6 health score.

        Weights:
          TLS health          : 0.45  (most critical — no TLS = no remote access)
          Certificate status  : 0.35  (predictive — catch before expiry)
          Encoding errors     : 0.20
        """
        sev_score = {"healthy": 100, "warning": 60, "critical": 20}

        self.health_score = round(
            sev_score[self.tls.severity] * 0.45
            + sev_score[self.certificates.severity] * 0.35
            + sev_score[self.encoding.severity] * 0.20,
            1,
        )

        all_sevs = [self.tls.severity, self.certificates.severity, self.encoding.severity]
        if "critical" in all_sevs:
            self.overall_severity = "critical"
        elif "warning" in all_sevs:
            self.overall_severity = "warning"
        else:
            self.overall_severity = "healthy"

        self.anomalies = []
        if self.tls.severity != "healthy":
            self.anomalies.append(f"[L6-TLS] {self.tls.detail}")
        if self.certificates.severity != "healthy":
            self.anomalies.append(f"[L6-CERT] {self.certificates.detail}")
        if self.encoding.severity != "healthy":
            self.anomalies.append(f"[L6-ENC] {self.encoding.detail}")

        return self


# ── Syslog Parser ─────────────────────────────────────────────────────────────

class SyslogParser:
    """
    Parses RFC 3164 / RFC 5424 syslog messages and classifies them
    into L6 KPI categories using the SYSLOG_PATTERNS library.
    """

    # RFC 3164 pattern: <priority>timestamp hostname process: message
    RFC3164 = re.compile(
        r"^<(\d+)>(\w{3}\s+\d+\s[\d:]+)\s+(\S+)\s+(\S+):\s+(.+)$"
    )
    # RFC 5424 pattern: <priority>version timestamp hostname app-name procid msgid msg
    RFC5424 = re.compile(
        r"^<(\d+)>(\d)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.+)$"
    )

    def parse_line(
        self, raw: str, source_ip: str = "unknown"
    ) -> Optional[ParsedSyslogEvent]:
        """
        Parse one syslog line and return a classified event, or None
        if the line doesn't match any L6 pattern.
        """
        raw = raw.strip()
        if not raw:
            return None

        # Try to extract hostname and message body from syslog format
        hostname = source_ip
        message = raw
        timestamp = datetime.utcnow()

        m = self.RFC3164.match(raw)
        if m:
            priority = int(m.group(1))
            hostname = m.group(3)
            message = f"{m.group(4)}: {m.group(5)}"
        else:
            m5 = self.RFC5424.match(raw)
            if m5:
                priority = int(m5.group(1))
                hostname = m5.group(4)
                message = m5.group(8)

        # Match against L6 pattern library
        for pattern_def in SYSLOG_PATTERNS:
            if pattern_def["pattern"].search(message):
                return ParsedSyslogEvent(
                    raw_line=raw,
                    timestamp=timestamp,
                    source_ip=source_ip,
                    category=pattern_def["category"],
                    severity=pattern_def["severity"],
                    action=pattern_def["action"],
                    matched_pattern=pattern_def["pattern"].pattern,
                    device_hostname=hostname,
                )

        return None  # Not an L6 event — ignore

    def parse_file(self, filepath: str, source_ip: str = "file") -> List[ParsedSyslogEvent]:
        """Parse all L6 events from a log file."""
        events = []
        path = Path(filepath)
        if not path.exists():
            logger.warning(f"Log file not found: {filepath}")
            return events
        with open(path, "r", errors="replace") as f:
            for line in f:
                evt = self.parse_line(line, source_ip=source_ip)
                if evt:
                    events.append(evt)
        logger.info(f"Parsed {len(events)} L6 events from {filepath}")
        return events


# ── Certificate Scanner ───────────────────────────────────────────────────────

class CertificateScanner:
    """
    Probes HTTPS/TLS ports on EAGLE routers and SCADA servers
    and reports days until certificate expiry.

    Proactive: warns 30 days before expiry so you never get a surprise outage.
    """

    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout

    async def check_cert(self, host: str, port: int = 443) -> Dict:
        """
        Check TLS certificate expiry for a host:port.

        Returns dict with: host, port, days_remaining, subject, expires, error
        """
        result = {"host": host, "port": port, "days_remaining": None,
                  "subject": None, "expires": None, "error": None}
        try:
            loop = asyncio.get_event_loop()
            cert_info = await asyncio.wait_for(
                loop.run_in_executor(None, self._get_cert_sync, host, port),
                timeout=self.timeout,
            )
            result.update(cert_info)
        except asyncio.TimeoutError:
            result["error"] = f"Connection timeout ({self.timeout}s)"
        except Exception as e:
            result["error"] = str(e)
        return result

    def _get_cert_sync(self, host: str, port: int) -> Dict:
        """Synchronous cert fetch (run in executor to avoid blocking)."""
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_OPTIONAL
            with socket.create_connection((host, port), timeout=self.timeout) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                    cert = ssock.getpeercert()

            # Parse expiry date
            not_after_str = cert.get("notAfter", "")
            # Format: "Dec 15 12:00:00 2025 GMT"
            not_after = datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z")
            days_remaining = (not_after - datetime.utcnow()).days

            # Extract subject CN
            subject = dict(x[0] for x in cert.get("subject", []))
            cn = subject.get("commonName", "unknown")

            return {
                "days_remaining": days_remaining,
                "subject": cn,
                "expires": not_after.strftime("%Y-%m-%d"),
            }
        except ssl.SSLError as e:
            return {"error": f"SSL error: {e}"}
        except Exception as e:
            return {"error": str(e)}

    async def scan_all(self, hosts: List[Tuple[str, int]]) -> CertificateStatus:
        """
        Scan multiple hosts and return aggregated CertificateStatus.

        Parameters
        ----------
        hosts : list of (host, port) tuples
            e.g. [("192.168.1.1", 8443), ("192.168.1.2", 443)]
        """
        status = CertificateStatus()
        tasks = [self.check_cert(host, port) for host, port in hosts]
        results = await asyncio.gather(*tasks)

        status.certs_checked = results
        status.expired = [
            r for r in results
            if r["days_remaining"] is not None and r["days_remaining"] <= 0
        ]
        status.expiring_soon = [
            r for r in results
            if r["days_remaining"] is not None
            and 0 < r["days_remaining"] <= THRESHOLDS["cert_expiry_warning_days"]
        ]

        if status.expired:
            status.severity = "critical"
            hosts_str = ", ".join(f"{r['host']}:{r['port']}" for r in status.expired)
            status.detail = (
                f"EXPIRED certificates on: {hosts_str}. "
                "TLS connections will FAIL. Renew immediately."
            )
        elif any(
            r["days_remaining"] is not None
            and r["days_remaining"] <= THRESHOLDS["cert_expiry_critical_days"]
            for r in results
        ):
            status.severity = "critical"
            crit = [
                r for r in results
                if r["days_remaining"] is not None
                and r["days_remaining"] <= THRESHOLDS["cert_expiry_critical_days"]
            ]
            status.detail = (
                f"Certificates expiring in ≤{THRESHOLDS['cert_expiry_critical_days']} days: "
                + ", ".join(f"{r['host']} ({r['days_remaining']}d)" for r in crit)
            )
        elif status.expiring_soon:
            status.severity = "warning"
            status.detail = (
                f"{len(status.expiring_soon)} certificate(s) expiring within "
                f"{THRESHOLDS['cert_expiry_warning_days']} days: "
                + ", ".join(
                    f"{r['host']} ({r['days_remaining']}d)" for r in status.expiring_soon
                )
            )
        else:
            status.severity = "healthy"
            valid = [r for r in results if r.get("days_remaining") is not None]
            if valid:
                min_days = min(r["days_remaining"] for r in valid)
                status.detail = (
                    f"All {len(valid)} certificates valid. "
                    f"Earliest expiry: {min_days} days."
                )
            else:
                status.detail = "Certificate status unavailable (connection errors)."

        return status


# ── Master L6 Collector ───────────────────────────────────────────────────────

class L6Collector:
    """
    Unified Layer 6 presentation health collector.

    Combines:
      - Real-time syslog listener (UDP)
      - Certificate expiry scanning
      - Log file parsing

    Parameters
    ----------
    syslog_port : int
        UDP port to listen on for syslog messages (default 514, needs root;
        use 5140 if running without root).
    tls_hosts : list of (host, port)
        Hosts to scan for certificate expiry.
    log_files : list of str
        Log file paths to parse on each collection cycle.
    poll_interval_sec : int
        How often to aggregate a snapshot from the event buffer.
    window_seconds : int
        Time window for rate calculations (default 3600 = 1 hour).
    """

    def __init__(
        self,
        syslog_port: int = 5140,
        tls_hosts: Optional[List[Tuple[str, int]]] = None,
        log_files: Optional[List[str]] = None,
        poll_interval_sec: int = 60,
        window_seconds: int = 3600,
    ):
        self.syslog_port = syslog_port
        self.tls_hosts = tls_hosts or []
        self.log_files = log_files or []
        self.poll_interval_sec = poll_interval_sec
        self.window_seconds = window_seconds

        self._parser = SyslogParser()
        self._cert_scanner = CertificateScanner()

        # Rolling event buffer (deque of ParsedSyslogEvent, max 10000 events)
        self._event_buffer: deque = deque(maxlen=10_000)
        self._syslog_running = False
        self._simulation_mode = False

    # ── Syslog UDP Listener ───────────────────────────────────────────────────

    async def start_syslog_listener(self):
        """
        Start async UDP syslog listener.
        Events are parsed and buffered; call get_snapshot() to aggregate.

        Typically run as a background task:
            asyncio.create_task(collector.start_syslog_listener())
        """
        loop = asyncio.get_event_loop()

        class SyslogProtocol(asyncio.DatagramProtocol):
            def __init__(self, collector_ref):
                self._col = collector_ref

            def datagram_received(self, data, addr):
                try:
                    message = data.decode("utf-8", errors="replace")
                    source_ip = addr[0]
                    evt = self._col._parser.parse_line(message, source_ip=source_ip)
                    if evt:
                        self._col._event_buffer.append(evt)
                except Exception as e:
                    logger.debug(f"Syslog parse error: {e}")

        try:
            transport, _ = await loop.create_datagram_endpoint(
                lambda: SyslogProtocol(self),
                local_addr=("0.0.0.0", self.syslog_port),
            )
            self._syslog_running = True
            logger.info(f"Syslog UDP listener started on port {self.syslog_port}")
        except PermissionError:
            logger.warning(
                f"Cannot bind syslog port {self.syslog_port} (permission denied). "
                "Try port 5140 or run as root. Falling back to simulation."
            )
            self._simulation_mode = True
        except Exception as e:
            logger.error(f"Syslog listener failed: {e}. Using simulation mode.")
            self._simulation_mode = True

    # ── Snapshot Aggregation ──────────────────────────────────────────────────

    def _build_tls_status(self, window_events: List[ParsedSyslogEvent]) -> TLSStatus:
        """Aggregate TLS events from the time window into a TLSStatus."""
        status = TLSStatus()

        tls_failures = [
            e for e in window_events
            if e.category in ("tls_handshake_failure", "certificate_issue", "cipher_mismatch")
        ]
        cipher_mismatches = [e for e in window_events if e.category == "cipher_mismatch"]

        status.failures_last_hour = len(tls_failures)
        status.cipher_mismatches = len(cipher_mismatches)
        status.recent_failures = tls_failures[-5:]  # Keep last 5 for display

        # Rate calculation
        if window_events:
            oldest = min(e.timestamp for e in window_events)
            dt_hrs = max((datetime.utcnow() - oldest).total_seconds() / 3600, 0.01)
            status.failure_rate_per_hr = round(len(tls_failures) / dt_hrs, 1)

        if status.failures_last_hour >= THRESHOLDS["tls_failure_critical"] or \
                status.cipher_mismatches > 0:
            status.severity = "critical"
            status.detail = (
                f"TLS CRITICAL: {status.failures_last_hour} failures/hr. "
                f"Cipher mismatches: {status.cipher_mismatches}. "
                f"ACTION: {tls_failures[-1].action if tls_failures else 'Check EAGLE router TLS config.'}"
            )
        elif status.failures_last_hour >= THRESHOLDS["tls_failure_warning"]:
            status.severity = "warning"
            status.detail = (
                f"TLS warnings: {status.failures_last_hour} failures in window. "
                f"Rate: {status.failure_rate_per_hr:.1f}/hr."
            )
        else:
            status.severity = "healthy"
            status.detail = f"TLS healthy: {status.failures_last_hour} failures in window."

        return status

    def _build_encoding_status(
        self, window_events: List[ParsedSyslogEvent]
    ) -> EncodingStatus:
        """Aggregate encoding/translation events into EncodingStatus."""
        status = EncodingStatus()

        enc_events = [
            e for e in window_events
            if e.category in (
                "encoding_error", "modbus_frame_error",
                "opcua_encoding_error", "protocol_translation_error",
            )
        ]

        status.encoding_errors_last_hour = len(enc_events)
        status.modbus_frame_errors = sum(
            1 for e in enc_events if e.category == "modbus_frame_error"
        )
        status.opcua_type_errors = sum(
            1 for e in enc_events if e.category == "opcua_encoding_error"
        )
        status.protocol_translation_errors = sum(
            1 for e in enc_events if e.category == "protocol_translation_error"
        )

        total = status.encoding_errors_last_hour
        if total >= THRESHOLDS["encoding_error_critical"]:
            status.severity = "critical"
            status.detail = (
                f"Encoding CRITICAL: {total} errors/hr. "
                f"Modbus frames: {status.modbus_frame_errors}, "
                f"OPC UA types: {status.opcua_type_errors}. "
                f"ACTION: {enc_events[-1].action if enc_events else 'Check protocol mapping config.'}"
            )
        elif total >= THRESHOLDS["encoding_error_warning"]:
            status.severity = "warning"
            status.detail = (
                f"Encoding errors: {total}/hr. "
                f"Modbus: {status.modbus_frame_errors}, OPC UA: {status.opcua_type_errors}."
            )
        else:
            status.severity = "healthy"
            status.detail = f"Encoding healthy: {total} errors in window."

        return status

    def _simulate_events(self) -> List[ParsedSyslogEvent]:
        """Generate simulated L6 events for demo mode."""
        import random
        simulated_lines = [
            "<134>Dec 15 10:00:01 eagle-router-01 openssl: TLS handshake failed: alert number 42",
            "<134>Dec 15 10:01:00 eagle-router-01 openssl: SSL_ERROR: certificate expired on SCADA endpoint",
            "<134>Dec 15 10:05:00 hirschmann-sw-01 modbus-gw: Modbus CRC frame error on register 40010",
            "<134>Dec 15 10:10:00 eagle-router-01 openssl: unsupported cipher suite: TLS_RSA_WITH_RC4",
            "<134>Dec 15 10:15:00 plc-47 opcua: OPC UA BadEncodingError on node ns=2;i=1001",
            "<134>Dec 15 10:20:00 eagle-router-01 protocol-bridge: protocol translation error Modbus->OPCUA",
            "<134>Dec 15 10:25:00 eagle-router-01 sshd: SSH authentication failed for user admin",
            "<134>Dec 15 10:30:00 eagle-router-01 openssl: certificate warning expiring in 12 days",
        ]

        # Randomly inject healthy or faulty scenarios
        scenario = random.choice(["healthy", "warning", "critical"])
        lines = []
        if scenario == "healthy":
            lines = simulated_lines[-1:]  # just a cert warning
        elif scenario == "warning":
            lines = simulated_lines[2:5]  # encoding errors
        else:
            lines = simulated_lines[:4]   # TLS failures + cert

        events = []
        for line in lines:
            evt = self._parser.parse_line(line, source_ip="192.168.1.1")
            if evt:
                events.append(evt)
        return events

    async def parse_log_file(self, filepath: str, source_ip: str = "file") -> None:
        """Parse a log file and add events to the buffer."""
        events = self._parser.parse_file(filepath, source_ip=source_ip)
        for evt in events:
            self._event_buffer.append(evt)
        logger.info(f"Loaded {len(events)} L6 events from {filepath}")

    def get_snapshot(self) -> L6KPISnapshot:
        """
        Aggregate the current event buffer into an L6KPISnapshot.
        Call this after start_syslog_listener() has been running.
        """
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=self.window_seconds)

        # If in simulation mode, inject fake events
        if self._simulation_mode or not self._event_buffer:
            for evt in self._simulate_events():
                self._event_buffer.append(evt)

        # Filter to time window
        window_events = [
            e for e in self._event_buffer
            if e.timestamp >= cutoff
        ]

        snapshot = L6KPISnapshot(
            timestamp=now,
            tls=self._build_tls_status(window_events),
            encoding=self._build_encoding_status(window_events),
            raw_event_count=len(window_events),
        )
        # Certificates are populated separately via scan_certs()
        return snapshot

    async def scan_certs(self) -> CertificateStatus:
        """Probe TLS endpoints for certificate expiry."""
        if not self.tls_hosts:
            return CertificateStatus(
                severity="healthy",
                detail="No TLS hosts configured for certificate scanning.",
            )
        return await self._cert_scanner.scan_all(self.tls_hosts)

    async def collect_all(self) -> L6KPISnapshot:
        """
        Full L6 collection: parse log files + scan certs + aggregate snapshot.
        """
        # Parse any configured log files
        for lf in self.log_files:
            await self.parse_log_file(lf)

        # Build snapshot from event buffer
        snapshot = self.get_snapshot()

        # Scan certificates
        snapshot.certificates = await self.scan_certs()

        return snapshot.score()

    async def run_continuous(self, callback=None):
        """
        Start syslog listener + continuous polling loop.

        Parameters
        ----------
        callback : async callable, optional
            async def callback(snapshot: L6KPISnapshot)
        """
        await self.start_syslog_listener()
        logger.info(f"L6Collector running. Poll interval: {self.poll_interval_sec}s")

        while True:
            try:
                # Also parse log files each cycle
                for lf in self.log_files:
                    await self.parse_log_file(lf)

                snapshot = self.get_snapshot()
                snapshot.certificates = await self.scan_certs()
                snapshot.score()

                logger.info(
                    f"[L6] score={snapshot.health_score} "
                    f"severity={snapshot.overall_severity} "
                    f"events={snapshot.raw_event_count}"
                )
                if callback:
                    await callback(snapshot)
            except Exception as e:
                logger.error(f"L6Collector error: {e}")

            await asyncio.sleep(self.poll_interval_sec)


# ── CLI / Quick Test ──────────────────────────────────────────────────────────

async def _demo():
    logging.basicConfig(level=logging.INFO)

    collector = L6Collector(
        syslog_port=5140,
        tls_hosts=[
            ("google.com", 443),      # Will actually check cert
            ("expired.badssl.com", 443),  # Example expired cert
        ],
        poll_interval_sec=10,
    )

    print("\n=== L6 Presentation Layer KPI Demo ===")
    snapshot = await collector.collect_all()

    print(f"\nL6 Health Score : {snapshot.health_score}/100  [{snapshot.overall_severity.upper()}]")
    print(f"Events in window: {snapshot.raw_event_count}")
    print(f"\nTLS Status      : {snapshot.tls.severity.upper()}")
    print(f"  {snapshot.tls.detail}")
    print(f"\nCertificates    : {snapshot.certificates.severity.upper()}")
    print(f"  {snapshot.certificates.detail}")
    if snapshot.certificates.certs_checked:
        for c in snapshot.certificates.certs_checked:
            if c.get("days_remaining") is not None:
                print(f"    {c['host']}:{c['port']} — {c['days_remaining']} days remaining ({c['subject']})")
            elif c.get("error"):
                print(f"    {c['host']}:{c['port']} — error: {c['error']}")
    print(f"\nEncoding        : {snapshot.encoding.severity.upper()}")
    print(f"  {snapshot.encoding.detail}")

    if snapshot.anomalies:
        print("\n⚠ Anomalies Detected:")
        for a in snapshot.anomalies:
            print(f"  {a}")


if __name__ == "__main__":
    asyncio.run(_demo())
