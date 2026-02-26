"""
Data Repository Layer

Implements repository pattern for data access with optimized queries.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_, desc
from sqlalchemy.orm import Session
import pandas as pd

from src.database.models import (
    Asset, Metric, Alert, Topology, Configuration,
    SecurityEvent, MLPrediction, User, APIToken
)


class AssetRepository:
    """Repository for asset operations"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, asset_data: Dict[str, Any]) -> Asset:
        """Create new asset"""
        asset = Asset(**asset_data)
        self.session.add(asset)
        self.session.flush()
        return asset
    
    def get_by_id(self, asset_id: str) -> Optional[Asset]:
        """Get asset by ID"""
        return self.session.query(Asset).filter(
            Asset.asset_id == asset_id
        ).first()
    
    def get_all(self, status: Optional[str] = None) -> List[Asset]:
        """Get all assets, optionally filtered by status"""
        query = self.session.query(Asset)
        if status:
            query = query.filter(Asset.status == status)
        return query.all()
    
    def get_by_type(self, asset_type: str) -> List[Asset]:
        """Get assets by type"""
        return self.session.query(Asset).filter(
            Asset.type == asset_type
        ).all()
    
    def update(self, asset_id: str, updates: Dict[str, Any]) -> Optional[Asset]:
        """Update asset"""
        asset = self.get_by_id(asset_id)
        if asset:
            for key, value in updates.items():
                setattr(asset, key, value)
            asset.updated_at = datetime.utcnow()
            self.session.flush()
        return asset
    
    def delete(self, asset_id: str) -> bool:
        """Delete asset"""
        asset = self.get_by_id(asset_id)
        if asset:
            self.session.delete(asset)
            self.session.flush()
            return True
        return False


class MetricsRepository:
    """Repository for metrics operations with TimescaleDB optimizations"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def insert_batch(self, metrics: List[Dict[str, Any]]) -> int:
        """
        Batch insert metrics for performance
        
        Args:
            metrics: List of metric dictionaries
        
        Returns:
            Number of metrics inserted
        """
        metric_objects = [Metric(**m) for m in metrics]
        self.session.bulk_save_objects(metric_objects)
        self.session.flush()
        return len(metric_objects)
    
    def get_latest(
        self,
        asset_id: str,
        metric_names: Optional[List[str]] = None
    ) -> List[Metric]:
        """
        Get latest values for specified metrics
        
        Args:
            asset_id: Asset ID
            metric_names: List of metric names (None = all)
        
        Returns:
            List of latest metrics
        """
        # Use the latest_metrics view for efficiency
        from sqlalchemy import text
        query = self.session.execute(
            text("""
            SELECT * FROM latest_metrics
            WHERE asset_id = :asset_id
            """ + (" AND metric_name = ANY(:metric_names)" if metric_names else "")),
            {'asset_id': asset_id, 'metric_names': metric_names}
        )
        return query.fetchall()
    
    def query_time_range(
        self,
        asset_id: str,
        metric_name: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """
        Query metrics for a time range
        
        Args:
            asset_id: Asset ID
            metric_name: Metric name
            start_time: Start of time range
            end_time: End of time range
        
        Returns:
            DataFrame with time-series data
        """
        query = self.session.query(Metric).filter(
            and_(
                Metric.asset_id == asset_id,
                Metric.metric_name == metric_name,
                Metric.time >= start_time,
                Metric.time <= end_time
            )
        ).order_by(Metric.time)
        
        results = query.all()
        
        # Convert to DataFrame
        data = [{
            'time': m.time,
            'value': m.value,
            'unit': m.unit,
            'tags': m.tags
        } for m in results]
        
        return pd.DataFrame(data)
    
    def get_aggregated(
        self,
        asset_id: str,
        metric_name: str,
        start_time: datetime,
        end_time: datetime,
        interval: str = '1 hour'
    ) -> pd.DataFrame:
        """
        Get aggregated metrics using continuous aggregates
        
        Args:
            asset_id: Asset ID
            metric_name: Metric name
            start_time: Start time
            end_time: End time
            interval: Aggregation interval ('1 hour' or '1 day')
        
        Returns:
            DataFrame with aggregated data
        """
        # Use appropriate continuous aggregate view
        view_name = 'metrics_hourly' if interval == '1 hour' else 'metrics_daily'
        
        from sqlalchemy import text
        query = self.session.execute(
            text(f"""
            SELECT bucket, avg_value, max_value, min_value, stddev_value, sample_count
            FROM {view_name}
            WHERE asset_id = :asset_id
              AND metric_name = :metric_name
              AND bucket >= :start_time
              AND bucket <= :end_time
            ORDER BY bucket
            """),
            {
                'asset_id': asset_id,
                'metric_name': metric_name,
                'start_time': start_time,
                'end_time': end_time
            }
        )
        
        results = query.fetchall()
        return pd.DataFrame(results, columns=['time', 'avg', 'max', 'min', 'stddev', 'count'])


class AlertRepository:
    """Repository for alert operations"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, alert_data: Dict[str, Any]) -> Alert:
        """Create new alert"""
        alert = Alert(**alert_data)
        self.session.add(alert)
        self.session.flush()
        return alert
    
    def get_active(
        self,
        asset_id: Optional[str] = None,
        severity: Optional[str] = None
    ) -> List[Alert]:
        """Get active (unresolved) alerts"""
        query = self.session.query(Alert).filter(Alert.resolved == False)
        
        if asset_id:
            query = query.filter(Alert.asset_id == asset_id)
        if severity:
            query = query.filter(Alert.severity == severity)
        
        return query.order_by(desc(Alert.time)).all()
    
    def get_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        asset_id: Optional[str] = None
    ) -> List[Alert]:
        """Get alerts in time range"""
        query = self.session.query(Alert).filter(
            and_(
                Alert.time >= start_time,
                Alert.time <= end_time
            )
        )
        
        if asset_id:
            query = query.filter(Alert.asset_id == asset_id)
        
        return query.order_by(desc(Alert.time)).all()
    
    def acknowledge(self, alert_id: str, acknowledged_by: str) -> Optional[Alert]:
        """Acknowledge an alert"""
        alert = self.session.query(Alert).filter(Alert.id == alert_id).first()
        if alert:
            alert.acknowledged = True
            alert.acknowledged_by = acknowledged_by
            alert.acknowledged_at = datetime.utcnow()
            self.session.flush()
        return alert
    
    def resolve(self, alert_id: str, resolved_by: str) -> Optional[Alert]:
        """Resolve an alert"""
        alert = self.session.query(Alert).filter(Alert.id == alert_id).first()
        if alert:
            alert.resolved = True
            alert.resolved_by = resolved_by
            alert.resolved_at = datetime.utcnow()
            self.session.flush()
        return alert
    
    def get_summary(self) -> Dict[str, int]:
        """Get alert summary statistics"""
        from sqlalchemy import text
        result = self.session.execute(
            text("""
            SELECT * FROM active_alerts_summary
            """)
        )
        
        summary = {}
        for row in result:
            key = f"{row.severity}_{row.alert_type}"
            summary[key] = row.count
        
        return summary


class TopologyRepository:
    """Repository for topology operations"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create_connection(self, connection_data: Dict[str, Any]) -> Topology:
        """Create network connection"""
        connection = Topology(**connection_data)
        self.session.add(connection)
        self.session.flush()
        return connection
    
    def get_all_connections(self, status: str = 'active') -> List[Topology]:
        """Get all network connections"""
        return self.session.query(Topology).filter(
            Topology.status == status
        ).all()
    
    def get_device_connections(self, asset_id: str) -> List[Topology]:
        """Get all connections for a device"""
        return self.session.query(Topology).filter(
            or_(
                Topology.source_id == asset_id,
                Topology.target_id == asset_id
            )
        ).all()
    
    def update_connection(
        self,
        source_id: str,
        target_id: str,
        updates: Dict[str, Any]
    ) -> Optional[Topology]:
        """Update connection"""
        connection = self.session.query(Topology).filter(
            and_(
                Topology.source_id == source_id,
                Topology.target_id == target_id
            )
        ).first()
        
        if connection:
            for key, value in updates.items():
                setattr(connection, key, value)
            connection.updated_at = datetime.utcnow()
            self.session.flush()
        
        return connection


class SecurityEventRepository:
    """Repository for security event operations"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, event_data: Dict[str, Any]) -> SecurityEvent:
        """Create security event"""
        event = SecurityEvent(**event_data)
        self.session.add(event)
        self.session.flush()
        return event
    
    def get_recent(
        self,
        hours: int = 24,
        event_type: Optional[str] = None,
        severity: Optional[str] = None
    ) -> List[SecurityEvent]:
        """Get recent security events"""
        start_time = datetime.utcnow() - timedelta(hours=hours)
        
        query = self.session.query(SecurityEvent).filter(
            SecurityEvent.time >= start_time
        )
        
        if event_type:
            query = query.filter(SecurityEvent.event_type == event_type)
        if severity:
            query = query.filter(SecurityEvent.severity == severity)
        
        return query.order_by(desc(SecurityEvent.time)).all()
    
    def get_unresolved(self) -> List[SecurityEvent]:
        """Get unresolved security events"""
        return self.session.query(SecurityEvent).filter(
            SecurityEvent.resolved == False
        ).order_by(desc(SecurityEvent.time)).all()
    
    def resolve(self, event_id: str, resolved_by: str) -> Optional[SecurityEvent]:
        """Resolve security event"""
        event = self.session.query(SecurityEvent).filter(
            SecurityEvent.id == event_id
        ).first()
        
        if event:
            event.resolved = True
            event.resolved_by = resolved_by
            event.resolved_at = datetime.utcnow()
            self.session.flush()
        
        return event
