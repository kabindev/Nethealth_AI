"""
Rogue Device Detector

Detects unauthorized devices on the network using:
- MAC address whitelist
- Behavioral fingerprinting
- Traffic pattern anomaly detection
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Set, Optional
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


@dataclass
class RogueDeviceAlert:
    """Alert for detected rogue device"""
    device_id: str
    mac_address: str
    ip_address: Optional[str]
    first_seen: datetime
    reason: str  # 'unknown_mac', 'abnormal_behavior', 'unauthorized_type'
    severity: str  # 'CRITICAL', 'WARNING', 'INFO'
    confidence: float  # 0.0 to 1.0
    behavioral_score: Optional[float] = None
    details: Dict = None


class RogueDeviceDetector:
    """
    Detect unauthorized devices on the network
    
    Methods:
    - MAC whitelist checking
    - Behavioral fingerprinting
    - Traffic pattern anomaly detection
    """
    
    def __init__(
        self,
        whitelist_path: str = 'data/security/mac_whitelist.json',
        behavioral_model_path: Optional[str] = None
    ):
        """
        Initialize rogue device detector
        
        Args:
            whitelist_path: Path to MAC address whitelist
            behavioral_model_path: Path to trained behavioral model
        """
        self.whitelist = self._load_whitelist(whitelist_path)
        self.whitelist_path = Path(whitelist_path)
        
        # Behavioral anomaly detector
        self.behavioral_model = IsolationForest(
            contamination=0.1,  # Expect 10% anomalies
            random_state=42
        )
        self.scaler = StandardScaler()
        self.is_fitted = False
        
        if behavioral_model_path and Path(behavioral_model_path).exists():
            self._load_behavioral_model(behavioral_model_path)
        
        # Device history
        self.device_history: Dict[str, Dict] = {}
    
    def _load_whitelist(self, path: str) -> Set[str]:
        """Load MAC address whitelist"""
        whitelist_file = Path(path)
        
        if whitelist_file.exists():
            with open(whitelist_file, 'r') as f:
                data = json.load(f)
                return set(data.get('allowed_macs', []))
        else:
            # Create default whitelist
            print(f"[WARNING] Whitelist not found at {path}, creating default")
            default_whitelist = {
                'allowed_macs': [],
                'created': datetime.now().isoformat(),
                'description': 'Authorized MAC addresses'
            }
            whitelist_file.parent.mkdir(parents=True, exist_ok=True)
            with open(whitelist_file, 'w') as f:
                json.dump(default_whitelist, f, indent=2)
            return set()
    
    def add_to_whitelist(self, mac_address: str, description: str = ""):
        """Add MAC address to whitelist"""
        self.whitelist.add(mac_address)
        
        # Update file
        with open(self.whitelist_path, 'r') as f:
            data = json.load(f)
        
        data['allowed_macs'].append(mac_address)
        data['last_updated'] = datetime.now().isoformat()
        
        with open(self.whitelist_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"[OK] Added {mac_address} to whitelist")
    
    def remove_from_whitelist(self, mac_address: str):
        """Remove MAC address from whitelist"""
        self.whitelist.discard(mac_address)
        
        with open(self.whitelist_path, 'r') as f:
            data = json.load(f)
        
        if mac_address in data['allowed_macs']:
            data['allowed_macs'].remove(mac_address)
            data['last_updated'] = datetime.now().isoformat()
            
            with open(self.whitelist_path, 'w') as f:
                json.dump(data, f, indent=2)
    
    def fit_behavioral_model(self, normal_traffic: pd.DataFrame):
        """
        Fit behavioral model on normal traffic patterns
        
        Args:
            normal_traffic: DataFrame with traffic features
        """
        features = self._extract_behavioral_features(normal_traffic)
        
        # Normalize
        features_scaled = self.scaler.fit_transform(features)
        
        # Fit anomaly detector
        self.behavioral_model.fit(features_scaled)
        self.is_fitted = True
        
        print(f"[OK] Fitted behavioral model on {len(features)} samples")
    
    def _extract_behavioral_features(self, traffic_data: pd.DataFrame) -> np.ndarray:
        """
        Extract behavioral features from traffic data
        
        Features:
        - Packet rate (packets/sec)
        - Byte rate (bytes/sec)
        - Protocol distribution
        - Port diversity
        - Connection patterns
        """
        features = []
        
        # Group by device
        for device_id, device_traffic in traffic_data.groupby('device_id'):
            feature_vector = [
                device_traffic['packet_count'].sum() / len(device_traffic),  # Avg packet rate
                device_traffic['byte_count'].sum() / len(device_traffic),    # Avg byte rate
                device_traffic['protocol'].nunique(),                         # Protocol diversity
                device_traffic.get('dst_port', pd.Series([0])).nunique(),    # Port diversity
                device_traffic['connection_count'].mean(),                    # Avg connections
                device_traffic['packet_size'].mean(),                         # Avg packet size
                device_traffic['packet_size'].std(),                          # Packet size variance
                device_traffic['inter_arrival_time'].mean(),                  # Avg inter-arrival
            ]
            features.append(feature_vector)
        
        return np.array(features)
    
    def detect_rogue_devices(
        self,
        observed_devices: List[Dict],
        traffic_data: Optional[pd.DataFrame] = None
    ) -> List[RogueDeviceAlert]:
        """
        Scan for unauthorized devices
        
        Args:
            observed_devices: List of device dicts with 'id', 'mac_address', 'ip_address'
            traffic_data: Optional traffic data for behavioral analysis
        
        Returns:
            List of RogueDeviceAlert objects
        """
        alerts = []
        current_time = datetime.now()
        
        for device in observed_devices:
            device_id = device.get('id')
            mac_address = device.get('mac_address', 'unknown')
            ip_address = device.get('ip_address')
            
            # Track device history
            if device_id not in self.device_history:
                self.device_history[device_id] = {
                    'first_seen': current_time,
                    'last_seen': current_time,
                    'mac_address': mac_address
                }
            else:
                self.device_history[device_id]['last_seen'] = current_time
            
            # Check 1: MAC whitelist
            if mac_address not in self.whitelist:
                alerts.append(RogueDeviceAlert(
                    device_id=device_id,
                    mac_address=mac_address,
                    ip_address=ip_address,
                    first_seen=self.device_history[device_id]['first_seen'],
                    reason='unknown_mac',
                    severity='CRITICAL',
                    confidence=1.0,
                    details={'message': f'MAC address {mac_address} not in whitelist'}
                ))
                continue
            
            # Check 2: Behavioral anomaly (if traffic data provided)
            if traffic_data is not None and self.is_fitted:
                device_traffic = traffic_data[traffic_data['device_id'] == device_id]
                
                if not device_traffic.empty:
                    features = self._extract_behavioral_features(device_traffic)
                    
                    if len(features) > 0:
                        features_scaled = self.scaler.transform(features)
                        anomaly_score = self.behavioral_model.score_samples(features_scaled)[0]
                        
                        # Threshold: -0.5 (lower = more anomalous)
                        if anomaly_score < -0.5:
                            alerts.append(RogueDeviceAlert(
                                device_id=device_id,
                                mac_address=mac_address,
                                ip_address=ip_address,
                                first_seen=self.device_history[device_id]['first_seen'],
                                reason='abnormal_behavior',
                                severity='WARNING',
                                confidence=min(1.0, abs(anomaly_score)),
                                behavioral_score=anomaly_score,
                                details={'message': 'Unusual traffic pattern detected'}
                            ))
        
        return alerts
    
    def get_device_fingerprint(self, device_id: str, traffic_data: pd.DataFrame) -> Dict:
        """
        Generate behavioral fingerprint for a device
        
        Returns:
            Dict with behavioral characteristics
        """
        device_traffic = traffic_data[traffic_data['device_id'] == device_id]
        
        if device_traffic.empty:
            return {}
        
        fingerprint = {
            'device_id': device_id,
            'avg_packet_rate': device_traffic['packet_count'].mean(),
            'avg_byte_rate': device_traffic['byte_count'].mean(),
            'protocol_diversity': device_traffic['protocol'].nunique(),
            'common_protocols': device_traffic['protocol'].value_counts().head(3).to_dict(),
            'avg_packet_size': device_traffic['packet_size'].mean(),
            'connection_pattern': device_traffic['connection_count'].describe().to_dict(),
            'active_hours': device_traffic.groupby('hour')['packet_count'].sum().to_dict()
        }
        
        return fingerprint
    
    def generate_report(self, alerts: List[RogueDeviceAlert]) -> Dict:
        """Generate security report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'total_alerts': len(alerts),
            'critical_alerts': sum(1 for a in alerts if a.severity == 'CRITICAL'),
            'warning_alerts': sum(1 for a in alerts if a.severity == 'WARNING'),
            'alerts_by_reason': {},
            'devices': []
        }
        
        # Group by reason
        for alert in alerts:
            reason = alert.reason
            if reason not in report['alerts_by_reason']:
                report['alerts_by_reason'][reason] = 0
            report['alerts_by_reason'][reason] += 1
            
            report['devices'].append({
                'device_id': alert.device_id,
                'mac_address': alert.mac_address,
                'ip_address': alert.ip_address,
                'reason': alert.reason,
                'severity': alert.severity,
                'confidence': alert.confidence,
                'first_seen': alert.first_seen.isoformat()
            })
        
        return report
