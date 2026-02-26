"""
Granger Causality Engine

Proves directional influence between network metrics using time-series statistical analysis.
Goes beyond topology-based correlation to establish true cause-effect relationships.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime
from dataclasses import dataclass
from statsmodels.tsa.stattools import grangercausalitytests, adfuller
import warnings

warnings.filterwarnings('ignore')  # Suppress statsmodels warnings


@dataclass
class CausalEdge:
    """Proven causal relationship between metrics"""
    from_metric: str
    from_asset: str
    to_metric: str
    to_asset: str
    strength: float  # Confidence (1 - min_p_value)
    optimal_lag: int  # Time steps between cause and effect
    p_value: float
    test_type: str = "granger"
    
    def __repr__(self):
        return f"{self.from_asset}.{self.from_metric} → {self.to_asset}.{self.to_metric} (lag={self.optimal_lag}, p={self.p_value:.4f})"


class CausalGraph:
    """
    Data structure for storing and querying causal relationships
    """
    
    def __init__(self):
        """Initialize empty causal graph"""
        self.edges: List[CausalEdge] = []
        self._edge_map: Dict[Tuple[str, str], CausalEdge] = {}
    
    def add_edge(self, edge: CausalEdge):
        """Add a proven causal edge to the graph"""
        key = (f"{edge.from_asset}.{edge.from_metric}", 
               f"{edge.to_asset}.{edge.to_metric}")
        self.edges.append(edge)
        self._edge_map[key] = edge
    
    def get_causing_metrics(self, target_metric: str, target_asset: str) -> List[CausalEdge]:
        """
        Find all metrics that cause the target metric.
        
        Args:
            target_metric: Metric name (e.g., 'latency')
            target_asset: Asset ID
            
        Returns:
            List of causal edges pointing to target
        """
        causing = []
        for edge in self.edges:
            if edge.to_metric == target_metric and edge.to_asset == target_asset:
                causing.append(edge)
        
        # Sort by strength (highest confidence first)
        causing.sort(key=lambda e: e.strength, reverse=True)
        return causing
    
    def get_affected_metrics(self, source_metric: str, source_asset: str) -> List[CausalEdge]:
        """
        Find all metrics affected by the source metric.
        
        Args:
            source_metric: Metric name (e.g., 'crc_error')
            source_asset: Asset ID
            
        Returns:
            List of causal edges originating from source
        """
        affected = []
        for edge in self.edges:
            if edge.from_metric == source_metric and edge.from_asset == source_asset:
                affected.append(edge)
        
        affected.sort(key=lambda e: e.strength, reverse=True)
        return affected
    
    def get_edge_strength(self, from_key: str, to_key: str) -> float:
        """
        Get causal strength between two metrics.
        
        Args:
            from_key: Source metric key (asset.metric)
            to_key: Target metric key (asset.metric)
            
        Returns:
            Causal strength (0-1), or 0 if no edge exists
        """
        edge = self._edge_map.get((from_key, to_key))
        return edge.strength if edge else 0.0
    
    def get_optimal_lag(self, from_key: str, to_key: str) -> Optional[int]:
        """Get time delay for causal effect"""
        edge = self._edge_map.get((from_key, to_key))
        return edge.optimal_lag if edge else None
    
    def has_edge(self, from_key: str, to_key: str) -> bool:
        """Check if causal edge exists"""
        return (from_key, to_key) in self._edge_map
    
    def detect_feedback_loops(self) -> List[List[str]]:
        """
        Detect circular causation (A → B → A).
        
        Returns:
            List of feedback loops (each loop is a list of metric keys)
        """
        loops = []
        
        # Build adjacency list
        graph = {}
        for edge in self.edges:
            from_key = f"{edge.from_asset}.{edge.from_metric}"
            to_key = f"{edge.to_asset}.{edge.to_metric}"
            
            if from_key not in graph:
                graph[from_key] = []
            graph[from_key].append(to_key)
        
        # DFS to find cycles
        def find_cycles(node, path, visited):
            if node in path:
                # Found a cycle
                cycle_start = path.index(node)
                loops.append(path[cycle_start:])
                return
            
            if node in visited:
                return
            
            visited.add(node)
            path.append(node)
            
            for neighbor in graph.get(node, []):
                find_cycles(neighbor, path.copy(), visited)
        
        visited = set()
        for node in graph:
            find_cycles(node, [], visited)
        
        return loops
    
    def get_all_edges(self) -> List[CausalEdge]:
        """Get all causal edges"""
        return self.edges.copy()
    
    def __len__(self):
        """Number of causal edges"""
        return len(self.edges)
    
    def __repr__(self):
        return f"CausalGraph({len(self.edges)} edges)"


class CausalityEngine:
    """
    Determines true cause-effect relationships using Granger causality tests.
    
    Granger causality tests if past values of metric A help predict metric B
    beyond B's own history. This proves directional influence.
    """
    
    def __init__(self, significance_level: float = 0.05, max_lag: int = 5):
        """
        Initialize causality engine.
        
        Args:
            significance_level: P-value threshold for causality (default 0.05)
            max_lag: Maximum lag to test (default 5 timesteps)
        """
        self.significance_level = significance_level
        self.max_lag = max_lag
    
    def check_stationarity(self, timeseries: np.ndarray) -> Tuple[bool, float]:
        """
        Check if time series is stationary using Augmented Dickey-Fuller test.
        
        Args:
            timeseries: Time series data
            
        Returns:
            Tuple of (is_stationary, p_value)
        """
        if len(timeseries) < 12:
            # Not enough data for ADF test
            return False, 1.0
        
        try:
            result = adfuller(timeseries, autolag='AIC')
            p_value = result[1]
            is_stationary = p_value < 0.05
            return is_stationary, p_value
        except Exception:
            return False, 1.0
    
    def make_stationary(self, timeseries: np.ndarray) -> np.ndarray:
        """
        Make time series stationary using differencing.
        
        Args:
            timeseries: Non-stationary time series
            
        Returns:
            Differenced (stationary) time series
        """
        # First-order differencing
        diff = np.diff(timeseries)
        return diff
    
    def granger_test(
        self,
        metric_A_timeseries: np.ndarray,
        metric_B_timeseries: np.ndarray,
        max_lag: Optional[int] = None
    ) -> Dict:
        """
        Test if metric_A 'Granger-causes' metric_B.
        
        Tests if past values of A help predict B beyond B's own history.
        
        Args:
            metric_A_timeseries: Time series for potential cause
            metric_B_timeseries: Time series for potential effect
            max_lag: Maximum lag to test (uses self.max_lag if None)
            
        Returns:
            Dictionary with:
                - causes: bool (True if A causes B)
                - confidence: float (1 - min_p_value)
                - optimal_lag: int (time steps between cause and effect)
                - p_value: float (minimum p-value across lags)
                - interpretation: str (human-readable explanation)
        """
        if max_lag is None:
            max_lag = self.max_lag
        
        # Ensure same length
        min_len = min(len(metric_A_timeseries), len(metric_B_timeseries))
        A = metric_A_timeseries[-min_len:]
        B = metric_B_timeseries[-min_len:]
        
        # Need at least 30 points for reliable test
        if min_len < 30:
            return {
                'causes': False,
                'confidence': 0.0,
                'optimal_lag': 0,
                'p_value': 1.0,
                'interpretation': 'Insufficient data for Granger test (need ≥30 points)'
            }
        
        # Check stationarity
        is_stationary_A, _ = self.check_stationarity(A)
        is_stationary_B, _ = self.check_stationarity(B)
        
        # Make stationary if needed
        if not is_stationary_A:
            A = self.make_stationary(A)
        if not is_stationary_B:
            B = self.make_stationary(B)
        
        # Ensure same length after differencing
        min_len = min(len(A), len(B))
        A = A[-min_len:]
        B = B[-min_len:]
        
        # Adjust max_lag if needed
        max_lag = min(max_lag, min_len // 3)  # Rule of thumb: max_lag < T/3
        
        if max_lag < 1:
            return {
                'causes': False,
                'confidence': 0.0,
                'optimal_lag': 0,
                'p_value': 1.0,
                'interpretation': 'Time series too short for lag analysis'
            }
        
        try:
            # Run Granger causality test
            # Data format: [dependent_var, independent_var]
            data = np.column_stack([B, A])
            
            result = grangercausalitytests(data, maxlag=max_lag, verbose=False)
            
            # Extract p-values for each lag (using F-test)
            p_values = []
            for lag in range(1, max_lag + 1):
                # Get F-test p-value
                p_val = result[lag][0]['ssr_ftest'][1]
                p_values.append(p_val)
            
            # Find minimum p-value and corresponding lag
            min_p = min(p_values)
            optimal_lag = p_values.index(min_p) + 1
            
            # Determine if causal
            causes = min_p < self.significance_level
            confidence = 1 - min_p
            
            # Generate interpretation
            if causes:
                interpretation = f"Metric A affects B with {optimal_lag} timestep delay (p={min_p:.4f})"
            else:
                interpretation = f"No significant causal relationship detected (p={min_p:.4f})"
            
            return {
                'causes': causes,
                'confidence': confidence,
                'optimal_lag': optimal_lag,
                'p_value': min_p,
                'interpretation': interpretation
            }
        
        except Exception as e:
            return {
                'causes': False,
                'confidence': 0.0,
                'optimal_lag': 0,
                'p_value': 1.0,
                'interpretation': f'Granger test failed: {str(e)}'
            }
    
    def build_causal_graph(
        self,
        metrics_dict: Dict[str, Dict[str, np.ndarray]]
    ) -> CausalGraph:
        """
        Test all metric pairs to construct causal network.
        
        Args:
            metrics_dict: Dictionary mapping asset_id to dict of {metric_name: timeseries}
                Example: {
                    'switch-1': {'crc_error': [1,2,3,...], 'latency': [10,12,11,...]},
                    'plc-2': {'packet_loss': [0,1,0,...], 'latency': [15,20,18,...]}
                }
        
        Returns:
            CausalGraph with proven causal edges
        """
        causal_graph = CausalGraph()
        
        # Flatten metrics into list of (asset, metric, timeseries)
        all_metrics = []
        for asset_id, metrics in metrics_dict.items():
            for metric_name, timeseries in metrics.items():
                all_metrics.append((asset_id, metric_name, timeseries))
        
        # Test all pairs
        for i, (asset_a, metric_a, ts_a) in enumerate(all_metrics):
            for j, (asset_b, metric_b, ts_b) in enumerate(all_metrics):
                if i == j:
                    continue  # Skip self-loops
                
                # Test if A causes B
                result = self.granger_test(ts_a, ts_b)
                
                if result['causes']:
                    edge = CausalEdge(
                        from_metric=metric_a,
                        from_asset=asset_a,
                        to_metric=metric_b,
                        to_asset=asset_b,
                        strength=result['confidence'],
                        optimal_lag=result['optimal_lag'],
                        p_value=result['p_value'],
                        test_type='granger'
                    )
                    causal_graph.add_edge(edge)
        
        return causal_graph
    
    def get_causal_strength(
        self,
        metric_A_timeseries: np.ndarray,
        metric_B_timeseries: np.ndarray
    ) -> float:
        """
        Calculate strength of causal relationship (0-1).
        
        Args:
            metric_A_timeseries: Potential cause
            metric_B_timeseries: Potential effect
            
        Returns:
            Causal strength (1 - p_value)
        """
        result = self.granger_test(metric_A_timeseries, metric_B_timeseries)
        return result['confidence']
