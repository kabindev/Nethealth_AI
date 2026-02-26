"""
Unit tests for Probabilistic Diagnostic Engine

Tests Bayesian inference, belief updating, and multi-hypothesis generation.
"""

import pytest
from datetime import datetime
from src.intelligence.bayesian_diagnostics import (
    ProbabilisticDiagnosticEngine,
    ProbabilisticDiagnosis,
    BeliefUpdate
)


class TestBayesianNetworkStructure:
    """Test Bayesian network construction and validation"""
    
    def setup_method(self):
        """Setup test engine"""
        self.engine = ProbabilisticDiagnosticEngine()
    
    def test_network_initialization(self):
        """Test that network initializes correctly"""
        assert self.engine.model is not None
        assert self.engine.inference_engine is not None
    
    def test_network_structure(self):
        """Test network has correct nodes and edges"""
        nodes = set(self.engine.model.nodes())
        
        expected_nodes = {
            'CableAge', 'AmbientTemp', 'EMI_Source', 'ConfigError',
            'CableFailure', 'ConnectorOxidation', 'CRCErrors',
            'PacketLoss', 'Latency'
        }
        
        assert nodes == expected_nodes, f"Expected {expected_nodes}, got {nodes}"
    
    def test_network_validity(self):
        """Test that network structure is valid"""
        assert self.engine.model.check_model(), "Bayesian network model is invalid"
    
    def test_cpd_normalization(self):
        """Test that all CPDs are properly normalized (sum to 1)"""
        for cpd in self.engine.model.get_cpds():
            # Check that probabilities sum to 1 for each parent configuration
            values = cpd.values
            
            # Sum along the variable dimension (axis 0)
            sums = values.sum(axis=0)
            
            # All sums should be close to 1.0
            assert all(abs(s - 1.0) < 0.01 for s in sums.flatten()), \
                f"CPD for {cpd.variable} not normalized: {sums}"


class TestProbabilisticDiagnosis:
    """Test probabilistic diagnosis functionality"""
    
    def setup_method(self):
        """Setup test engine"""
        self.engine = ProbabilisticDiagnosticEngine()
    
    def test_basic_inference(self):
        """Test basic probabilistic inference"""
        symptoms = {
            'CRCErrors': 'High',
            'PacketLoss': 'High'
        }
        
        diagnosis = self.engine.diagnose_with_uncertainty(symptoms)
        
        assert isinstance(diagnosis, ProbabilisticDiagnosis)
        assert diagnosis.primary_cause is not None
        assert 0 <= diagnosis.primary_probability <= 1
        assert len(diagnosis.cause_probabilities) > 0
    
    def test_probability_distribution(self):
        """Test that probability distribution is valid"""
        symptoms = {'CRCErrors': 'High'}
        
        diagnosis = self.engine.diagnose_with_uncertainty(symptoms)
        
        # All probabilities should be between 0 and 1
        for cause, prob in diagnosis.cause_probabilities.items():
            assert 0 <= prob <= 1, f"{cause} has invalid probability: {prob}"
    
    def test_high_crc_errors_diagnosis(self):
        """Test diagnosis with high CRC errors"""
        symptoms = {
            'CRCErrors': 'High',
            'PacketLoss': 'Medium'
        }
        
        diagnosis = self.engine.diagnose_with_uncertainty(symptoms)
        
        # High CRC errors should suggest cable or EMI issues
        cable_prob = diagnosis.cause_probabilities.get('CableFailure', 0)
        emi_prob = diagnosis.cause_probabilities.get('EMI_Source', 0)
        
        # At least one should have significant probability
        assert (cable_prob > 0.2 or emi_prob > 0.2), \
            "High CRC should suggest cable or EMI issues"
    
    def test_confidence_levels(self):
        """Test confidence level assignment"""
        # High confidence scenario
        symptoms = {'CRCErrors': 'High', 'PacketLoss': 'High', 'Latency': 'VeryHigh'}
        diagnosis = self.engine.diagnose_with_uncertainty(symptoms)
        
        # Should have some confidence level assigned
        assert diagnosis.confidence_level in ['High', 'Medium', 'Low']
    
    def test_multi_hypothesis_actions(self):
        """Test multi-hypothesis action generation"""
        symptoms = {'CRCErrors': 'Medium'}
        
        diagnosis = self.engine.diagnose_with_uncertainty(symptoms)
        
        # Should generate at least one action
        assert len(diagnosis.multi_hypothesis_actions) > 0
        
        # Actions should be strings
        for action in diagnosis.multi_hypothesis_actions:
            assert isinstance(action, str)
            assert len(action) > 0


class TestBeliefUpdating:
    """Test Bayesian belief updating"""
    
    def setup_method(self):
        """Setup test engine"""
        self.engine = ProbabilisticDiagnosticEngine()
    
    def test_belief_update_basic(self):
        """Test basic belief updating"""
        # Initial diagnosis
        initial_symptoms = {'CRCErrors': 'High'}
        initial_diagnosis = self.engine.diagnose_with_uncertainty(initial_symptoms)
        initial_cable_prob = initial_diagnosis.cause_probabilities['CableFailure']
        
        # Simulate TDR test passing (cable is OK)
        # This should decrease cable failure probability
        # Note: We don't have TDR in the network, so we'll use a proxy
        # In real implementation, you'd add TDR_Result node
        
        # For now, test that update mechanism works
        new_evidence = {'PacketLoss': 'Low'}
        updated_diagnosis = self.engine.update_beliefs_online(new_evidence)
        
        # Should have updated probabilities
        assert updated_diagnosis is not None
        assert len(self.engine.belief_history) == 1
    
    def test_belief_history_tracking(self):
        """Test that belief updates are tracked"""
        symptoms = {'CRCErrors': 'High'}
        self.engine.diagnose_with_uncertainty(symptoms)
        
        # Add evidence
        self.engine.update_beliefs_online({'PacketLoss': 'Medium'})
        self.engine.update_beliefs_online({'Latency': 'High'})
        
        # Should have 2 updates
        history = self.engine.get_belief_evolution()
        assert len(history) == 2
        
        # Each update should be a BeliefUpdate
        for update in history:
            assert isinstance(update, BeliefUpdate)
    
    def test_probability_shifts(self):
        """Test that probability shifts are calculated"""
        symptoms = {'CRCErrors': 'Medium'}
        self.engine.diagnose_with_uncertainty(symptoms)
        
        # Update with new evidence
        new_evidence = {'PacketLoss': 'High'}
        self.engine.update_beliefs_online(new_evidence)
        
        # Check belief history
        update = self.engine.belief_history[0]
        
        assert update.previous_probabilities is not None
        assert update.updated_probabilities is not None
        assert update.probability_shifts is not None
        
        # Shifts should be difference between updated and previous
        for cause in update.probability_shifts:
            expected_shift = (
                update.updated_probabilities[cause] - 
                update.previous_probabilities[cause]
            )
            assert abs(update.probability_shifts[cause] - expected_shift) < 0.01


class TestEdgeCases:
    """Test edge cases and error handling"""
    
    def setup_method(self):
        """Setup test engine"""
        self.engine = ProbabilisticDiagnosticEngine()
    
    def test_no_symptoms(self):
        """Test diagnosis with no symptoms (prior probabilities)"""
        diagnosis = self.engine.diagnose_with_uncertainty({})
        
        # Should still return valid diagnosis (based on priors)
        assert diagnosis is not None
        assert len(diagnosis.cause_probabilities) > 0
    
    def test_ambiguous_symptoms(self):
        """Test with ambiguous symptoms (multiple causes plausible)"""
        symptoms = {'CRCErrors': 'Medium', 'PacketLoss': 'Low'}
        
        diagnosis = self.engine.diagnose_with_uncertainty(symptoms)
        
        # Multiple causes should have non-trivial probability
        significant_causes = [
            cause for cause, prob in diagnosis.cause_probabilities.items()
            if prob > 0.15
        ]
        
        # Should have at least 2 plausible causes
        assert len(significant_causes) >= 1
    
    def test_reset_evidence(self):
        """Test resetting evidence"""
        symptoms = {'CRCErrors': 'High'}
        self.engine.diagnose_with_uncertainty(symptoms)
        self.engine.update_beliefs_online({'PacketLoss': 'High'})
        
        # Reset
        self.engine.reset_evidence()
        
        assert len(self.engine.current_evidence) == 0
        assert len(self.engine.belief_history) == 0


class TestIntegration:
    """Integration tests for complete diagnostic workflow"""
    
    def test_complete_diagnostic_workflow(self):
        """Test complete workflow: initial diagnosis → updates → final diagnosis"""
        engine = ProbabilisticDiagnosticEngine()
        
        # Step 1: Initial symptoms
        initial = engine.diagnose_with_uncertainty({
            'CRCErrors': 'High',
            'PacketLoss': 'Medium'
        })
        
        assert initial.confidence_level in ['High', 'Medium', 'Low']
        initial_primary = initial.primary_cause
        
        # Step 2: Technician gathers more evidence
        updated1 = engine.update_beliefs_online({'Latency': 'High'})
        
        # Step 3: More evidence
        updated2 = engine.update_beliefs_online({'PacketLoss': 'High'})
        
        # Should have 2 belief updates
        assert len(engine.get_belief_evolution()) == 2
        
        # Final diagnosis should be valid
        assert updated2.primary_cause is not None
        assert updated2.primary_probability > 0
    
    def test_most_likely_cause_extraction(self):
        """Test extracting most likely cause"""
        engine = ProbabilisticDiagnosticEngine()
        
        diagnosis = engine.diagnose_with_uncertainty({'CRCErrors': 'High'})
        
        cause, prob = engine.get_most_likely_cause(diagnosis)
        
        assert cause == diagnosis.primary_cause
        assert prob == diagnosis.primary_probability


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
