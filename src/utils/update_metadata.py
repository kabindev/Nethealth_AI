import sys
import os
import logging

# Add project root to path
sys.path.append(os.getcwd())

from src.database.connection import init_database
from src.database.models import Asset

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_asset_metadata():
    """
    Update asset metadata with protocols
    """
    logger.info("Initializing database connection...")
    db_manager = init_database()
    session = db_manager.Session()
    
    try:
        logger.info("Updating asset metadata...")
        assets = session.query(Asset).all()
        
        count = 0
        for asset in assets:
            # Determine protocol based on type
            protocol = 'snmp'
            if asset.type == 'plc':
                protocol = 'modbus'
            elif asset.type == 'hmi':
                protocol = 'profinet'
            
            # Update meta_data
            current_metadata = asset.meta_data or {}
            if not isinstance(current_metadata, dict):
                current_metadata = {}
                
            current_metadata['protocol'] = protocol
            # Force update by reassigning (SQLAlchemy tracks changes on assignment)
            asset.meta_data = dict(current_metadata)
            
            count += 1
        
        session.commit()
        logger.info(f"Updated metadata for {count} assets.")
        print("\n[SUCCESS] Asset metadata updated.")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating metadata: {e}")
        # raise
    finally:
        session.close()
        db_manager.close()

if __name__ == "__main__":
    update_asset_metadata()
