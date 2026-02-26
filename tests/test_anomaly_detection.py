import pandas as pd
import numpy as np
import pytest
from src.intelligence.anomaly_detector import AnomalyDetector

def test_anomaly_detection_logic():
    # Train on normal data
    np.random.seed(42)
    train_data = pd.DataFrame({
        'value': np.random.normal(10, 1, 100)
    })
    
    detector = AnomalyDetector(contamination=0.1)
    detector.train(train_data, ['value'])
    
    # Test on anomalies
    test_data = pd.DataFrame({
        'value': [10, 100, 10] # 100 is anomaly
    })
    
    results = detector.detect(test_data, ['value'])
    
    assert results.iloc[0]['is_anomaly'] == False
    assert results.iloc[1]['is_anomaly'] == True
    assert results.iloc[2]['is_anomaly'] == False
