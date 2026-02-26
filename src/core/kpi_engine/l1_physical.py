from typing import Dict, Any

class L1PhysicalKPIs:
    """
    Calculates L1 Physical Layer Health Score (0-100).
    Metrics:
    - CRC Error Rate (Critical)
    - Link Flaps (Critical)
    - Signal Quality / RSSI (Warning)
    """
    
    def calculate_score(self, metrics: Dict[str, float]) -> float:
        score = 100.0
        
        # 1. CRC Errors
        crc = metrics.get('crc_error', 0)
        if crc > 100:
            score -= 40
        elif crc > 10:
            score -= 20
        elif crc > 0:
            score -= 5
            
        # 2. Link Flaps
        flaps = metrics.get('link_flaps', 0)
        if flaps > 10:
            score -= 40
        elif flaps > 2:
            score -= 20
            
        # 3. Signal Quality (RSSI) - usually negative, e.g. -60dBm is good, -90 is bad
        rssi = metrics.get('rssi', -50) # default good signal
        if rssi < -85:
            score -= 30
        elif rssi < -75:
            score -= 10
            
        return max(0.0, score)
