"""
Modbus TCP Data Collector

Collects data from Modbus TCP devices (PLCs, sensors, actuators).
"""

from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import asyncio
import logging

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

logger = logging.getLogger(__name__)


@dataclass
class ModbusDevice:
    """Modbus TCP device configuration"""
    device_id: str
    ip_address: str
    port: int = 502
    unit_id: int = 1  # Modbus slave ID
    poll_interval: int = 5  # seconds
    timeout: int = 3
    retries: int = 3


@dataclass
class ModbusRegisterMap:
    """Modbus register mapping configuration"""
    metric_name: str
    function_code: int  # 3=holding, 4=input, 1=coil, 2=discrete
    address: int
    count: int = 1
    data_type: str = 'uint16'  # uint16, int16, uint32, int32, float32, etc.
    scale: float = 1.0
    offset: float = 0.0
    unit: str = ''


@dataclass
class ModbusMetric:
    """Modbus metric result"""
    device_id: str
    metric_name: str
    address: int
    value: Any
    unit: str
    timestamp: datetime
    tags: Dict[str, Any]


class ModbusTCPCollector:
    """
    Modbus TCP data collector
    
    Features:
    - Async Modbus TCP client
    - Support for all function codes
    - Register-to-metric mapping
    - Data type conversion
    - Scaling and offset
    - Connection pooling
    """
    
    def __init__(
        self,
        devices: List[ModbusDevice],
        register_maps: Dict[str, List[ModbusRegisterMap]]
    ):
        """
        Initialize Modbus collector
        
        Args:
            devices: List of Modbus devices
            register_maps: Mapping of device_id to register configurations
        """
        self.devices = {d.device_id: d for d in devices}
        self.register_maps = register_maps
        self.clients: Dict[str, AsyncModbusTcpClient] = {}
        self.running = False
    
    async def connect_device(self, device: ModbusDevice) -> bool:
        """
        Connect to a Modbus device
        
        Args:
            device: Modbus device configuration
        
        Returns:
            True if connected successfully
        """
        try:
            client = AsyncModbusTcpClient(
                host=device.ip_address,
                port=device.port,
                timeout=device.timeout,
                retries=device.retries
            )
            
            await client.connect()
            
            if client.connected:
                self.clients[device.device_id] = client
                logger.info(f"Connected to Modbus device {device.device_id} at {device.ip_address}")
                return True
            else:
                logger.error(f"Failed to connect to {device.device_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error connecting to {device.device_id}: {e}")
            return False
    
    async def disconnect_device(self, device_id: str):
        """Disconnect from a Modbus device"""
        if device_id in self.clients:
            client = self.clients[device_id]
            client.close()
            del self.clients[device_id]
            logger.info(f"Disconnected from {device_id}")
    
    async def read_register(
        self,
        device_id: str,
        register_map: ModbusRegisterMap
    ) -> Optional[ModbusMetric]:
        """
        Read a single register from device
        
        Args:
            device_id: Device ID
            register_map: Register mapping configuration
        
        Returns:
            ModbusMetric or None if error
        """
        client = self.clients.get(device_id)
        if not client or not client.connected:
            logger.error(f"Device {device_id} not connected")
            return None
        
        device = self.devices[device_id]
        timestamp = datetime.utcnow()
        
        try:
            # Read based on function code
            if register_map.function_code == 3:  # Read holding registers
                result = await client.read_holding_registers(
                    address=register_map.address,
                    count=register_map.count,
                    slave=device.unit_id
                )
            elif register_map.function_code == 4:  # Read input registers
                result = await client.read_input_registers(
                    address=register_map.address,
                    count=register_map.count,
                    slave=device.unit_id
                )
            elif register_map.function_code == 1:  # Read coils
                result = await client.read_coils(
                    address=register_map.address,
                    count=register_map.count,
                    slave=device.unit_id
                )
            elif register_map.function_code == 2:  # Read discrete inputs
                result = await client.read_discrete_inputs(
                    address=register_map.address,
                    count=register_map.count,
                    slave=device.unit_id
                )
            else:
                logger.error(f"Unsupported function code: {register_map.function_code}")
                return None
            
            if result.isError():
                logger.error(f"Modbus error reading {register_map.metric_name}: {result}")
                return None
            
            # Convert raw value to typed value
            raw_value = result.registers if hasattr(result, 'registers') else result.bits
            typed_value = self._convert_value(raw_value, register_map.data_type)
            
            # Apply scaling and offset
            scaled_value = (typed_value * register_map.scale) + register_map.offset
            
            metric = ModbusMetric(
                device_id=device_id,
                metric_name=register_map.metric_name,
                address=register_map.address,
                value=scaled_value,
                unit=register_map.unit,
                timestamp=timestamp,
                tags={
                    'source': 'modbus',
                    'function_code': register_map.function_code,
                    'data_type': register_map.data_type
                }
            )
            
            return metric
            
        except ModbusException as e:
            logger.error(f"Modbus exception reading {register_map.metric_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error reading {register_map.metric_name}: {e}")
            return None
    
    async def collect_device_metrics(self, device_id: str) -> List[ModbusMetric]:
        """
        Collect all configured metrics from a device
        
        Args:
            device_id: Device ID
        
        Returns:
            List of metrics
        """
        register_maps = self.register_maps.get(device_id, [])
        if not register_maps:
            logger.warning(f"No register maps configured for {device_id}")
            return []
        
        # Read all registers
        tasks = [
            self.read_register(device_id, reg_map)
            for reg_map in register_maps
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out None and exceptions
        metrics = [
            r for r in results
            if r is not None and not isinstance(r, Exception)
        ]
        
        logger.debug(f"Collected {len(metrics)} metrics from {device_id}")
        return metrics
    
    async def poll_all_devices(self) -> Dict[str, List[ModbusMetric]]:
        """
        Poll all configured devices
        
        Returns:
            Dictionary mapping device_id to metrics
        """
        tasks = [
            self.collect_device_metrics(device_id)
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
    
    async def start_polling(self, callback=None):
        """
        Start continuous polling
        
        Args:
            callback: Optional callback function(device_id, metrics)
        """
        # Connect to all devices
        for device in self.devices.values():
            await self.connect_device(device)
        
        self.running = True
        logger.info(f"Starting Modbus polling for {len(self.devices)} devices")
        
        while self.running:
            try:
                # Poll all devices
                metrics_by_device = await self.poll_all_devices()
                
                # Call callback if provided
                if callback:
                    for device_id, metrics in metrics_by_device.items():
                        if metrics:
                            await callback(device_id, metrics)
                
                # Wait for next poll interval
                min_interval = min(d.poll_interval for d in self.devices.values())
                await asyncio.sleep(min_interval)
                
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                await asyncio.sleep(5)
    
    async def stop_polling(self):
        """Stop polling and disconnect all devices"""
        self.running = False
        
        # Disconnect all devices
        for device_id in list(self.clients.keys()):
            await self.disconnect_device(device_id)
        
        logger.info("Stopped Modbus polling")
    
    def _convert_value(self, raw_value: Any, data_type: str) -> Any:
        """
        Convert raw Modbus value to typed value
        
        Args:
            raw_value: Raw register value(s)
            data_type: Target data type
        
        Returns:
            Converted value
        """
        if data_type == 'uint16':
            return int(raw_value[0]) if isinstance(raw_value, list) else int(raw_value)
        
        elif data_type == 'int16':
            val = int(raw_value[0]) if isinstance(raw_value, list) else int(raw_value)
            # Convert to signed
            return val if val < 32768 else val - 65536
        
        elif data_type == 'uint32':
            if len(raw_value) < 2:
                return 0
            return (raw_value[0] << 16) | raw_value[1]
        
        elif data_type == 'int32':
            if len(raw_value) < 2:
                return 0
            val = (raw_value[0] << 16) | raw_value[1]
            # Convert to signed
            return val if val < 2147483648 else val - 4294967296
        
        elif data_type == 'float32':
            if len(raw_value) < 2:
                return 0.0
            # IEEE 754 float conversion
            import struct
            bytes_val = struct.pack('>HH', raw_value[0], raw_value[1])
            return struct.unpack('>f', bytes_val)[0]
        
        elif data_type == 'bool':
            return bool(raw_value[0] if isinstance(raw_value, list) else raw_value)
        
        else:
            logger.warning(f"Unknown data type: {data_type}, returning raw value")
            return raw_value
