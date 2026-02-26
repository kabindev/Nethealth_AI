"""
Profinet DCP (Discovery and Configuration Protocol) Collector

Collects data from Profinet devices using DCP protocol.
Supports device discovery, identification, and parameter reading.
"""

from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import asyncio
import logging
import socket
import struct

from scapy.all import Ether, Raw, sendp, sniff, conf

logger = logging.getLogger(__name__)


@dataclass
class ProfinetDevice:
    """Profinet device information"""
    device_id: str
    mac_address: str
    ip_address: Optional[str] = None
    station_name: Optional[str] = None
    device_type: Optional[str] = None
    vendor_id: Optional[int] = None
    device_id_number: Optional[int] = None
    device_role: Optional[str] = None
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None


@dataclass
class ProfinetMetric:
    """Profinet metric result"""
    device_id: str
    metric_name: str
    value: Any
    unit: str
    timestamp: datetime
    tags: Dict[str, Any]


class ProfinetDCPCollector:
    """
    Profinet DCP data collector
    
    Features:
    - Device discovery via DCP multicast
    - Station name resolution
    - Parameter reading (DCP Get)
    - Diagnostic data extraction
    - Topology discovery
    
    DCP Protocol:
    - EtherType: 0x8892
    - Multicast MAC: 01:0E:CF:00:00:00
    - Service IDs: Identify (5), Get (3), Set (4)
    """
    
    # DCP Protocol Constants
    DCP_ETHERTYPE = 0x8892
    DCP_MULTICAST_MAC = "01:0e:cf:00:00:00"
    
    # Service IDs
    DCP_SERVICE_IDENTIFY = 5
    DCP_SERVICE_GET = 3
    DCP_SERVICE_SET = 4
    
    # Option IDs
    DCP_OPTION_IP = 0x01
    DCP_OPTION_DEVICE_PROPERTIES = 0x02
    DCP_OPTION_DEVICE_INITIATIVE = 0x06
    
    # Suboption IDs
    DCP_SUBOPTION_MAC = 0x01
    DCP_SUBOPTION_IP_PARAMETER = 0x02
    DCP_SUBOPTION_DEVICE_VENDOR = 0x01
    DCP_SUBOPTION_DEVICE_NAME = 0x02
    DCP_SUBOPTION_DEVICE_ID = 0x03
    DCP_SUBOPTION_DEVICE_ROLE = 0x04
    
    def __init__(self, interface: str = None):
        """
        Initialize Profinet DCP collector
        
        Args:
            interface: Network interface to use (e.g., 'eth0', 'en0')
        """
        self.interface = interface or conf.iface
        self.devices: Dict[str, ProfinetDevice] = {}
        self.running = False
        self.xid = 0  # Transaction ID counter
    
    def _build_dcp_identify_request(self) -> bytes:
        """
        Build DCP Identify request packet
        
        Returns:
            Raw DCP packet bytes
        """
        self.xid = (self.xid + 1) & 0xFFFFFFFF
        
        # DCP Header
        # Service ID: Identify (5), Service Type: Request (0)
        service_id = self.DCP_SERVICE_IDENTIFY
        service_type = 0
        xid = self.xid
        response_delay = 0
        dcp_data_length = 4  # Just the "Identify All" option
        
        dcp_header = struct.pack(
            '>BBHHI',
            service_id,
            service_type,
            xid & 0xFFFF,
            response_delay,
            dcp_data_length
        )
        
        # DCP Block: Identify All
        option = 0xFF  # All options
        suboption = 0xFF  # All suboptions
        block_length = 0
        
        dcp_block = struct.pack(
            '>BBH',
            option,
            suboption,
            block_length
        )
        
        return dcp_header + dcp_block
    
    def _build_dcp_get_request(self, option: int, suboption: int) -> bytes:
        """
        Build DCP Get request packet
        
        Args:
            option: DCP option ID
            suboption: DCP suboption ID
        
        Returns:
            Raw DCP packet bytes
        """
        self.xid = (self.xid + 1) & 0xFFFFFFFF
        
        # DCP Header
        service_id = self.DCP_SERVICE_GET
        service_type = 0
        xid = self.xid
        response_delay = 0
        dcp_data_length = 4
        
        dcp_header = struct.pack(
            '>BBHHI',
            service_id,
            service_type,
            xid & 0xFFFF,
            response_delay,
            dcp_data_length
        )
        
        # DCP Block
        block_length = 0
        dcp_block = struct.pack(
            '>BBH',
            option,
            suboption,
            block_length
        )
        
        return dcp_header + dcp_block
    
    def _parse_dcp_response(self, packet) -> Optional[ProfinetDevice]:
        """
        Parse DCP response packet
        
        Args:
            packet: Scapy packet
        
        Returns:
            ProfinetDevice or None
        """
        try:
            if not packet.haslayer(Ether):
                return None
            
            # Check EtherType
            if packet[Ether].type != self.DCP_ETHERTYPE:
                return None
            
            # Extract raw payload
            if not packet.haslayer(Raw):
                return None
            
            payload = bytes(packet[Raw].load)
            
            # Parse DCP header
            if len(payload) < 10:
                return None
            
            service_id = payload[0]
            service_type = payload[1]
            xid = struct.unpack('>H', payload[2:4])[0]
            response_delay = struct.unpack('>H', payload[4:6])[0]
            dcp_data_length = struct.unpack('>I', payload[6:10])[0]
            
            # Only process responses
            if service_type != 1:  # 1 = Response
                return None
            
            # Parse DCP blocks
            device = ProfinetDevice(
                device_id=packet[Ether].src,
                mac_address=packet[Ether].src,
                last_seen=datetime.utcnow()
            )
            
            offset = 10
            while offset < len(payload):
                if offset + 4 > len(payload):
                    break
                
                option = payload[offset]
                suboption = payload[offset + 1]
                block_length = struct.unpack('>H', payload[offset + 2:offset + 4])[0]
                
                block_data_start = offset + 4
                block_data_end = block_data_start + block_length
                
                if block_data_end > len(payload):
                    break
                
                block_data = payload[block_data_start:block_data_end]
                
                # Parse based on option/suboption
                if option == self.DCP_OPTION_IP and suboption == self.DCP_SUBOPTION_IP_PARAMETER:
                    # IP address (4 bytes), Netmask (4 bytes), Gateway (4 bytes)
                    if len(block_data) >= 12:
                        ip_bytes = block_data[0:4]
                        device.ip_address = '.'.join(str(b) for b in ip_bytes)
                
                elif option == self.DCP_OPTION_DEVICE_PROPERTIES and suboption == self.DCP_SUBOPTION_DEVICE_NAME:
                    # Station name (string)
                    try:
                        device.station_name = block_data.decode('utf-8').rstrip('\x00')
                    except:
                        pass
                
                elif option == self.DCP_OPTION_DEVICE_PROPERTIES and suboption == self.DCP_SUBOPTION_DEVICE_VENDOR:
                    # Vendor ID (2 bytes), Device ID (2 bytes)
                    if len(block_data) >= 4:
                        device.vendor_id = struct.unpack('>H', block_data[0:2])[0]
                        device.device_id_number = struct.unpack('>H', block_data[2:4])[0]
                
                elif option == self.DCP_OPTION_DEVICE_PROPERTIES and suboption == self.DCP_SUBOPTION_DEVICE_ROLE:
                    # Device role (1 byte)
                    if len(block_data) >= 1:
                        role_byte = block_data[0]
                        roles = []
                        if role_byte & 0x01:
                            roles.append('IO-Device')
                        if role_byte & 0x02:
                            roles.append('IO-Controller')
                        if role_byte & 0x04:
                            roles.append('IO-Supervisor')
                        device.device_role = ','.join(roles) if roles else 'Unknown'
                
                # Move to next block (align to 2-byte boundary)
                offset = block_data_end
                if block_length % 2 != 0:
                    offset += 1
            
            return device
            
        except Exception as e:
            logger.error(f"Error parsing DCP response: {e}")
            return None
    
    async def discover_devices(self, timeout: int = 5) -> List[ProfinetDevice]:
        """
        Discover Profinet devices on the network
        
        Args:
            timeout: Discovery timeout in seconds
        
        Returns:
            List of discovered devices
        """
        logger.info(f"Starting Profinet device discovery on {self.interface}")
        
        # Build and send DCP Identify request
        dcp_payload = self._build_dcp_identify_request()
        
        packet = Ether(
            dst=self.DCP_MULTICAST_MAC,
            type=self.DCP_ETHERTYPE
        ) / Raw(load=dcp_payload)
        
        # Send request
        sendp(packet, iface=self.interface, verbose=False)
        
        # Sniff for responses
        discovered = []
        
        def packet_handler(pkt):
            device = self._parse_dcp_response(pkt)
            if device:
                # Update or add device
                if device.mac_address not in self.devices:
                    device.first_seen = datetime.utcnow()
                    self.devices[device.mac_address] = device
                else:
                    # Update existing device
                    existing = self.devices[device.mac_address]
                    if device.ip_address:
                        existing.ip_address = device.ip_address
                    if device.station_name:
                        existing.station_name = device.station_name
                    if device.vendor_id:
                        existing.vendor_id = device.vendor_id
                    if device.device_id_number:
                        existing.device_id_number = device.device_id_number
                    if device.device_role:
                        existing.device_role = device.device_role
                    existing.last_seen = datetime.utcnow()
                    device = existing
                
                discovered.append(device)
                logger.info(
                    f"Discovered Profinet device: {device.station_name or device.mac_address} "
                    f"({device.ip_address or 'no IP'})"
                )
        
        # Sniff with timeout
        sniff(
            iface=self.interface,
            filter=f"ether proto 0x8892",
            prn=packet_handler,
            timeout=timeout,
            store=False
        )
        
        logger.info(f"Discovery complete. Found {len(discovered)} devices")
        return discovered
    
    async def collect_device_metrics(self, device: ProfinetDevice) -> List[ProfinetMetric]:
        """
        Collect metrics from a Profinet device
        
        Args:
            device: Profinet device
        
        Returns:
            List of metrics
        """
        metrics = []
        timestamp = datetime.utcnow()
        
        # Basic device status metrics
        metrics.append(ProfinetMetric(
            device_id=device.device_id,
            metric_name='device_status',
            value=1 if device.last_seen and (datetime.utcnow() - device.last_seen).seconds < 60 else 0,
            unit='status',
            timestamp=timestamp,
            tags={
                'source': 'profinet',
                'station_name': device.station_name,
                'device_role': device.device_role
            }
        ))
        
        if device.vendor_id:
            metrics.append(ProfinetMetric(
                device_id=device.device_id,
                metric_name='vendor_id',
                value=device.vendor_id,
                unit='id',
                timestamp=timestamp,
                tags={'source': 'profinet'}
            ))
        
        if device.device_id_number:
            metrics.append(ProfinetMetric(
                device_id=device.device_id,
                metric_name='device_id_number',
                value=device.device_id_number,
                unit='id',
                timestamp=timestamp,
                tags={'source': 'profinet'}
            ))
        
        return metrics
    
    async def poll_all_devices(self) -> Dict[str, List[ProfinetMetric]]:
        """
        Poll all discovered devices
        
        Returns:
            Dictionary mapping device_id to metrics
        """
        metrics_by_device = {}
        
        for device in self.devices.values():
            metrics = await self.collect_device_metrics(device)
            metrics_by_device[device.device_id] = metrics
        
        return metrics_by_device
    
    async def start_polling(self, discovery_interval: int = 300, callback=None):
        """
        Start continuous polling with periodic discovery
        
        Args:
            discovery_interval: Device discovery interval in seconds
            callback: Optional callback function(device_id, metrics)
        """
        self.running = True
        logger.info("Starting Profinet DCP polling")
        
        last_discovery = 0
        
        while self.running:
            try:
                current_time = datetime.utcnow().timestamp()
                
                # Periodic device discovery
                if current_time - last_discovery >= discovery_interval:
                    await self.discover_devices()
                    last_discovery = current_time
                
                # Poll all devices
                metrics_by_device = await self.poll_all_devices()
                
                # Call callback if provided
                if callback:
                    for device_id, metrics in metrics_by_device.items():
                        if metrics:
                            await callback(device_id, metrics)
                
                # Wait before next poll
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                await asyncio.sleep(5)
    
    def stop_polling(self):
        """Stop polling"""
        self.running = False
        logger.info("Stopped Profinet DCP polling")
    
    def get_device_by_name(self, station_name: str) -> Optional[ProfinetDevice]:
        """Get device by station name"""
        for device in self.devices.values():
            if device.station_name == station_name:
                return device
        return None
    
    def get_device_by_mac(self, mac_address: str) -> Optional[ProfinetDevice]:
        """Get device by MAC address"""
        return self.devices.get(mac_address)
