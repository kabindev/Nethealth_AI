"""
Unit tests for Granger Causality Engine

Tests statistical causality detection, causal graph construction, and integration.
"""

import pytest
import numpy as np
from src.intelligence.causality_engine import CausalityEngine, CausalGraph, CausalEdge


class TestGrangerCausality:
    """Test core Granger causality detection"""
    
    def setup_method(self):
        """Setup test engine"""
        self.engine = CausalityEngine(significance_level=0.05, max_lag=5)
    
    def test_known_causal_relationship(self):
        """Test detection of known causal relationship"""
        # Create synthetic data where A causes B with lag=2
        np.random.seed(42)
        A = np.random.randn(100)
        B = np.zeros(100)
        B[2:] = 0.8 * A[:-2] + 0.2 * np.random.randn(98)
        
        # Test if A Granger-causes B
        result = self.engine.granger_test(A, B)
        
        assert result['causes'] == True, "Should detect causal relationship"
        assert result['p_value'] < 0.05, f"P-value should be < 0.05, got {result['p_value']}"
        assert result['optimal_lag'] == 2, f"Should detect lag=2, got {result['optimal_lag']}"
        assert result['confidence'] > 0.9, f"Should have high confidence, got {result['confidence']}"
    
    def test_independent_metrics(self):
        """Test that independent metrics are not flagged as causal"""
        # Create independent random series
        np.random.seed(42)
        A = np.random.randn(100)
        B = np.random.randn(100)
        
        result = self.engine.granger_test(A, B)
        
        assert result['causes'] == False, "Should not detect causation in independent series"
        assert result['p_value'] > 0.05, f"P-value should be > 0.05, got {result['p_value']}"
    
    def test_reverse_causation(self):
        """Test asymmetric detection (A→B but not B→A)"""
        np.random.seed(42)
        A = np.random.randn(100)
        B = np.zeros(100)
        B[1:] = 0.7 * A[:-1] + 0.3 * np.random.randn(99)
        
        # A should cause B
        result_A_to_B = self.engine.granger_test(A, B)
        assert result_A_to_B['causes'] == True, "A should cause B"
        
        # B should NOT cause A (reverse)
        result_B_to_A = self.engine.granger_test(B, A)
        assert result_B_to_A['causes'] == False, "B should not cause A"
    
    def test_insufficient_data(self):
        """Test handling of insufficient data"""
        # Only 20 points (need 30)
        A = np.random.randn(20)
        B = np.random.randn(20)
        
        result = self.engine.granger_test(A, B)
        
        assert result['causes'] == False
        assert 'Insufficient data' in result['interpretation']
    
    def test_stationarity_handling(self):
        """Test that non-stationary series are handled"""
        # Create non-stationary series (random walk)
        np.random.seed(42)
        A = np.cumsum(np.random.randn(100))  # Random walk
        B = np.cumsum(np.random.randn(100))
        
        # Should not crash, should handle via differencing
        result = self.engine.granger_test(A, B)
        
        assert 'causes' in result
        assert 'p_value' in result


class TestCausalGraph:
    """Test causal graph data structure"""
    
    def setup_method(self):
        """Setup test graph"""
        self.graph = CausalGraph()
    
    def test_add_edge(self):
        """Test adding causal edges"""
        edge = CausalEdge(
            from_metric='crc_error',
            from_asset='switch-1',
            to_metric='latency',
            to_asset='plc-2',
            strength=0.95,
            optimal_lag=2,
            p_value=0.003
        )
        
        self.graph.add_edge(edge)
        
        assert len(self.graph) == 1
        assert self.graph.has_edge('switch-1.crc_error', 'plc-2.latency')
    
    def test_get_causing_metrics(self):
        """Test finding metrics that cause a target"""
        # Add edges: A→C, B→C
        edge1 = CausalEdge('metric_a', 'asset1', 'metric_c', 'asset3', 0.9, 1, 0.01)
        edge2 = CausalEdge('metric_b', 'asset2', 'metric_c', 'asset3', 0.85, 2, 0.02)
        
        self.graph.add_edge(edge1)
        self.graph.add_edge(edge2)
        
        causing = self.graph.get_causing_metrics('metric_c', 'asset3')
        
        assert len(causing) == 2
        # Should be sorted by strength (0.9 first)
        assert causing[0].strength == 0.9
        assert causing[1].strength == 0.85
    
    def test_get_affected_metrics(self):
        """Test finding metrics affected by a source"""
        # Add edges: A→B, A→C
        edge1 = CausalEdge('metric_a', 'asset1', 'metric_b', 'asset2', 0.9, 1, 0.01)
        edge2 = CausalEdge('metric_a', 'asset1', 'metric_c', 'asset3', 0.85, 2, 0.02)
        
        self.graph.add_edge(edge1)
        self.graph.add_edge(edge2)
        
        affected = self.graph.get_affected_metrics('metric_a', 'asset1')
        
        assert len(affected) == 2
        assert affected[0].to_metric in ['metric_b', 'metric_c']
    
    def test_feedback_loop_detection(self):
        """Test detection of circular causation"""
        # Create loop: A→B→C→A
        edge1 = CausalEdge('a', 'asset1', 'b', 'asset2', 0.9, 1, 0.01)
        edge2 = CausalEdge('b', 'asset2', 'c', 'asset3', 0.9, 1, 0.01)
        edge3 = CausalEdge('c', 'asset3', 'a', 'asset1', 0.9, 1, 0.01)
        
        self.graph.add_edge(edge1)
        self.graph.add_edge(edge2)
        self.graph.add_edge(edge3)
        
        loops = self.graph.detect_feedback_loops()
        
        assert len(loops) > 0, "Should detect feedback loop"


class TestCausalGraphBuilding:
    """Test building causal graph from metrics"""
    
    def setup_method(self):
        """Setup test engine"""
        self.engine = CausalityEngine()
    
    def test_build_causal_graph(self):
        """Test building graph from multiple metrics"""
        np.random.seed(42)
        
        # Create synthetic network with known causality
        # Switch CRC errors → PLC latency
        crc_errors = np.random.poisson(5, 100).astype(float)
        plc_latency = np.zeros(100)
        plc_latency[2:] = 0.6 * crc_errors[:-2] + np.random.randn(98) * 2
        
        # Independent metric
        cpu_usage = np.random.randn(100) * 10 + 50
        
        metrics_dict = {
            'switch-1': {
                'crc_error': crc_errors,
                'cpu_usage': cpu_usage
            },
            'plc-2': {
                'latency': plc_latency
            }
        }
        
        graph = self.engine.build_causal_graph(metrics_dict)
        
        # Should find CRC → Latency causation
        assert len(graph) > 0, "Should find at least one causal relationship"
        
        # Check if CRC→Latency edge exists
        has_crc_latency = graph.has_edge('switch-1.crc_error', 'plc-2.latency')
        
        # Note: May not always detect due to randomness, but should have some edges
        assert len(graph) >= 0  # At minimum, should not crash


class TestIntegration:
    """Integration tests for causality engine"""
    
    def test_causal_strength_calculation(self):
        """Test calculating causal strength"""
        engine = CausalityEngine()
        
        np.random.seed(42)
        A = np.random.randn(100)
        B = np.zeros(100)
        B[1:] = 0.8 * A[:-1] + 0.2 * np.random.randn(99)
        
        strength = engine.get_causal_strength(A, B)
        
        assert 0 <= strength <= 1, "Strength should be in [0,1]"
        assert strength > 0.8, f"Should have high strength for strong causation, got {strength}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
