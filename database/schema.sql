-- NetHealth AI Production Database Schema
-- PostgreSQL 14+ with TimescaleDB extension

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ============================================================================
-- ASSETS TABLE
-- ============================================================================
-- Stores device/asset metadata
CREATE TABLE IF NOT EXISTS assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(255),
    type VARCHAR(50),  -- switch, router, plc, sensor, etc.
    ip_address INET,
    mac_address MACADDR,
    location JSONB,  -- {x: float, y: float, floor: string, building: string}
    metadata JSONB,  -- Flexible storage for device-specific data
    status VARCHAR(20) DEFAULT 'active',  -- active, inactive, maintenance
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_assets_type ON assets(type);
CREATE INDEX idx_assets_status ON assets(status);
CREATE INDEX idx_assets_ip ON assets(ip_address);

-- ============================================================================
-- METRICS HYPERTABLE
-- ============================================================================
-- Time-series metrics data
CREATE TABLE IF NOT EXISTS metrics (
    time TIMESTAMPTZ NOT NULL,
    asset_id VARCHAR(100) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    value DOUBLE PRECISION,
    unit VARCHAR(20),
    tags JSONB,  -- Additional metadata like source, quality, etc.
    FOREIGN KEY (asset_id) REFERENCES assets(asset_id) ON DELETE CASCADE
);

-- Convert to hypertable (7-day chunks)
SELECT create_hypertable('metrics', 'time', 
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Compression policy (compress data older than 7 days)
ALTER TABLE metrics SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'asset_id,metric_name',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy('metrics', INTERVAL '7 days', if_not_exists => TRUE);

-- Retention policy (drop data older than 90 days)
SELECT add_retention_policy('metrics', INTERVAL '90 days', if_not_exists => TRUE);

-- Indexes for query performance
CREATE INDEX idx_metrics_asset_time ON metrics (asset_id, time DESC);
CREATE INDEX idx_metrics_name_time ON metrics (metric_name, time DESC);
CREATE INDEX idx_metrics_asset_name_time ON metrics (asset_id, metric_name, time DESC);

-- ============================================================================
-- CONTINUOUS AGGREGATES
-- ============================================================================
-- Hourly aggregates for faster queries
CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    asset_id,
    metric_name,
    AVG(value) AS avg_value,
    MAX(value) AS max_value,
    MIN(value) AS min_value,
    STDDEV(value) AS stddev_value,
    COUNT(*) AS sample_count
FROM metrics
GROUP BY bucket, asset_id, metric_name;

-- Refresh policy (refresh every hour, lag 1 hour)
SELECT add_continuous_aggregate_policy('metrics_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Daily aggregates
CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time) AS bucket,
    asset_id,
    metric_name,
    AVG(value) AS avg_value,
    MAX(value) AS max_value,
    MIN(value) AS min_value,
    STDDEV(value) AS stddev_value,
    COUNT(*) AS sample_count
FROM metrics
GROUP BY bucket, asset_id, metric_name;

SELECT add_continuous_aggregate_policy('metrics_daily',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- ============================================================================
-- ALERTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    time TIMESTAMPTZ NOT NULL,
    asset_id VARCHAR(100),
    alert_type VARCHAR(50),  -- anomaly, fault, threshold, prediction
    severity VARCHAR(20),  -- critical, high, medium, low, info
    description TEXT,
    metadata JSONB,  -- Additional context, affected metrics, etc.
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_by VARCHAR(100),
    acknowledged_at TIMESTAMPTZ,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_by VARCHAR(100),
    resolved_at TIMESTAMPTZ,
    FOREIGN KEY (asset_id) REFERENCES assets(asset_id) ON DELETE SET NULL
);

-- Convert to hypertable
SELECT create_hypertable('alerts', 'time', 
    chunk_time_interval => INTERVAL '30 days',
    if_not_exists => TRUE
);

-- Indexes
CREATE INDEX idx_alerts_asset_time ON alerts (asset_id, time DESC);
CREATE INDEX idx_alerts_severity_time ON alerts (severity, time DESC);
CREATE INDEX idx_alerts_unresolved ON alerts (resolved, time DESC) WHERE NOT resolved;
CREATE INDEX idx_alerts_type ON alerts (alert_type, time DESC);

-- ============================================================================
-- TOPOLOGY TABLE
-- ============================================================================
-- Network topology/connections
CREATE TABLE IF NOT EXISTS topology (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id VARCHAR(100) NOT NULL,
    target_id VARCHAR(100) NOT NULL,
    connection_type VARCHAR(50),  -- ethernet, profinet, modbus, etc.
    bandwidth INTEGER,  -- Mbps
    latency FLOAT,  -- ms
    metadata JSONB,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (source_id) REFERENCES assets(asset_id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES assets(asset_id) ON DELETE CASCADE,
    UNIQUE(source_id, target_id)
);

CREATE INDEX idx_topology_source ON topology(source_id);
CREATE INDEX idx_topology_target ON topology(target_id);
CREATE INDEX idx_topology_type ON topology(connection_type);

-- ============================================================================
-- CONFIGURATIONS TABLE
-- ============================================================================
-- Configuration baselines and history
CREATE TABLE IF NOT EXISTS configurations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id VARCHAR(100) NOT NULL,
    config_snapshot JSONB NOT NULL,
    config_hash VARCHAR(64) NOT NULL,  -- SHA256 hash
    version INTEGER NOT NULL,
    is_baseline BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(100),
    FOREIGN KEY (asset_id) REFERENCES assets(asset_id) ON DELETE CASCADE
);

CREATE INDEX idx_config_asset_version ON configurations(asset_id, version DESC);
CREATE INDEX idx_config_baseline ON configurations(asset_id, is_baseline) WHERE is_baseline = TRUE;
CREATE INDEX idx_config_time ON configurations(created_at DESC);

-- ============================================================================
-- SECURITY EVENTS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS security_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    time TIMESTAMPTZ NOT NULL,
    event_type VARCHAR(50),  -- rogue_device, config_drift, unauthorized_access
    severity VARCHAR(20),  -- critical, warning, info
    device_id VARCHAR(100),
    mac_address MACADDR,
    ip_address INET,
    details JSONB,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_by VARCHAR(100),
    resolved_at TIMESTAMPTZ
);

-- Convert to hypertable
SELECT create_hypertable('security_events', 'time',
    chunk_time_interval => INTERVAL '30 days',
    if_not_exists => TRUE
);

-- Indexes
CREATE INDEX idx_security_time ON security_events(time DESC);
CREATE INDEX idx_security_type ON security_events(event_type, time DESC);
CREATE INDEX idx_security_severity ON security_events(severity, time DESC);
CREATE INDEX idx_security_unresolved ON security_events(resolved, time DESC) WHERE NOT resolved;
CREATE INDEX idx_security_device ON security_events(device_id, time DESC);

-- ============================================================================
-- ML PREDICTIONS TABLE
-- ============================================================================
-- Store ML model predictions for analysis
CREATE TABLE IF NOT EXISTS ml_predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    time TIMESTAMPTZ NOT NULL,
    model_name VARCHAR(100) NOT NULL,  -- gnn_correlator, lstm_forecaster
    model_version VARCHAR(20),
    asset_id VARCHAR(100),
    prediction_type VARCHAR(50),  -- fault_probability, forecast, anomaly
    prediction_value JSONB,  -- Flexible storage for different prediction types
    confidence FLOAT,
    metadata JSONB,
    FOREIGN KEY (asset_id) REFERENCES assets(asset_id) ON DELETE SET NULL
);

SELECT create_hypertable('ml_predictions', 'time',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

CREATE INDEX idx_predictions_model_time ON ml_predictions(model_name, time DESC);
CREATE INDEX idx_predictions_asset_time ON ml_predictions(asset_id, time DESC);

-- ============================================================================
-- USERS TABLE (for API authentication)
-- ============================================================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'viewer',  -- admin, operator, viewer
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_login TIMESTAMPTZ
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);

-- ============================================================================
-- API TOKENS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS api_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    token_hash VARCHAR(255) NOT NULL,
    name VARCHAR(100),  -- Token description
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used TIMESTAMPTZ,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_tokens_user ON api_tokens(user_id);
CREATE INDEX idx_tokens_hash ON api_tokens(token_hash);

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for auto-updating updated_at
CREATE TRIGGER update_assets_updated_at BEFORE UPDATE ON assets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_topology_updated_at BEFORE UPDATE ON topology
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- VIEWS FOR COMMON QUERIES
-- ============================================================================

-- Latest metrics per asset
CREATE OR REPLACE VIEW latest_metrics AS
SELECT DISTINCT ON (asset_id, metric_name)
    asset_id,
    metric_name,
    value,
    unit,
    time,
    tags
FROM metrics
ORDER BY asset_id, metric_name, time DESC;

-- Active alerts summary
CREATE OR REPLACE VIEW active_alerts_summary AS
SELECT
    severity,
    alert_type,
    COUNT(*) as count
FROM alerts
WHERE NOT resolved
GROUP BY severity, alert_type;

-- Asset health summary
CREATE OR REPLACE VIEW asset_health_summary AS
SELECT
    a.asset_id,
    a.name,
    a.type,
    a.status,
    COUNT(DISTINCT al.id) as active_alerts,
    MAX(al.severity) as max_severity
FROM assets a
LEFT JOIN alerts al ON a.asset_id = al.asset_id AND NOT al.resolved
GROUP BY a.asset_id, a.name, a.type, a.status;

-- ============================================================================
-- SAMPLE DATA (for testing)
-- ============================================================================

-- Insert sample assets
INSERT INTO assets (asset_id, name, type, ip_address, location, metadata)
VALUES
    ('switch_001', 'Core Switch 1', 'switch', '192.168.1.1', 
     '{"x": 50, "y": 50, "floor": "1", "building": "Main"}'::jsonb,
     '{"vendor": "Cisco", "model": "Catalyst 9300"}'::jsonb),
    ('plc_001', 'Production Line PLC', 'plc', '192.168.1.100',
     '{"x": 150, "y": 100, "floor": "1", "building": "Factory"}'::jsonb,
     '{"vendor": "Siemens", "model": "S7-1500"}'::jsonb),
    ('sensor_001', 'Temperature Sensor 1', 'sensor', '192.168.1.200',
     '{"x": 200, "y": 150, "floor": "1", "building": "Factory"}'::jsonb,
     '{"vendor": "Honeywell", "type": "temperature"}'::jsonb)
ON CONFLICT (asset_id) DO NOTHING;

-- Insert sample topology
INSERT INTO topology (source_id, target_id, connection_type, bandwidth)
VALUES
    ('switch_001', 'plc_001', 'ethernet', 1000),
    ('switch_001', 'sensor_001', 'ethernet', 100)
ON CONFLICT (source_id, target_id) DO NOTHING;

-- ============================================================================
-- GRANTS (adjust based on your security requirements)
-- ============================================================================

-- Create application user (run separately with appropriate credentials)
-- CREATE USER nethealth_app WITH PASSWORD 'your_secure_password';
-- GRANT CONNECT ON DATABASE nethealth TO nethealth_app;
-- GRANT USAGE ON SCHEMA public TO nethealth_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO nethealth_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO nethealth_app;
