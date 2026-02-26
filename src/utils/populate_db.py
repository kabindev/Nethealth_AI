"""
Database Population Script

Populates the local database (SQLite/PostgreSQL) with synthetic data
to simulate a Production environment.
"""

import sys
import os
import pandas as pd
from datetime import datetime
import logging
from sqlalchemy import select

# Add project root to path
sys.path.append(os.getcwd())

from src.database.connection import init_database
from src.database.models import Asset, Metric, Alert
from src.utils.data_generator import NetworkDataGenerator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def populate_database(num_scenarios=5, points_per_scenario=100):
    """
    Populate database with synthetic data
    """
    logger.info("Initializing database...")
    db_manager = init_database()
    
    logger.info(f"Generating synthetic data ({num_scenarios} scenarios)...")
    generator = NetworkDataGenerator()
    metrics_df, ground_truths = generator.generate_dataset(
        num_scenarios=num_scenarios, 
        num_points=points_per_scenario,
        multi_asset_ratio=0.3
    )
    
    session = db_manager.Session()
    
    try:
        # 1. Create Assets
        logger.info("Creating assets...")
        unique_assets = metrics_df['asset_id'].unique()
        
        existing_assets = {a.asset_id for a in session.query(Asset.asset_id).all()}
        
        for asset_id in unique_assets:
            if asset_id not in existing_assets:
                # Determine asset type based on naming convention
                asset_type = 'unknown'
                if 'switch' in asset_id:
                    asset_type = 'switch'
                elif 'plc' in asset_id:
                    asset_type = 'plc'
                elif 'hmi' in asset_id:
                    asset_type = 'hmi'
                elif 'firewall' in asset_id:
                    asset_type = 'firewall'
                
                # Assign protocol based on type
                protocol = 'snmp'
                if asset_type == 'plc':
                    protocol = 'modbus'
                elif asset_type == 'hmi':
                    protocol = 'profinet'
                
                asset = Asset(
                    asset_id=asset_id,
                    name=asset_id.replace('-', ' ').title(),
                    type=asset_type,
                    status='active',
                    ip_address=f"192.168.1.{len(existing_assets) + 10}",
                    location={"floor": "1", "zone": "production"},
                    meta_data={"generated": True, "protocol": protocol}
                )
                session.add(asset)
                existing_assets.add(asset_id)
        
        session.commit()
        logger.info(f"Ensured {len(existing_assets)} assets exist.")
        
        # 2. Insert Metrics
        logger.info("Inserting metrics (this may take a moment)...")
        # Bulk insert is faster
        metrics_data = []
        for _, row in metrics_df.iterrows():
            # Check if metric already exists to avoid PK violation if re-running
            # For simplicity, we'll skip check and use ignore/merge if possible, 
            # but standard SQLAlchemy doesn't support 'INSERT IGNORE' easily across dialects.
            # We will just insert new data.
            pass
        
        # Actually, let's just use to_sql if possible? 
        # But we defined models. Let's use objects for now, or raw SQL if too slow.
        # Given it's a demo, 5 scenarios * 100 points * ~10 metrics = 5000 rows. Fast enough.
        
        # Clear existing metrics to avoid duplicates for this demo script
        session.query(Metric).delete()
        session.commit()
        
        batch_size = 1000
        objects = []
        
        for idx, row in metrics_df.iterrows():
            metric = Metric(
                time=row['timestamp'],
                asset_id=row['asset_id'],
                metric_name=row['metric_name'],
                value=row['value'],
                unit=row['unit']
            )
            objects.append(metric)
            
            if len(objects) >= batch_size:
                session.bulk_save_objects(objects)
                objects = []
                
        if objects:
            session.bulk_save_objects(objects)
            
        session.commit()
        logger.info(f"Inserted {len(metrics_df)} metric records.")
        
        # 3. Create Alerts based on Ground Truth
        logger.info("Creating alerts from ground truth...")
        session.query(Alert).delete()
        
        for gt in ground_truths:
            start_time = datetime.fromisoformat(gt['fault_start_time'])
            
            # Create an alert
            alert = Alert(
                time=start_time,
                asset_id=gt['affected_asset'],
                alert_type=gt['fault_type'],
                severity='critical' if gt['severity'] > 0.8 else 'warning',
                description=f"Detected {gt['fault_type']} on {gt['affected_asset']} (Severity: {gt['severity']:.2f})",
                resolved=False,
                meta_data=gt
            )
            session.add(alert)
            
        session.commit()
        logger.info(f"Created {len(ground_truths)} alerts.")
        
        # 4. Create SQLite Views (Mocking TimescaleDB primitives)
        logger.info("Creating SQLite views...")
        from sqlalchemy import text
        
        # latest_metrics view
        session.execute(text("DROP VIEW IF EXISTS latest_metrics"))
        session.execute(text("""
            CREATE VIEW latest_metrics AS
            SELECT m1.*
            FROM metrics m1
            JOIN (
                SELECT asset_id, metric_name, MAX(time) as max_time
                FROM metrics
                GROUP BY asset_id, metric_name
            ) m2 ON m1.asset_id = m2.asset_id 
                AND m1.metric_name = m2.metric_name 
                AND m1.time = m2.max_time
        """))
        
        # metrics_hourly view
        session.execute(text("DROP VIEW IF EXISTS metrics_hourly"))
        session.execute(text("""
            CREATE VIEW metrics_hourly AS
            SELECT 
                strftime('%Y-%m-%d %H:00:00', time) as bucket,
                asset_id,
                metric_name,
                AVG(value) as avg_value,
                MAX(value) as max_value,
                MIN(value) as min_value,
                0 as stddev_value,
                COUNT(*) as sample_count
            FROM metrics
            GROUP BY bucket, asset_id, metric_name
        """))
        
        # metrics_daily view
        session.execute(text("DROP VIEW IF EXISTS metrics_daily"))
        session.execute(text("""
            CREATE VIEW metrics_daily AS
            SELECT 
                strftime('%Y-%m-%d 00:00:00', time) as bucket,
                asset_id,
                metric_name,
                AVG(value) as avg_value,
                MAX(value) as max_value,
                MIN(value) as min_value,
                0 as stddev_value,
                COUNT(*) as sample_count
            FROM metrics
            GROUP BY bucket, asset_id, metric_name
        """))

        # active_alerts_summary view
        session.execute(text("DROP VIEW IF EXISTS active_alerts_summary"))
        session.execute(text("""
            CREATE VIEW active_alerts_summary AS
            SELECT severity, alert_type, COUNT(*) as count
            FROM alerts
            WHERE resolved = 0
            GROUP BY severity, alert_type
        """))
        
        session.commit()
        logger.info("Views created successfully.")
        
        logger.info("Database population complete!")
        print("\n[SUCCESS] Production database is ready.")
        print(f"Location: {db_manager.database_url}")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error populating database: {e}")
        raise
    finally:
        session.close()
        db_manager.close()

if __name__ == "__main__":
    populate_database()
