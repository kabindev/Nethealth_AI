"""
Probabilistic Diagnostic Engine using Bayesian Networks

Models uncertainty in fault diagnosis, provides probability distributions over
root causes, and updates beliefs as new evidence arrives during troubleshooting.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass, field

from pgmpy.models import DiscreteBayesianNetwork
from pgmpy.factors.discrete import TabularCPD
from pgmpy.inference import VariableElimination


@dataclass
class ProbabilisticDiagnosis:
    """Diagnosis with probability distribution over causes"""
    anomaly_id: str
    timestamp: datetime
    cause_probabilities: Dict[str, float]  # {cause: probability}
    primary_cause: str  # Highest probability
    primary_probability: float
    multi_hypothesis_actions: List[str]
    explanation: str
    confidence_level: str  # "High" if primary > 60%, "Medium" 40-60%, "Low" < 40%
    evidence_used: Dict[str, str] = field(default_factory=dict)


@dataclass
class BeliefUpdate:
    """Record of belief updating"""
    diagnosis_id: str
    timestamp: datetime
    new_evidence: Dict[str, str]  # {variable: observed_value}
    previous_probabilities: Dict[str, float]
    updated_probabilities: Dict[str, float]
    probability_shifts: Dict[str, float]  # Change in probability
    interpretation: str


class ProbabilisticDiagnosticEngine:
    """
    Bayesian Network-based diagnostic engine for uncertainty modeling.
    
    Models causal relationships between environmental factors, component failures,
    and symptoms. Provides probability distributions over root causes and updates
    beliefs as new evidence arrives.
    """
    
    def __init__(self):
        """Initialize Bayesian network with industrial network failure modes"""
        self.model = None
        self.inference_engine = None
        self.belief_history: List[BeliefUpdate] = []
        self.current_evidence: Dict[str, str] = {}
        
        # Build the Bayesian network
        self._build_network()
    
    def _build_network(self):
        """
        Construct Bayesian network structure and conditional probability tables.
        
        Network Structure:
        - Environmental factors → Component failures → Symptoms
        - Example: CableAge → CableFailure → CRCErrors → PacketLoss
        """
        # Define network structure (edges represent causal relationships)
        self.model = DiscreteBayesianNetwork([
            # Environmental factors → Component failures
            ('CableAge', 'CableFailure'),
            ('AmbientTemp', 'CableFailure'),
            ('AmbientTemp', 'ConnectorOxidation'),
            
            # Component failures → Symptoms
            ('CableFailure', 'CRCErrors'),
            ('ConnectorOxidation', 'CRCErrors'),
            ('EMI_Source', 'CRCErrors'),
            ('ConfigError', 'PacketLoss'),
            ('CRCErrors', 'PacketLoss'),
            
            # Symptom propagation
            ('PacketLoss', 'Latency'),
        ])
        
        # Define Conditional Probability Tables (CPDs)
        self._define_cpds()
        
        # Validate model
        assert self.model.check_model(), "Bayesian network model is invalid"
        
        # Initialize inference engine
        self.inference_engine = VariableElimination(self.model)
    
    def _define_cpds(self):
        """
        Define conditional probability tables for all nodes.
        
        CPDs encode domain knowledge about failure probabilities.
        """
        # Prior probabilities (root causes)
        
        # P(CableAge) - Cable age distribution
        cpd_cable_age = TabularCPD(
            variable='CableAge',
            variable_card=3,
            values=[[0.3],   # New
                    [0.5],   # Old
                    [0.2]]   # VeryOld
        )
        
        # P(AmbientTemp) - Temperature distribution
        cpd_ambient_temp = TabularCPD(
            variable='AmbientTemp',
            variable_card=3,
            values=[[0.6],   # Normal
                    [0.3],   # High
                    [0.1]]   # VeryHigh
        )
        
        # P(EMI_Source) - EMI presence
        cpd_emi = TabularCPD(
            variable='EMI_Source',
            variable_card=3,
            values=[[0.7],   # None
                    [0.2],   # Low
                    [0.1]]   # High
        )
        
        # P(ConfigError) - Configuration error probability
        cpd_config = TabularCPD(
            variable='ConfigError',
            variable_card=2,
            values=[[0.9],   # False
                    [0.1]]   # True
        )
        
        # Conditional probabilities
        
        # P(CableFailure | CableAge, AmbientTemp)
        cpd_cable_failure = TabularCPD(
            variable='CableFailure',
            variable_card=2,
            values=[
                # CableAge: New, Old, VeryOld (rows)
                # AmbientTemp: Normal, High, VeryHigh (columns within each age group)
                [0.95, 0.90, 0.80,  # New cable
                 0.85, 0.75, 0.60,  # Old cable
                 0.70, 0.50, 0.30], # VeryOld cable
                [0.05, 0.10, 0.20,  # Failure probabilities
                 0.15, 0.25, 0.40,
                 0.30, 0.50, 0.70]
            ],
            evidence=['CableAge', 'AmbientTemp'],
            evidence_card=[3, 3]
        )
        
        # P(ConnectorOxidation | AmbientTemp)
        cpd_connector = TabularCPD(
            variable='ConnectorOxidation',
            variable_card=2,
            values=[
                [0.90, 0.75, 0.60],  # False (no oxidation)
                [0.10, 0.25, 0.40]   # True (oxidation)
            ],
            evidence=['AmbientTemp'],
            evidence_card=[3]
        )
        
        # P(CRCErrors | CableFailure, ConnectorOxidation, EMI_Source)
        # Simplified: 3 states (Low, Medium, High)
        cpd_crc = TabularCPD(
            variable='CRCErrors',
            variable_card=3,
            values=[
                # Cable=F, Connector=F, EMI=None/Low/High
                [0.90, 0.70, 0.40,
                 # Cable=F, Connector=T, EMI=None/Low/High
                 0.70, 0.50, 0.30,
                 # Cable=T, Connector=F, EMI=None/Low/High
                 0.40, 0.25, 0.15,
                 # Cable=T, Connector=T, EMI=None/Low/High
                 0.20, 0.10, 0.05],  # Low CRC
                
                [0.08, 0.25, 0.40,
                 0.25, 0.35, 0.45,
                 0.40, 0.50, 0.45,
                 0.50, 0.50, 0.35],  # Medium CRC
                
                [0.02, 0.05, 0.20,
                 0.05, 0.15, 0.25,
                 0.20, 0.25, 0.40,
                 0.30, 0.40, 0.60]   # High CRC
            ],
            evidence=['CableFailure', 'ConnectorOxidation', 'EMI_Source'],
            evidence_card=[2, 2, 3]
        )
        
        # P(PacketLoss | CRCErrors, ConfigError)
        cpd_packet_loss = TabularCPD(
            variable='PacketLoss',
            variable_card=3,
            values=[
                # CRC=Low, Config=F/T; CRC=Med, Config=F/T; CRC=High, Config=F/T
                [0.90, 0.60, 0.70, 0.40, 0.50, 0.20],  # Low loss
                [0.08, 0.30, 0.25, 0.40, 0.35, 0.40],  # Medium loss
                [0.02, 0.10, 0.05, 0.20, 0.15, 0.40]   # High loss
            ],
            evidence=['CRCErrors', 'ConfigError'],
            evidence_card=[3, 2]
        )
        
        # P(Latency | PacketLoss)
        cpd_latency = TabularCPD(
            variable='Latency',
            variable_card=3,
            values=[
                [0.85, 0.60, 0.30],  # Normal latency
                [0.12, 0.30, 0.40],  # High latency
                [0.03, 0.10, 0.30]   # VeryHigh latency
            ],
            evidence=['PacketLoss'],
            evidence_card=[3]
        )
        
        # Add all CPDs to model
        self.model.add_cpds(
            cpd_cable_age,
            cpd_ambient_temp,
            cpd_emi,
            cpd_config,
            cpd_cable_failure,
            cpd_connector,
            cpd_crc,
            cpd_packet_loss,
            cpd_latency
        )
    
    def diagnose_with_uncertainty(
        self,
        observed_symptoms: Dict[str, str]
    ) -> ProbabilisticDiagnosis:
        """
        Perform probabilistic diagnosis given observed symptoms.
        
        Args:
            observed_symptoms: Dictionary of observed variables and their states
                Example: {'CRCErrors': 'High', 'PacketLoss': 'Medium'}
        
        Returns:
            ProbabilisticDiagnosis with probability distribution over root causes
        """
        # Store evidence
        self.current_evidence = observed_symptoms.copy()
        
        # Query for root cause probabilities
        root_causes = ['CableFailure', 'ConnectorOxidation', 'EMI_Source', 'ConfigError']
        
        cause_probabilities = {}
        
        for cause in root_causes:
            try:
                result = self.inference_engine.query(
                    variables=[cause],
                    evidence=observed_symptoms
                )
                
                # Extract probability of failure/presence
                if cause in ['CableFailure', 'ConnectorOxidation', 'ConfigError']:
                    # Binary variables - get P(True)
                    prob = result.values[1]
                    cause_probabilities[cause] = prob
                else:  # EMI_Source
                    # Multi-state - get P(Low) + P(High)
                    prob = result.values[1] + result.values[2]
                    cause_probabilities[cause] = prob
            except Exception as e:
                # If inference fails, assign low probability
                cause_probabilities[cause] = 0.01
        
        # Find primary cause
        primary_cause = max(cause_probabilities, key=cause_probabilities.get)
        primary_probability = cause_probabilities[primary_cause]
        
        # Determine confidence level
        if primary_probability > 0.6:
            confidence_level = "High"
        elif primary_probability > 0.4:
            confidence_level = "Medium"
        else:
            confidence_level = "Low"
        
        # Generate multi-hypothesis actions
        actions = self.generate_multi_hypothesis_action(cause_probabilities)
        
        # Generate explanation
        explanation = self._generate_explanation(
            cause_probabilities,
            observed_symptoms,
            primary_cause
        )
        
        diagnosis = ProbabilisticDiagnosis(
            anomaly_id=f"diag_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            timestamp=datetime.now(),
            cause_probabilities=cause_probabilities,
            primary_cause=primary_cause,
            primary_probability=primary_probability,
            multi_hypothesis_actions=actions,
            explanation=explanation,
            confidence_level=confidence_level,
            evidence_used=observed_symptoms
        )
        
        return diagnosis
    
    def generate_multi_hypothesis_action(
        self,
        prob_distribution: Dict[str, float]
    ) -> List[str]:
        """
        Generate action plan considering multiple possible causes.
        
        Args:
            prob_distribution: Probability for each root cause
        
        Returns:
            List of recommended actions (primary first, then parallel checks)
        """
        actions = []
        
        # Sort causes by probability
        sorted_causes = sorted(
            prob_distribution.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        # Generate actions for plausible causes (> 15% probability)
        for cause, prob in sorted_causes:
            if prob > 0.15:
                action = self._get_action_for_cause(cause, prob)
                actions.append(action)
        
        return actions
    
    def _get_action_for_cause(self, cause: str, probability: float) -> str:
        """Get recommended action for a specific cause"""
        action_map = {
            'CableFailure': f"Test cable with TDR (Time Domain Reflectometer) - {probability:.1%} probability",
            'ConnectorOxidation': f"Inspect connectors for oxidation/corrosion - {probability:.1%} probability",
            'EMI_Source': f"Scan for EMI sources (motors, VFDs, welders) - {probability:.1%} probability",
            'ConfigError': f"Verify network configuration (VLANs, QoS) - {probability:.1%} probability"
        }
        return action_map.get(cause, f"Investigate {cause} - {probability:.1%} probability")
    
    def _generate_explanation(
        self,
        probabilities: Dict[str, float],
        symptoms: Dict[str, str],
        primary: str
    ) -> str:
        """Generate human-readable explanation of diagnosis"""
        symptom_str = ", ".join([f"{k}={v}" for k, v in symptoms.items()])
        
        # Get top 3 causes
        top_causes = sorted(probabilities.items(), key=lambda x: x[1], reverse=True)[:3]
        
        explanation = f"Based on observed symptoms ({symptom_str}), the most likely causes are:\n"
        for i, (cause, prob) in enumerate(top_causes, 1):
            explanation += f"{i}. {cause.replace('_', ' ')}: {prob:.1%}\n"
        
        explanation += f"\nPrimary hypothesis: {primary.replace('_', ' ')} ({probabilities[primary]:.1%})"
        
        return explanation
    
    def update_beliefs_online(
        self,
        new_evidence: Dict[str, str]
    ) -> ProbabilisticDiagnosis:
        """
        Update beliefs with new evidence (Bayesian updating).
        
        Args:
            new_evidence: New observations from technician
                Example: {'TDR_Result': 'Pass'} after testing cable
        
        Returns:
            Updated diagnosis with shifted probabilities
        """
        # Store previous probabilities
        previous_diagnosis = self.diagnose_with_uncertainty(self.current_evidence)
        previous_probs = previous_diagnosis.cause_probabilities.copy()
        
        # Merge new evidence with existing
        self.current_evidence.update(new_evidence)
        
        # Re-run diagnosis with updated evidence
        updated_diagnosis = self.diagnose_with_uncertainty(self.current_evidence)
        updated_probs = updated_diagnosis.cause_probabilities
        
        # Calculate probability shifts
        shifts = {
            cause: updated_probs[cause] - previous_probs[cause]
            for cause in updated_probs
        }
        
        # Record belief update
        update = BeliefUpdate(
            diagnosis_id=updated_diagnosis.anomaly_id,
            timestamp=datetime.now(),
            new_evidence=new_evidence,
            previous_probabilities=previous_probs,
            updated_probabilities=updated_probs,
            probability_shifts=shifts,
            interpretation=self._interpret_belief_shift(shifts, new_evidence)
        )
        
        self.belief_history.append(update)
        
        return updated_diagnosis
    
    def _interpret_belief_shift(
        self,
        shifts: Dict[str, float],
        new_evidence: Dict[str, str]
    ) -> str:
        """Generate interpretation of how beliefs changed"""
        evidence_str = ", ".join([f"{k}={v}" for k, v in new_evidence.items()])
        
        # Find biggest shifts
        increases = {k: v for k, v in shifts.items() if v > 0.05}
        decreases = {k: v for k, v in shifts.items() if v < -0.05}
        
        interpretation = f"After observing {evidence_str}:\n"
        
        if increases:
            interpretation += "Increased probability: "
            interpretation += ", ".join([f"{k} (+{v:.1%})" for k, v in increases.items()])
            interpretation += "\n"
        
        if decreases:
            interpretation += "Decreased probability: "
            interpretation += ", ".join([f"{k} ({v:.1%})" for k, v in decreases.items()])
        
        return interpretation
    
    def get_most_likely_cause(self, diagnosis: ProbabilisticDiagnosis) -> Tuple[str, float]:
        """Extract highest probability cause"""
        return diagnosis.primary_cause, diagnosis.primary_probability
    
    def get_belief_evolution(self) -> List[BeliefUpdate]:
        """Get history of belief updates"""
        return self.belief_history.copy()
    
    def reset_evidence(self):
        """Clear current evidence and belief history"""
        self.current_evidence = {}
        self.belief_history = []
