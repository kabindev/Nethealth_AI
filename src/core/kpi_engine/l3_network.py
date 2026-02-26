from typing import Dict, Any

class L3NetworkKPIs:
    """
    Calculates L3 Network Layer Health Score (0-100).
    Metrics:
    - Packet Loss % (Critical)
    - Latency ms (Warning)
    - Reachability (Critical)
    """
    
    def calculate_score(self, metrics: Dict[str, float]) -> float:
        score = 100.0
        
        # 1. Reachability (Boolean 0 or 1, or percent)
        reachable = metrics.get('reachability', 1) 
        if reachable == 0:
            return 0.0 # Total failure
            
        # 2. Packet Loss (%)
        loss = metrics.get('packet_loss', 0)
        if loss > 20:
            score -= 50
        elif loss > 5:
            score -= 30
        elif loss > 1:
            score -= 10
            
        # 3. Dropped Packets (Critical for Firewall/Router)
        dropped = metrics.get('dropped_packets', 0)
        if dropped > 1000:
            score -= 60
        elif dropped > 100:
            score -= 30
        elif dropped > 0:
            score -= 10

        # 4. Latency (ms)
        latency = metrics.get('latency', 0)
        if latency > 200:
            score -= 30
        elif latency > 100:
            score -= 10
            
        return max(0.0, score)
