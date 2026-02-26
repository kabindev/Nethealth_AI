import pandas as pd
from src.core.kpi_engine.baseline import BaselineCalculator
from src.core.kpi_engine.one_score import OneScoreCalculator

def test_baseline_calculation():
    calc = BaselineCalculator(window_size=3)
    data = pd.Series([10, 10, 10, 100])
    mean, std = calc.calculate_baseline(data)
    
    # After 3 values (10, 10, 10), mean should be 10, std 0.
    # The rolling applies to current window. 
    # Index 2: [10, 10, 10] -> mean 10.
    assert mean.iloc[2] == 10
    assert std.iloc[2] == 0

def test_one_score_calculation():
    osc = OneScoreCalculator()
    metrics = {
        "crc_error": 500, # Bad L1
        "link_flaps": 0,
        "rssi": -90, # Bad Signal
        "packet_loss": 0,
        "latency": 20,
        "reachability": 1,
        "retransmissions": 0,
        "connection_resets": 0
    }
    
    scores = osc.calculate_one_score(metrics)
    # L1 should be penalized heavily.
    # CRC > 100 -> -40
    # RSSI < -85 -> -30
    # L1 Score = 100 - 40 - 30 = 30
    
    assert scores['l1_score'] == 30.0
    assert scores['l3_score'] == 100.0 # No L3 issues
    assert scores['l4_score'] == 100.0 # No L4 issues
    
    # One Score = 30*0.4 + 100*0.4 + 100*0.2 = 12 + 40 + 20 = 72
    assert scores['one_score'] == 72.0
