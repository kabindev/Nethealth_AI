from typing import Dict

class L7ApplicationKPIs:
    """
    Calculates L7 Application Layer Health Score (0-100).
    Metrics:
    - CPU Usage (Critical)
    - Memory Usage (Warning/Critical)
    - Disk I/O (Warning)
    """

    def calculate_score(self, metrics: Dict[str, float]) -> float:
        score = 100.0

        # 1. CPU Usage
        cpu = metrics.get('cpu_usage', 0)
        if cpu > 95:
            score -= 40
        elif cpu > 90:
            score -= 20
        elif cpu > 80:
            score -= 10

        # 2. Memory Usage
        mem = metrics.get('memory_usage', 0)
        if mem > 95:
            score -= 30
        elif mem > 90:
            score -= 15
        elif mem > 85:
            score -= 5

        # 3. Disk I/O (simplified, usually % utilization or wait time)
        disk = metrics.get('disk_io', 0)
        if disk > 95:
            score -= 20
        elif disk > 90:
            score -= 10

        return max(0.0, score)
