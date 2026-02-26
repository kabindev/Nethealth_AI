from typing import Dict, Any

class L4TransportKPIs:
    """
    Calculates L4 Transport Layer Health Score (0-100).
    Metrics:
    - Retransmissions (Warning)
    - Connection Resets (Critical)
    """
    
    def calculate_score(self, metrics: Dict[str, float]) -> float:
        score = 100.0
        
        # 1. Retransmissions
        retrans = metrics.get('retransmissions', 0)
        if retrans > 50:
            score -= 30
        elif retrans > 10:
            score -= 10
            
        # 2. Connection Resets
        resets = metrics.get('connection_resets', 0)
        if resets > 5:
            score -= 40
        elif resets > 0:
            score -= 20
            
        return max(0.0, score)
