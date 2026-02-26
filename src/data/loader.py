import pandas as pd
import json
from typing import List, Dict
from pathlib import Path
from .schemas import MetricRecord, Asset

def load_metrics(file_path: str) -> List[MetricRecord]:
    """
    Load metrics from a CSV file.
    Expected CSV columns: timestamp, asset_id, metric_name, value, unit
    """
    df = pd.read_csv(file_path)
    
    # Ensure timestamp is datetime
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    records = []
    for _, row in df.iterrows():
        try:
            record = MetricRecord(
                timestamp=row['timestamp'],
                asset_id=row['asset_id'],
                metric_name=row['metric_name'],
                value=row['value'],
                unit=row.get('unit') # Optional column
            )
            records.append(record)
        except Exception as e:
            print(f"Error validating row {row}: {e}")
            
    return records

def load_assets(file_path: str) -> List[Asset]:
    """
    Load assets from a JSON file.
    """
    with open(file_path, 'r') as f:
        data = json.load(f)
        
    assets = []
    for item in data:
        try:
            asset = Asset(**item)
            assets.append(asset)
        except Exception as e:
            print(f"Error validating asset {item}: {e}")
            
    return assets
