from .l1_physical import L1PhysicalKPIs
from .l3_network import L3NetworkKPIs
from .l4_transport import L4TransportKPIs
from .l7_application import L7ApplicationKPIs
from typing import Dict

class OneScoreCalculator:
    def __init__(self):
        self.l1 = L1PhysicalKPIs()
        self.l3 = L3NetworkKPIs()
        self.l4 = L4TransportKPIs()
        self.l7 = L7ApplicationKPIs()
        
    def calculate_one_score(self, metrics: Dict[str, float]) -> Dict[str, float]:
        """
        Aggregates layer scores into a single ONE Health Score.
        Weights: L1 (30%), L3 (30%), L4 (20%), L7 (20%)
        """
        s1 = self.l1.calculate_score(metrics)
        s3 = self.l3.calculate_score(metrics)
        s4 = self.l4.calculate_score(metrics)
        s7 = self.l7.calculate_score(metrics)
        
        # Weighted Aggregation
        final_score = (s1 * 0.3) + (s3 * 0.3) + (s4 * 0.2) + (s7 * 0.2)
        
        # Critical Veto Logic: If any layer is failing (< 50), the overall score cannot be good
        min_layer_score = min(s1, s3, s4, s7)
        if min_layer_score < 50:
            final_score = min(final_score, 59.0)
        
        return {
            "one_score": round(final_score, 1),
            "l1_score": s1,
            "l3_score": s3,
            "l4_score": s4,
            "l7_score": s7
        }
