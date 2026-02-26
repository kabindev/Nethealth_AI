import sys
import os

# Add project root to python path
project_root = os.getcwd()
if project_root not in sys.path:
    sys.path.append(project_root)

from src.data.loader import load_metrics, load_assets

def test_loading():
    print("Testing Data Loading...")
    
    # Test Metrics
    metrics_file = os.path.join(project_root, 'data/raw/metrics_timeseries.csv')
    try:
        metrics = load_metrics(metrics_file)
        print(f"Loaded {len(metrics)} metrics.")
        for m in metrics:
            print(f" - {m}")
    except Exception as e:
        print(f"Failed to load metrics: {e}")

    # Test Assets
    assets_file = os.path.join(project_root, 'data/raw/assets.json')
    try:
        assets = load_assets(assets_file)
        print(f"Loaded {len(assets)} assets.")
        for a in assets:
            print(f" - {a}")
    except Exception as e:
        print(f"Failed to load assets: {e}")

if __name__ == "__main__":
    test_loading()
