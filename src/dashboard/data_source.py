"""
Data Source Abstraction Layer

Provides unified interface for dashboard to access data from different sources:
- Synthetic CSV files (for demos)
- Production TimescaleDB (for live monitoring)
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import pandas as pd
import json
import logging

logger = logging.getLogger(__name__)


class DataSource(ABC):
    """Abstract base class for data sources"""
    
    @abstractmethod
    def get_assets(self) -> List[Dict[str, Any]]:
        """Get all assets/devices"""
        pass
    
    @abstractmethod
    def get_asset(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """Get single asset by ID"""
        pass
    
    @abstractmethod
    def get_latest_metrics(self, asset_id: str) -> Dict[str, Any]:
        """Get latest metric values for an asset"""
        pass
    
    @abstractmethod
    def get_all_latest_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get latest metrics for all assets"""
        pass
    
    @abstractmethod
    def get_time_range_metrics(
        self,
        asset_id: str,
        metric_name: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """Get metrics for a time range"""
        pass
    
    @abstractmethod
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get active (unresolved) alerts"""
        pass
    
    @abstractmethod
    def get_topology(self) -> Dict[str, Any]:
        """Get network topology"""
        pass
    
    @abstractmethod
    def get_security_events(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get recent security events"""
        pass
    
    @abstractmethod
    def is_live(self) -> bool:
        """Check if this is a live data source"""
        pass


class SyntheticDataSource(DataSource):
    """
    Synthetic data source using CSV files
    
    This wraps the existing CSV-based data loading for backward compatibility.
    """
    
    def __init__(self, metrics_path: str = None, assets_path: str = None):
        """
        Initialize synthetic data source
        
        Args:
            metrics_path: Path to metrics CSV
            assets_path: Path to assets JSON
        """
        self.metrics_path = metrics_path or 'data/raw/metrics_timeseries.csv'
        self.assets_path = assets_path or 'data/raw/assets.json'
        
        self._load_data()
    
    def _load_data(self):
        """Load data from files"""
        try:
            # Load metrics
            self.metrics_df = pd.read_csv(self.metrics_path)
            if 'timestamp' in self.metrics_df.columns:
                self.metrics_df['timestamp'] = pd.to_datetime(self.metrics_df['timestamp'])
            
            # Load assets
            with open(self.assets_path, 'r') as f:
                self.assets_data = json.load(f)
            
            logger.info(f"Loaded synthetic data: {len(self.metrics_df)} metrics, {len(self.assets_data)} assets")
            
        except Exception as e:
            logger.error(f"Error loading synthetic data: {e}")
            self.metrics_df = pd.DataFrame()
            self.assets_data = []
    
    def reload_data(self, metrics_path: str = None, assets_path: str = None):
        """Reload data from different files"""
        if metrics_path:
            self.metrics_path = metrics_path
        if assets_path:
            self.assets_path = assets_path
        self._load_data()
    
    def get_assets(self) -> List[Dict[str, Any]]:
        """Get all assets"""
        return self.assets_data
    
    def get_asset(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """Get single asset"""
        for asset in self.assets_data:
            if asset.get('asset_id') == asset_id:
                return asset
        return None
    
    def get_latest_metrics(self, asset_id: str) -> Dict[str, Any]:
        """Get latest metrics for an asset"""
        if self.metrics_df.empty:
            return {}
        
        # Filter by asset
        asset_metrics = self.metrics_df[self.metrics_df['asset_id'] == asset_id]
        if asset_metrics.empty:
            return {}
        
        # Get latest values for each metric
        latest = {}
        for metric_name in asset_metrics['metric'].unique():
            metric_data = asset_metrics[asset_metrics['metric'] == metric_name]
            if not metric_data.empty:
                latest_row = metric_data.iloc[-1]
                latest[metric_name] = {
                    'value': latest_row['value'],
                    'timestamp': latest_row.get('timestamp', datetime.now())
                }
        
        return latest
    
    def get_all_latest_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get latest metrics for all assets"""
        all_metrics = {}
        for asset in self.assets_data:
            asset_id = asset.get('asset_id')
            if asset_id:
                all_metrics[asset_id] = self.get_latest_metrics(asset_id)
        return all_metrics
    
    def get_time_range_metrics(
        self,
        asset_id: str,
        metric_name: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """Get metrics for time range"""
        if self.metrics_df.empty:
            return pd.DataFrame()
        
        # Filter by asset and metric
        filtered = self.metrics_df[
            (self.metrics_df['asset_id'] == asset_id) &
            (self.metrics_df['metric'] == metric_name)
        ]
        
        # Filter by time if timestamp column exists
        if 'timestamp' in filtered.columns:
            filtered = filtered[
                (filtered['timestamp'] >= start_time) &
                (filtered['timestamp'] <= end_time)
            ]
        
        return filtered
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get active alerts (synthetic data doesn't have real alerts)"""
        return []
    
    def get_topology(self) -> Dict[str, Any]:
        """Get topology (extract from assets)"""
        topology = {'nodes': [], 'edges': []}
        
        for asset in self.assets_data:
            topology['nodes'].append({
                'id': asset.get('asset_id'),
                'type': asset.get('type'),
                'location': asset.get('location')
            })
        
        # Simple topology: connect devices in sequence
        for i in range(len(self.assets_data) - 1):
            topology['edges'].append({
                'source': self.assets_data[i].get('asset_id'),
                'target': self.assets_data[i + 1].get('asset_id')
            })
        
        return topology
    
    def get_security_events(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get security events (synthetic data doesn't have real events)"""
        return []
    
    def is_live(self) -> bool:
        """Not a live data source"""
        return False


class DatabaseDataSource(DataSource):
    """
    Production database data source using TimescaleDB
    
    Connects to PostgreSQL/TimescaleDB via repository layer.
    """
    
    def __init__(self, db_manager):
        """
        Initialize database data source
        
        Args:
            db_manager: DatabaseManager instance
        """
        self.db_manager = db_manager
        
        # Import repositories
        from src.database.repository import (
            AssetRepository,
            MetricsRepository,
            AlertRepository,
            TopologyRepository,
            SecurityEventRepository
        )
        
        self.AssetRepository = AssetRepository
        self.MetricsRepository = MetricsRepository
        self.AlertRepository = AlertRepository
        self.TopologyRepository = TopologyRepository
        self.SecurityEventRepository = SecurityEventRepository
        
        logger.info("Initialized database data source")
    
    def get_assets(self) -> List[Dict[str, Any]]:
        """Get all assets from database"""
        try:
            with self.db_manager.get_session() as session:
                repo = self.AssetRepository(session)
                assets = repo.get_all(status='active')
                
                # Convert to dict
                return [{
                    'asset_id': a.asset_id,
                    'type': a.type,
                    'name': a.name,
                    'ip_address': str(a.ip_address) if a.ip_address else None,
                    'mac_address': str(a.mac_address) if a.mac_address else None,
                    'location': a.location,
                    'metadata': a.meta_data,
                    'status': a.status
                } for a in assets]
                
        except Exception as e:
            logger.error(f"Error getting assets: {e}")
            return []
    
    def get_asset(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """Get single asset"""
        try:
            with self.db_manager.get_session() as session:
                repo = self.AssetRepository(session)
                asset = repo.get_by_id(asset_id)
                
                if asset:
                    return {
                        'asset_id': asset.asset_id,
                        'type': asset.type,
                        'name': asset.name,
                        'ip_address': str(asset.ip_address) if asset.ip_address else None,
                        'mac_address': str(asset.mac_address) if asset.mac_address else None,
                        'location': asset.location,
                        'metadata': asset.meta_data,
                        'status': asset.status
                    }
                return None
                
        except Exception as e:
            logger.error(f"Error getting asset {asset_id}: {e}")
            return None
    
    def get_latest_metrics(self, asset_id: str) -> Dict[str, Any]:
        """Get latest metrics for an asset"""
        try:
            with self.db_manager.get_session() as session:
                repo = self.MetricsRepository(session)
                latest = repo.get_latest(asset_id)
                
                # Convert to dict
                metrics = {}
                for row in latest:
                    metrics[row.metric_name] = {
                        'value': row.value,
                        'unit': row.unit,
                        'timestamp': row.time
                    }
                
                return metrics
                
        except Exception as e:
            logger.error(f"Error getting metrics for {asset_id}: {e}")
            return {}
    
    def get_all_latest_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get latest metrics for all assets"""
        all_metrics = {}
        assets = self.get_assets()
        
        for asset in assets:
            asset_id = asset['asset_id']
            all_metrics[asset_id] = self.get_latest_metrics(asset_id)
        
        return all_metrics
    
    def get_time_range_metrics(
        self,
        asset_id: str,
        metric_name: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """Get metrics for time range"""
        try:
            with self.db_manager.get_session() as session:
                repo = self.MetricsRepository(session)
                df = repo.query_time_range(asset_id, metric_name, start_time, end_time)
                return df
                
        except Exception as e:
            logger.error(f"Error getting time range metrics: {e}")
            return pd.DataFrame()
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get active alerts"""
        try:
            with self.db_manager.get_session() as session:
                repo = self.AlertRepository(session)
                alerts = repo.get_active()
                
                # Convert to dict
                return [{
                    'id': str(a.id),
                    'asset_id': a.asset_id,
                    'alert_type': a.alert_type,
                    'severity': a.severity,
                    'message': a.message,
                    'time': a.time,
                    'acknowledged': a.acknowledged,
                    'resolved': a.resolved
                } for a in alerts]
                
        except Exception as e:
            logger.error(f"Error getting alerts: {e}")
            return []
    
    def get_topology(self) -> Dict[str, Any]:
        """Get network topology"""
        try:
            with self.db_manager.get_session() as session:
                repo = self.TopologyRepository(session)
                connections = repo.get_all_connections()
                
                # Build topology
                topology = {'nodes': [], 'edges': []}
                
                # Get all assets as nodes
                assets = self.get_assets()
                for asset in assets:
                    topology['nodes'].append({
                        'id': asset['asset_id'],
                        'type': asset['type'],
                        'location': asset.get('location')
                    })
                
                # Add connections as edges
                for conn in connections:
                    topology['edges'].append({
                        'source': conn.source_id,
                        'target': conn.target_id,
                        'connection_type': conn.connection_type,
                        'bandwidth': conn.bandwidth,
                        'status': conn.status
                    })
                
                return topology
                
        except Exception as e:
            logger.error(f"Error getting topology: {e}")
            return {'nodes': [], 'edges': []}
    
    def get_security_events(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get recent security events"""
        try:
            with self.db_manager.get_session() as session:
                repo = self.SecurityEventRepository(session)
                events = repo.get_recent(hours=hours)
                
                # Convert to dict
                return [{
                    'id': str(e.id),
                    'asset_id': e.asset_id,
                    'event_type': e.event_type,
                    'severity': e.severity,
                    'description': e.description,
                    'time': e.time,
                    'resolved': e.resolved
                } for e in events]
                
        except Exception as e:
            logger.error(f"Error getting security events: {e}")
            return []
    
    def is_live(self) -> bool:
        """This is a live data source"""
        return True
    
    def health_check(self) -> bool:
        """Check database connectivity"""
        return self.db_manager.health_check()
