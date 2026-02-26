"""
Configuration Drift Monitor

Monitors and detects configuration changes across network devices.
Tracks configuration history and alerts on unauthorized changes.
"""

import json
import hashlib
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
import difflib


@dataclass
class DeviceConfig:
    """Device configuration snapshot"""
    device_id: str
    config_hash: str
    config_data: Dict
    timestamp: datetime
    version: int = 1
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'DeviceConfig':
        """Create from dictionary"""
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


@dataclass
class ConfigDriftAlert:
    """Alert for configuration drift"""
    device_id: str
    change_type: str  # 'MODIFIED', 'NEW_DEVICE', 'DELETED_DEVICE', 'CRITICAL_CHANGE'
    changes: Dict  # Detailed changes
    severity: str  # 'CRITICAL', 'WARNING', 'INFO'
    timestamp: datetime
    baseline_version: int
    current_version: int
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


class ConfigurationMonitor:
    """
    Monitor and detect configuration drift
    
    Tracks:
    - Device configurations
    - Network topology changes
    - Security policy modifications
    """
    
    CRITICAL_KEYS = [
        'firewall_rules',
        'access_control',
        'encryption_settings',
        'authentication',
        'security_policies',
        'admin_accounts'
    ]
    
    def __init__(
        self,
        baseline_path: str = 'data/security/config_baseline.json',
        history_path: str = 'data/security/config_history'
    ):
        """
        Initialize configuration monitor
        
        Args:
            baseline_path: Path to baseline configuration file
            history_path: Directory for configuration history
        """
        self.baseline_path = Path(baseline_path)
        self.history_path = Path(history_path)
        self.history_path.mkdir(parents=True, exist_ok=True)
        
        self.baseline = self._load_baseline()
        self.history: List[DeviceConfig] = []
    
    def _load_baseline(self) -> Dict[str, DeviceConfig]:
        """Load baseline configurations"""
        if self.baseline_path.exists():
            with open(self.baseline_path, 'r') as f:
                data = json.load(f)
                baseline = {}
                for device_id, config_dict in data.items():
                    baseline[device_id] = DeviceConfig.from_dict(config_dict)
                return baseline
        else:
            print(f"[WARNING] Baseline not found at {self.baseline_path}")
            return {}
    
    def save_baseline(self):
        """Save current baseline to file"""
        self.baseline_path.parent.mkdir(parents=True, exist_ok=True)
        
        baseline_dict = {
            device_id: config.to_dict()
            for device_id, config in self.baseline.items()
        }
        
        with open(self.baseline_path, 'w') as f:
            json.dump(baseline_dict, f, indent=2)
        
        print(f"[OK] Saved baseline to {self.baseline_path}")
    
    def set_baseline(self, current_configs: Dict[str, Dict]):
        """
        Set current configurations as baseline
        
        Args:
            current_configs: Dict mapping device_id -> config_dict
        """
        self.baseline = {}
        
        for device_id, config_data in current_configs.items():
            config_hash = self._compute_hash(config_data)
            
            self.baseline[device_id] = DeviceConfig(
                device_id=device_id,
                config_hash=config_hash,
                config_data=config_data,
                timestamp=datetime.now(),
                version=1
            )
        
        self.save_baseline()
        print(f"[OK] Set baseline for {len(self.baseline)} devices")
    
    def _compute_hash(self, config_data: Dict) -> str:
        """Compute hash of configuration"""
        config_str = json.dumps(config_data, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()
    
    def detect_drift(
        self,
        current_configs: Dict[str, Dict]
    ) -> List[ConfigDriftAlert]:
        """
        Compare current configs against baseline
        
        Args:
            current_configs: Dict mapping device_id -> current config
        
        Returns:
            List of ConfigDriftAlert objects
        """
        alerts = []
        current_time = datetime.now()
        
        # Check for modifications and new devices
        for device_id, current_config in current_configs.items():
            baseline_config = self.baseline.get(device_id)
            
            if not baseline_config:
                # New device detected
                alerts.append(ConfigDriftAlert(
                    device_id=device_id,
                    change_type='NEW_DEVICE',
                    changes={'message': 'Device not in baseline'},
                    severity='WARNING',
                    timestamp=current_time,
                    baseline_version=0,
                    current_version=1
                ))
                continue
            
            # Compute current hash
            current_hash = self._compute_hash(current_config)
            
            if current_hash != baseline_config.config_hash:
                # Configuration changed
                diff = self._compute_diff(baseline_config.config_data, current_config)
                
                if diff:
                    severity = self._classify_severity(diff)
                    change_type = 'CRITICAL_CHANGE' if severity == 'CRITICAL' else 'MODIFIED'
                    
                    alerts.append(ConfigDriftAlert(
                        device_id=device_id,
                        change_type=change_type,
                        changes=diff,
                        severity=severity,
                        timestamp=current_time,
                        baseline_version=baseline_config.version,
                        current_version=baseline_config.version + 1
                    ))
                    
                    # Save to history
                    self._save_to_history(device_id, current_config, baseline_config.version + 1)
        
        # Check for deleted devices
        for device_id in self.baseline:
            if device_id not in current_configs:
                alerts.append(ConfigDriftAlert(
                    device_id=device_id,
                    change_type='DELETED_DEVICE',
                    changes={'message': 'Device no longer present'},
                    severity='CRITICAL',
                    timestamp=current_time,
                    baseline_version=self.baseline[device_id].version,
                    current_version=0
                ))
        
        return alerts
    
    def _compute_diff(self, baseline: Dict, current: Dict) -> Dict:
        """
        Compute detailed diff between configurations
        
        Returns:
            Dict with added, removed, and modified keys
        """
        diff = {
            'added': {},
            'removed': {},
            'modified': {}
        }
        
        # Find added and modified keys
        for key, current_value in current.items():
            if key not in baseline:
                diff['added'][key] = current_value
            elif baseline[key] != current_value:
                diff['modified'][key] = {
                    'old': baseline[key],
                    'new': current_value
                }
        
        # Find removed keys
        for key in baseline:
            if key not in current:
                diff['removed'][key] = baseline[key]
        
        # Remove empty sections
        diff = {k: v for k, v in diff.items() if v}
        
        return diff
    
    def _classify_severity(self, diff: Dict) -> str:
        """
        Classify drift severity based on change type
        
        Returns:
            'CRITICAL', 'WARNING', or 'INFO'
        """
        # Check if critical keys were modified
        for section in ['added', 'removed', 'modified']:
            if section in diff:
                for key in diff[section]:
                    if any(critical_key in key.lower() for critical_key in self.CRITICAL_KEYS):
                        return 'CRITICAL'
        
        # Check number of changes
        total_changes = sum(len(diff.get(section, {})) for section in ['added', 'removed', 'modified'])
        
        if total_changes > 10:
            return 'WARNING'
        
        return 'INFO'
    
    def _save_to_history(self, device_id: str, config_data: Dict, version: int):
        """Save configuration snapshot to history"""
        config_hash = self._compute_hash(config_data)
        
        snapshot = DeviceConfig(
            device_id=device_id,
            config_hash=config_hash,
            config_data=config_data,
            timestamp=datetime.now(),
            version=version
        )
        
        # Save to file
        filename = f"{device_id}_v{version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.history_path / filename
        
        with open(filepath, 'w') as f:
            json.dump(snapshot.to_dict(), f, indent=2)
    
    def get_config_history(self, device_id: str, limit: int = 10) -> List[DeviceConfig]:
        """
        Get configuration history for a device
        
        Args:
            device_id: Device identifier
            limit: Maximum number of historical configs to return
        
        Returns:
            List of DeviceConfig snapshots (most recent first)
        """
        history_files = sorted(
            self.history_path.glob(f"{device_id}_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        configs = []
        for filepath in history_files[:limit]:
            with open(filepath, 'r') as f:
                data = json.load(f)
                configs.append(DeviceConfig.from_dict(data))
        
        return configs
    
    def approve_changes(self, device_id: str, new_config: Dict):
        """
        Approve configuration changes and update baseline
        
        Args:
            device_id: Device identifier
            new_config: New approved configuration
        """
        config_hash = self._compute_hash(new_config)
        
        if device_id in self.baseline:
            version = self.baseline[device_id].version + 1
        else:
            version = 1
        
        self.baseline[device_id] = DeviceConfig(
            device_id=device_id,
            config_hash=config_hash,
            config_data=new_config,
            timestamp=datetime.now(),
            version=version
        )
        
        self.save_baseline()
        print(f"[OK] Approved configuration for {device_id} (version {version})")
    
    def generate_report(self, alerts: List[ConfigDriftAlert]) -> Dict:
        """Generate configuration drift report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'total_alerts': len(alerts),
            'critical_alerts': sum(1 for a in alerts if a.severity == 'CRITICAL'),
            'warning_alerts': sum(1 for a in alerts if a.severity == 'WARNING'),
            'info_alerts': sum(1 for a in alerts if a.severity == 'INFO'),
            'alerts_by_type': {},
            'devices': []
        }
        
        # Group by change type
        for alert in alerts:
            change_type = alert.change_type
            if change_type not in report['alerts_by_type']:
                report['alerts_by_type'][change_type] = 0
            report['alerts_by_type'][change_type] += 1
            
            report['devices'].append(alert.to_dict())
        
        return report
