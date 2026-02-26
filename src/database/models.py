"""
SQLAlchemy ORM Models for NetHealth AI Database

Provides object-relational mapping for Tables (SQLite/PostgreSQL compatible).
"""

from sqlalchemy import (
    Column, String, Float, Integer, DateTime, JSON, Boolean, 
    ForeignKey, Text, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

Base = declarative_base()


class Asset(Base):
    """Network asset/device model"""
    __tablename__ = 'assets'
    
    # Use String for UUID in SQLite
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_id = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(255))
    type = Column(String(50), index=True)
    ip_address = Column(String(50), index=True)  # Changed from INET to String
    mac_address = Column(String(20))  # Changed from MACADDR to String
    location = Column(JSON)
    meta_data = Column(JSON)
    status = Column(String(20), default='active', index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    metrics = relationship("Metric", back_populates="asset", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="asset")
    configurations = relationship("Configuration", back_populates="asset", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Asset(asset_id='{self.asset_id}', name='{self.name}', type='{self.type}')>"


class Metric(Base):
    """Time-series metric model"""
    __tablename__ = 'metrics'
    
    time = Column(DateTime, primary_key=True, nullable=False)
    asset_id = Column(String(100), ForeignKey('assets.asset_id', ondelete='CASCADE'), 
                     primary_key=True, nullable=False)
    metric_name = Column(String(100), primary_key=True, nullable=False)
    value = Column(Float)
    unit = Column(String(20))
    tags = Column(JSON)
    
    # Relationship
    asset = relationship("Asset", back_populates="metrics")
    
    def __repr__(self):
        return f"<Metric(asset_id='{self.asset_id}', metric='{self.metric_name}', value={self.value})>"


class Alert(Base):
    """Alert/anomaly model"""
    __tablename__ = 'alerts'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    time = Column(DateTime, nullable=False, index=True)
    asset_id = Column(String(100), ForeignKey('assets.asset_id', ondelete='SET NULL'), index=True)
    alert_type = Column(String(50), index=True)
    severity = Column(String(20), index=True)
    description = Column(Text)
    meta_data = Column(JSON)
    acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(String(100))
    acknowledged_at = Column(DateTime)
    resolved = Column(Boolean, default=False, index=True)
    resolved_by = Column(String(100))
    resolved_at = Column(DateTime)
    
    # Relationship
    asset = relationship("Asset", back_populates="alerts")
    
    def __repr__(self):
        return f"<Alert(id='{self.id}', type='{self.alert_type}', severity='{self.severity}')>"


class Topology(Base):
    """Network topology/connection model"""
    __tablename__ = 'topology'
    __table_args__ = (
        UniqueConstraint('source_id', 'target_id', name='uq_topology_connection'),
    )
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_id = Column(String(100), ForeignKey('assets.asset_id', ondelete='CASCADE'), 
                      nullable=False, index=True)
    target_id = Column(String(100), ForeignKey('assets.asset_id', ondelete='CASCADE'), 
                      nullable=False, index=True)
    connection_type = Column(String(50), index=True)
    bandwidth = Column(Integer)
    latency = Column(Float)
    meta_data = Column(JSON)
    status = Column(String(20), default='active')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Topology(source='{self.source_id}', target='{self.target_id}', type='{self.connection_type}')>"


class Configuration(Base):
    """Device configuration snapshot model"""
    __tablename__ = 'configurations'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_id = Column(String(100), ForeignKey('assets.asset_id', ondelete='CASCADE'), 
                     nullable=False, index=True)
    config_snapshot = Column(JSON, nullable=False)
    config_hash = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False)
    is_baseline = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    created_by = Column(String(100))
    
    # Relationship
    asset = relationship("Asset", back_populates="configurations")
    
    def __repr__(self):
        return f"<Configuration(asset_id='{self.asset_id}', version={self.version}, baseline={self.is_baseline})>"


class SecurityEvent(Base):
    """Security event model"""
    __tablename__ = 'security_events'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    time = Column(DateTime, nullable=False, index=True)
    event_type = Column(String(50), index=True)
    severity = Column(String(20), index=True)
    device_id = Column(String(100), index=True)
    mac_address = Column(String(20))
    ip_address = Column(String(50))
    details = Column(JSON)
    resolved = Column(Boolean, default=False, index=True)
    resolved_by = Column(String(100))
    resolved_at = Column(DateTime)
    
    def __repr__(self):
        return f"<SecurityEvent(id='{self.id}', type='{self.event_type}', severity='{self.severity}')>"


class MLPrediction(Base):
    """ML model prediction model"""
    __tablename__ = 'ml_predictions'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    time = Column(DateTime, nullable=False, index=True)
    model_name = Column(String(100), nullable=False, index=True)
    model_version = Column(String(20))
    asset_id = Column(String(100), ForeignKey('assets.asset_id', ondelete='SET NULL'), index=True)
    prediction_type = Column(String(50))
    prediction_value = Column(JSON)
    confidence = Column(Float)
    meta_data = Column(JSON)
    
    def __repr__(self):
        return f"<MLPrediction(model='{self.model_name}', type='{self.prediction_type}', confidence={self.confidence})>"


class User(Base):
    """User model for authentication"""
    __tablename__ = 'users'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), default='viewer')
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)
    
    # Relationships
    api_tokens = relationship("APIToken", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(username='{self.username}', role='{self.role}')>"


class APIToken(Base):
    """API token model"""
    __tablename__ = 'api_tokens'
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey('users.id', ondelete='CASCADE'), 
                    nullable=False, index=True)
    token_hash = Column(String(255), nullable=False, index=True)
    name = Column(String(100))
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used = Column(DateTime)
    
    # Relationship
    user = relationship("User", back_populates="api_tokens")
    
    def __repr__(self):
        return f"<APIToken(name='{self.name}', user_id='{self.user_id}')>"
