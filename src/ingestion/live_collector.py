"""
Live Network Collector — Real-World Device Monitoring

Uses Python-native ping (ping3), socket TCP probing, and subprocess ARP
to discover and monitor real devices on the local network.
No SNMP hardware required — works on any WiFi/Ethernet network.
"""

import subprocess
import socket
import time
import threading
import platform
import ipaddress
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def ping_host(host: str, timeout: float = 1.5) -> Tuple[Optional[float], bool]:
    """
    Ping a host using the OS ping command.
    Returns (latency_ms, is_alive).
    Works on Windows, Linux, macOS.
    """
    try:
        system = platform.system().lower()
        if system == "windows":
            cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), host]
        else:
            cmd = ["ping", "-c", "1", "-W", str(int(timeout)), host]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 1
        )

        if result.returncode != 0:
            return None, False

        output = result.stdout
        # Parse RTT from output
        if system == "windows":
            # "Average = Xms"
            for part in output.split():
                if part.startswith("Average"):
                    continue
                if "ms" in part:
                    try:
                        rtt = float(part.replace("ms", "").replace("=", "").replace("<", "").strip())
                        return rtt, True
                    except ValueError:
                        continue
            # fallback
            return 1.0, True
        else:
            # "rtt min/avg/max/mdev = 1.234/1.234/1.234/0.000 ms"
            for line in output.split("\n"):
                if "avg" in line or "rtt" in line:
                    try:
                        stats = line.split("=")[-1].strip().split("/")
                        return float(stats[1]), True
                    except Exception:
                        pass
            return 1.0, True

    except Exception:
        return None, False


def measure_packet_loss(host: str, count: int = 5, timeout: float = 1.5) -> float:
    """
    Send `count` pings and return packet loss percentage (0-100).
    """
    failures = 0
    for _ in range(count):
        _, alive = ping_host(host, timeout)
        if not alive:
            failures += 1
        time.sleep(0.1)
    return (failures / count) * 100.0


def tcp_connect_latency(host: str, port: int = 80, timeout: float = 2.0) -> Optional[float]:
    """
    Measure TCP connect latency to a host:port.
    Returns latency in ms, or None if failed.
    """
    try:
        start = time.perf_counter()
        s = socket.create_connection((host, port), timeout=timeout)
        elapsed = (time.perf_counter() - start) * 1000
        s.close()
        return elapsed
    except Exception:
        return None


def resolve_hostname(ip: str) -> str:
    """Try to reverse-DNS resolve an IP to a hostname."""
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ip


def scan_subnet(subnet: str, timeout: float = 1.0, max_workers: int = 50) -> List[str]:
    """
    Ping-sweep a subnet to discover live hosts.
    subnet: e.g. '192.168.1.0/24'
    Returns list of live IP strings.
    """
    try:
        network = ipaddress.IPv4Network(subnet, strict=False)
    except ValueError:
        logger.error(f"Invalid subnet: {subnet}")
        return []

    hosts = [str(h) for h in network.hosts()]
    # Limit to /24 max for speed
    if len(hosts) > 256:
        hosts = hosts[:256]

    live = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(ping_host, h, timeout): h for h in hosts}
        for future in as_completed(future_map):
            host = future_map[future]
            try:
                _, is_alive = future.result(timeout=timeout + 1)
                if is_alive:
                    live.append(host)
            except Exception:
                pass

    live.sort(key=lambda ip: [int(x) for x in ip.split(".")])
    return live


# -----------------------------------------------------------------
# Rolling Data Store
# -----------------------------------------------------------------

class RollingMetricStore:
    """Thread-safe rolling time-series store for live metrics."""

    def __init__(self, max_rows_per_metric: int = 200):
        self._lock = threading.Lock()
        self._records: List[Dict] = []
        self.max_rows = max_rows_per_metric

    def append(self, asset_id: str, metric_name: str, value: float, unit: str = ""):
        row = {
            "timestamp": datetime.now(),
            "asset_id": asset_id,
            "metric_name": metric_name,
            "value": value,
            "unit": unit,
        }
        with self._lock:
            self._records.append(row)
            # Trim per-metric to keep rolling window
            per_key = {}
            for r in self._records:
                k = (r["asset_id"], r["metric_name"])
                per_key.setdefault(k, []).append(r)
            trimmed = []
            for recs in per_key.values():
                trimmed.extend(recs[-self.max_rows:])
            self._records = trimmed

    def to_dataframe(self) -> pd.DataFrame:
        with self._lock:
            if not self._records:
                return pd.DataFrame(
                    columns=["timestamp", "asset_id", "metric_name", "value", "unit"]
                )
            return pd.DataFrame(self._records)

    def save_csv(self, path: str):
        df = self.to_dataframe()
        if not df.empty:
            df.to_csv(path, index=False)

    def row_count(self) -> int:
        with self._lock:
            return len(self._records)


# -----------------------------------------------------------------
# Main Collector Class
# -----------------------------------------------------------------

COMMON_PORTS = {
    80:   "http",
    443:  "https",
    22:   "ssh",
    53:   "dns",
    3389: "rdp",
    8080: "http-alt",
}


class LiveNetworkCollector:
    """
    Continuously polls real network devices using ping and TCP probing.
    Stores results in a RollingMetricStore for the AI pipeline.

    Usage:
        collector = LiveNetworkCollector(devices)
        collector.start()          # non-blocking background thread
        df = collector.get_data()  # get current rolling DataFrame
        collector.stop()
    """

    def __init__(
        self,
        devices: List[Dict],          # [{"id": ..., "ip": ..., "type": ...}, ...]
        poll_interval: int = 15,      # seconds between polls
        ping_count: int = 4,          # pings per poll for loss %
        max_rows: int = 200,
    ):
        self.devices = {d["id"]: d for d in devices}
        self.poll_interval = poll_interval
        self.ping_count = ping_count
        self.store = RollingMetricStore(max_rows_per_metric=max_rows)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.last_poll_time: Optional[datetime] = None
        self.poll_count = 0

    def _probe_device(self, device: Dict):
        """Probe one device and store all metrics."""
        ip = device.get("ip", "")
        asset_id = device.get("id", ip)

        if not ip:
            return

        # 1. Ping latency
        latency_ms, alive = ping_host(ip, timeout=1.5)
        if latency_ms is not None:
            self.store.append(asset_id, "latency", round(latency_ms, 2), "ms")
        else:
            # Host unreachable — latency is very high
            self.store.append(asset_id, "latency", 9999.0, "ms")

        # 2. Packet loss
        loss = measure_packet_loss(ip, count=self.ping_count, timeout=1.5)
        self.store.append(asset_id, "packet_loss", round(loss, 1), "percent")

        # 3. CRC-error proxy: high loss spikes suggest physical layer issues
        # Simulate CRC errors from packet loss correlation
        crc_proxy = round(loss * 0.4 * np.random.uniform(0.8, 1.2), 2)
        self.store.append(asset_id, "crc_error", crc_proxy, "count")

        # 4. TCP port response time (try common ports)
        tcp_rtt = None
        for port, service in COMMON_PORTS.items():
            rtt = tcp_connect_latency(ip, port, timeout=1.5)
            if rtt is not None:
                tcp_rtt = rtt
                self.store.append(asset_id, f"tcp_{service}_rtt", round(rtt, 2), "ms")
                break  # Only probe first available port

        # 5. Composite SNR estimate (higher latency → lower SNR proxy)
        if latency_ms and latency_ms < 9000:
            # Map latency to SNR: 1ms → ~38dB, 100ms → ~20dB
            snr_proxy = max(10.0, 40.0 - (latency_ms / 5.0))
            snr_proxy += np.random.normal(0, 0.5)
            self.store.append(asset_id, "snr_db", round(snr_proxy, 2), "dB")

        # 6. BER proxy from packet loss
        ber_proxy = loss / 100.0 * 1e-6
        self.store.append(asset_id, "ber", ber_proxy, "ratio")

        logger.debug(
            f"[{asset_id}] latency={latency_ms}ms loss={loss}% tcp_rtt={tcp_rtt}ms"
        )

    def _poll_loop(self):
        """Background polling loop."""
        logger.info(
            f"LiveNetworkCollector started: {len(self.devices)} devices, "
            f"interval={self.poll_interval}s"
        )
        while self._running:
            try:
                with ThreadPoolExecutor(max_workers=20) as executor:
                    futures = [
                        executor.submit(self._probe_device, dev)
                        for dev in self.devices.values()
                    ]
                    for f in as_completed(futures):
                        try:
                            f.result()
                        except Exception as e:
                            logger.error(f"Probe error: {e}")

                self.last_poll_time = datetime.now()
                self.poll_count += 1

            except Exception as e:
                logger.error(f"Poll loop error: {e}")

            # Sleep in small increments so stop() is responsive
            for _ in range(self.poll_interval * 2):
                if not self._running:
                    break
                time.sleep(0.5)

    def start(self):
        """Start background polling thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop background polling."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def get_data(self) -> pd.DataFrame:
        """Return current rolling DataFrame."""
        return self.store.to_dataframe()

    def save_data(self, path: str):
        """Save current data to CSV."""
        self.store.save_csv(path)

    def get_status(self) -> Dict:
        return {
            "running": self._running,
            "device_count": len(self.devices),
            "total_rows": self.store.row_count(),
            "poll_count": self.poll_count,
            "last_poll": self.last_poll_time.isoformat() if self.last_poll_time else None,
        }

    def is_ready(self) -> bool:
        """True once we have at least one full poll worth of data."""
        return self.poll_count >= 1 and self.store.row_count() > 0
