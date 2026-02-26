"""Ingestion package initialization — optional protocol collectors."""

# SNMP v3 collector (requires pysnmp)
try:
    from src.ingestion.snmp_collector import SNMPv3Collector, SNMPDevice, SNMPMetric
    _snmp_available = True
except ImportError:
    _snmp_available = False

# Modbus TCP collector (requires pymodbus)
try:
    from src.ingestion.modbus_collector import (
        ModbusTCPCollector,
        ModbusDevice,
        ModbusRegisterMap,
        ModbusMetric,
    )
    _modbus_available = True
except ImportError:
    _modbus_available = False

# Profinet collector (requires scapy / custom libs)
try:
    from src.ingestion.profinet_collector import (
        ProfinetDCPCollector,
        ProfinetDevice,
        ProfinetMetric,
    )
    _profinet_available = True
except ImportError:
    _profinet_available = False

# Live collector (always available — uses only stdlib + numpy/pandas)
from src.ingestion.live_collector import LiveNetworkCollector, scan_subnet, ping_host

__all__ = [
    "LiveNetworkCollector",
    "scan_subnet",
    "ping_host",
]
