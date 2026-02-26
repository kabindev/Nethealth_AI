import sys
import os
import pandas as pd
import numpy as np

# Add project root
sys.path.append(os.getcwd())

from src.intelligence.anomaly_detector import AnomalyDetector

def test_anomaly():
    print("\n--- Testing Anomaly Detector ---")
    
    # 1. Generate Training Data (Normal)
    # 100 samples, mean=10, std=1
    np.random.seed(42)
    train_data = pd.DataFrame({
        'crc_error': np.random.normal(0, 1, 100), # mostly 0
        'packet_loss': np.random.normal(0, 0.5, 100),
        'latency': np.random.normal(20, 2, 100)
    })
    # Ensure non-negative roughly
    train_data[train_data < 0] = 0
    
    print("Training on 'normal' data...")
    detector = AnomalyDetector(contamination=0.1)
    detector.train(train_data, ['crc_error', 'packet_loss', 'latency'])
    
    # 2. Generate Test Data (With Anomalies)
    test_data = pd.DataFrame({
        'crc_error': [0, 500, 0, 10], # 500 is huge anomaly
        'packet_loss': [0, 20, 0, 1],
        'latency': [20, 1000, 19, 21]
    })
    
    print("\nTesting on mixed data:")
    results = detector.detect(test_data, ['crc_error', 'packet_loss', 'latency'])
    
    print(results[['crc_error', 'anomaly_score', 'is_anomaly']])
    
    # Check if index 1 (the huge anomaly) is detected
    assert results.iloc[1]['is_anomaly'] == True
    print("\nAnomaly detected correctly!")

if __name__ == "__main__":
    test_anomaly()
