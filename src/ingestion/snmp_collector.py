"""
SNMP v3 Data Collector

Collects metrics from network devices using SNMP v3 protocol.
Supports authentication (MD5/SHA) and encryption (DES/AES).
"""

from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime
import asyncio
import logging

from pysnmp.hlapi import *
from pysnmp.entity.rfc3413.oneliner import cmdgen
from pysnmp.proto import rfc1902

logger = logging.getLogger(__name__)


@dataclass
class SNMPDevice:
    """SNMP device configuration"""
    device_id: str
    ip_address: str
    port: int = 161
    # SNMPv3 authentication
    username: str = ''
    auth_protocol: str = 'MD5'  # MD5 or SHA
    auth_password: str = ''
    # SNMPv3 encryption
    priv_protocol: str = 'DES'  # DES or AES
    priv_password: str = ''
    # Polling configuration
    poll_interval: int = 60  # seconds
    timeout: int = 5
    retries: int = 3


@dataclass
class SNMPMetric:
    """SNMP metric result"""
    device_id: str
    metric_name: str
    oid: str
    value: Any
    unit: str
    timestamp: datetime
    tags: Dict[str, Any]


class SNMPv3Collector:
    """
    SNMP v3 data collector with parallel polling
    
    Features:
    - SNMPv3 authentication and encryption
    - Parallel device polling
    - MIB parsing
    - Automatic retry on failure
    - Metric normalization
    """
    
    # Standard OIDs for network metrics
    STANDARD_OIDS = {
        # System information
        'sysDescr': '1.3.6.1.2.1.1.1.0',
        'sysUpTime': '1.3.6.1.2.1.1.3.0',
        'sysName': '1.3.6.1.2.1.1.5.0',
        
        # Interface statistics (ifTable)
        'ifNumber': '1.3.6.1.2.1.2.1.0',
        'ifDescr': '1.3.6.1.2.1.2.2.1.2',
        'ifType': '1.3.6.1.2.1.2.2.1.3',
        'ifSpeed': '1.3.6.1.2.1.2.2.1.5',
        'ifAdminStatus': '1.3.6.1.2.1.2.2.1.7',
        'ifOperStatus': '1.3.6.1.2.1.2.2.1.8',
        'ifInOctets': '1.3.6.1.2.1.2.2.1.10',
        'ifOutOctets': '1.3.6.1.2.1.2.2.1.16',
        'ifInErrors': '1.3.6.1.2.1.2.2.1.14',
        'ifOutErrors': '1.3.6.1.2.1.2.2.1.20',
        
        # Extended interface statistics (ifXTable)
        'ifHCInOctets': '1.3.6.1.2.1.31.1.1.1.6',
        'ifHCOutOctets': '1.3.6.1.2.1.31.1.1.1.10',
        'ifHighSpeed': '1.3.6.1.2.1.31.1.1.1.15',
        
        # IP statistics
        'ipInReceives': '1.3.6.1.2.1.4.3.0',
        'ipInDelivers': '1.3.6.1.2.1.4.9.0',
        'ipOutRequests': '1.3.6.1.2.1.4.10.0',
        
        # TCP statistics
        'tcpActiveOpens': '1.3.6.1.2.1.6.5.0',
        'tcpPassiveOpens': '1.3.6.1.2.1.6.6.0',
        'tcpCurrEstab': '1.3.6.1.2.1.6.9.0',
        
        # UDP statistics
        'udpInDatagrams': '1.3.6.1.2.1.7.1.0',
        'udpOutDatagrams': '1.3.6.1.2.1.7.4.0',
    }
    
    def __init__(self, devices: List[SNMPDevice]):
        """
        Initialize SNMP collector
        
        Args:
            devices: List of SNMP devices to poll
        """
        self.devices = {d.device_id: d for d in devices}
        self.running = False
        self.tasks = []
    
    def _get_auth_protocol(self, protocol: str):
        """Get pysnmp auth protocol object"""
        protocols = {
            'MD5': usmHMACMD5AuthProtocol,
            'SHA': usmHMACSHAAuthProtocol,
            'SHA224': usmHMAC128SHA224AuthProtocol,
            'SHA256': usmHMAC192SHA256AuthProtocol,
            'SHA384': usmHMAC256SHA384AuthProtocol,
            'SHA512': usmHMAC384SHA512AuthProtocol,
        }
        return protocols.get(protocol.upper(), usmHMACMD5AuthProtocol)
    
    def _get_priv_protocol(self, protocol: str):
        """Get pysnmp privacy protocol object"""
        protocols = {
            'DES': usmDESPrivProtocol,
            'AES': usmAesCfb128Protocol,
            'AES128': usmAesCfb128Protocol,
            'AES192': usmAesCfb192Protocol,
            'AES256': usmAesCfb256Protocol,
        }
        return protocols.get(protocol.upper(), usmDESPrivProtocol)
    
    async def poll_device(self, device: SNMPDevice, oids: List[str]) -> List[SNMPMetric]:
        """
        Poll a single device for specified OIDs
        
        Args:
            device: SNMP device configuration
            oids: List of OIDs to query
        
        Returns:
            List of SNMP metrics
        """
        metrics = []
        timestamp = datetime.utcnow()
        
        try:
            # Create SNMP engine
            iterator = getCmd(
                SnmpEngine(),
                UsmUserData(
                    device.username,
                    device.auth_password,
                    device.priv_password,
                    authProtocol=self._get_auth_protocol(device.auth_protocol),
                    privProtocol=self._get_priv_protocol(device.priv_protocol)
                ),
                UdpTransportTarget(
                    (device.ip_address, device.port),
                    timeout=device.timeout,
                    retries=device.retries
                ),
                ContextData(),
                *[ObjectType(ObjectIdentity(oid)) for oid in oids]
            )
            
            # Execute query
            errorIndication, errorStatus, errorIndex, varBinds = next(iterator)
            
            if errorIndication:
                logger.error(f"SNMP error for {device.device_id}: {errorIndication}")
                return metrics
            
            if errorStatus:
                logger.error(
                    f"SNMP error for {device.device_id}: {errorStatus.prettyPrint()} "
                    f"at {errorIndex and varBinds[int(errorIndex) - 1][0] or '?'}"
                )
                return metrics
            
            # Parse results
            for oid, value in varBinds:
                metric_name = self._oid_to_metric_name(str(oid))
                normalized_value, unit = self._normalize_value(value)
                
                metric = SNMPMetric(
                    device_id=device.device_id,
                    metric_name=metric_name,
                    oid=str(oid),
                    value=normalized_value,
                    unit=unit,
                    timestamp=timestamp,
                    tags={'source': 'snmp', 'ip': device.ip_address}
                )
                metrics.append(metric)
            
            logger.debug(f"Collected {len(metrics)} metrics from {device.device_id}")
            
        except Exception as e:
            logger.error(f"Error polling {device.device_id}: {e}")
        
        return metrics
    
    async def poll_interface_table(self, device: SNMPDevice) -> List[SNMPMetric]:
        """
        Poll interface table (ifTable) for all interfaces
        
        Args:
            device: SNMP device configuration
        
        Returns:
            List of interface metrics
        """
        metrics = []
        timestamp = datetime.utcnow()
        
        try:
            # Walk ifTable to get all interfaces
            iterator = nextCmd(
                SnmpEngine(),
                UsmUserData(
                    device.username,
                    device.auth_password,
                    device.priv_password,
                    authProtocol=self._get_auth_protocol(device.auth_protocol),
                    privProtocol=self._get_priv_protocol(device.priv_protocol)
                ),
                UdpTransportTarget(
                    (device.ip_address, device.port),
                    timeout=device.timeout,
                    retries=device.retries
                ),
                ContextData(),
                ObjectType(ObjectIdentity('IF-MIB', 'ifDescr')),
                ObjectType(ObjectIdentity('IF-MIB', 'ifOperStatus')),
                ObjectType(ObjectIdentity('IF-MIB', 'ifInOctets')),
                ObjectType(ObjectIdentity('IF-MIB', 'ifOutOctets')),
                ObjectType(ObjectIdentity('IF-MIB', 'ifInErrors')),
                ObjectType(ObjectIdentity('IF-MIB', 'ifOutErrors')),
                lexicographicMode=False
            )
            
            for errorIndication, errorStatus, errorIndex, varBinds in iterator:
                if errorIndication or errorStatus:
                    break
                
                # Extract interface index from OID
                if_index = str(varBinds[0][0]).split('.')[-1]
                
                # Parse interface metrics
                if_descr = str(varBinds[0][1])
                if_oper_status = int(varBinds[1][1])
                if_in_octets = int(varBinds[2][1])
                if_out_octets = int(varBinds[3][1])
                if_in_errors = int(varBinds[4][1])
                if_out_errors = int(varBinds[5][1])
                
                # Create metrics for this interface
                interface_metrics = [
                    SNMPMetric(
                        device_id=device.device_id,
                        metric_name=f'interface_{if_index}_oper_status',
                        oid=str(varBinds[1][0]),
                        value=if_oper_status,
                        unit='status',
                        timestamp=timestamp,
                        tags={
                            'source': 'snmp',
                            'interface': if_descr,
                            'if_index': if_index
                        }
                    ),
                    SNMPMetric(
                        device_id=device.device_id,
                        metric_name=f'interface_{if_index}_in_octets',
                        oid=str(varBinds[2][0]),
                        value=if_in_octets,
                        unit='bytes',
                        timestamp=timestamp,
                        tags={
                            'source': 'snmp',
                            'interface': if_descr,
                            'if_index': if_index
                        }
                    ),
                    SNMPMetric(
                        device_id=device.device_id,
                        metric_name=f'interface_{if_index}_out_octets',
                        oid=str(varBinds[3][0]),
                        value=if_out_octets,
                        unit='bytes',
                        timestamp=timestamp,
                        tags={
                            'source': 'snmp',
                            'interface': if_descr,
                            'if_index': if_index
                        }
                    ),
                    SNMPMetric(
                        device_id=device.device_id,
                        metric_name=f'interface_{if_index}_in_errors',
                        oid=str(varBinds[4][0]),
                        value=if_in_errors,
                        unit='count',
                        timestamp=timestamp,
                        tags={
                            'source': 'snmp',
                            'interface': if_descr,
                            'if_index': if_index
                        }
                    ),
                    SNMPMetric(
                        device_id=device.device_id,
                        metric_name=f'interface_{if_index}_out_errors',
                        oid=str(varBinds[5][0]),
                        value=if_out_errors,
                        unit='count',
                        timestamp=timestamp,
                        tags={
                            'source': 'snmp',
                            'interface': if_descr,
                            'if_index': if_index
                        }
                    ),
                ]
                
                metrics.extend(interface_metrics)
            
            logger.debug(f"Collected {len(metrics)} interface metrics from {device.device_id}")
            
        except Exception as e:
            logger.error(f"Error polling interface table for {device.device_id}: {e}")
        
        return metrics
    
    async def collect_all_metrics(self, device_id: str) -> List[SNMPMetric]:
        """
        Collect all standard metrics from a device
        
        Args:
            device_id: Device ID
        
        Returns:
            List of all metrics
        """
        device = self.devices.get(device_id)
        if not device:
            logger.error(f"Device {device_id} not found")
            return []
        
        # Collect system metrics
        system_oids = [
            self.STANDARD_OIDS['sysUpTime'],
            self.STANDARD_OIDS['ipInReceives'],
            self.STANDARD_OIDS['ipOutRequests'],
            self.STANDARD_OIDS['tcpCurrEstab'],
        ]
        
        system_metrics = await self.poll_device(device, system_oids)
        
        # Collect interface metrics
        interface_metrics = await self.poll_interface_table(device)
        
        return system_metrics + interface_metrics
    
    async def poll_all_devices(self) -> Dict[str, List[SNMPMetric]]:
        """
        Poll all configured devices in parallel
        
        Returns:
            Dictionary mapping device_id to list of metrics
        """
        tasks = [
            self.collect_all_metrics(device_id)
            for device_id in self.devices.keys()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        metrics_by_device = {}
        for device_id, result in zip(self.devices.keys(), results):
            if isinstance(result, Exception):
                logger.error(f"Error collecting from {device_id}: {result}")
                metrics_by_device[device_id] = []
            else:
                metrics_by_device[device_id] = result
        
        return metrics_by_device
    
    def _oid_to_metric_name(self, oid: str) -> str:
        """Convert OID to human-readable metric name"""
        # Reverse lookup in STANDARD_OIDS
        for name, standard_oid in self.STANDARD_OIDS.items():
            if oid.startswith(standard_oid):
                return name
        
        # If not found, use OID as name
        return f"oid_{oid.replace('.', '_')}"
    
    def _normalize_value(self, value) -> Tuple[Any, str]:
        """
        Normalize SNMP value and determine unit
        
        Args:
            value: SNMP value object
        
        Returns:
            Tuple of (normalized_value, unit)
        """
        # Counter32/Counter64
        if isinstance(value, (rfc1902.Counter32, rfc1902.Counter64)):
            return int(value), 'count'
        
        # Gauge32
        if isinstance(value, rfc1902.Gauge32):
            return int(value), 'gauge'
        
        # TimeTicks (convert to seconds)
        if isinstance(value, rfc1902.TimeTicks):
            return int(value) / 100.0, 'seconds'
        
        # Integer
        if isinstance(value, (rfc1902.Integer, rfc1902.Integer32)):
            return int(value), 'integer'
        
        # String
        if isinstance(value, rfc1902.OctetString):
            try:
                return str(value), 'string'
            except:
                return value.hexValue, 'hex'
        
        # Default
        return str(value), 'unknown'
    
    async def start_polling(self, callback=None):
        """
        Start continuous polling of all devices
        
        Args:
            callback: Optional callback function(device_id, metrics)
        """
        self.running = True
        logger.info(f"Starting SNMP polling for {len(self.devices)} devices")
        
        while self.running:
            try:
                # Poll all devices
                metrics_by_device = await self.poll_all_devices()
                
                # Call callback if provided
                if callback:
                    for device_id, metrics in metrics_by_device.items():
                        if metrics:
                            await callback(device_id, metrics)
                
                # Wait for next poll interval (use minimum interval)
                min_interval = min(d.poll_interval for d in self.devices.values())
                await asyncio.sleep(min_interval)
                
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                await asyncio.sleep(5)  # Wait before retry
    
    def stop_polling(self):
        """Stop continuous polling"""
        self.running = False
        logger.info("Stopping SNMP polling")
