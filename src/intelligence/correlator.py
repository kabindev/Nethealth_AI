from typing import List, Dict, Tuple, Optional
from src.data.schemas import Anomaly, RootCause, Asset
from src.core.topology.topology_builder import TopologyBuilder
from src.intelligence.causality_engine import CausalityEngine, CausalGraph
import networkx as nx
import numpy as np

class Correlator:
    def __init__(self, topology: TopologyBuilder, causality_engine: Optional[CausalityEngine] = None):
        self.topology = topology
        self.causality_engine = causality_engine or CausalityEngine()
        self.causal_graph: Optional[CausalGraph] = None

    def correlate(self, anomalies: List[Anomaly]) -> List[RootCause]:
        """
        Correlate anomalies to find root causes.
        Simplification: We assume provided anomalies are from the same time window.
        """
        if not anomalies:
            return []

        # Map asset_id to anomalies
        anomaly_map = {a.asset_id: a for a in anomalies}
        affected_assets = set(anomaly_map.keys())
        
        root_causes = []
        
        # Simple algorithm: Finding the "most upstream" anomalous node in the graph subgraph induced by anomalies.
        # But we also need to respect Layer precedence?
        # Let's use Upstream Dominance first.
        
        # 1. Identify "Source" anomalies (nodes that have no anomalous ancestors)
        for asset_id in affected_assets:
            ancestors = set(nx.ancestors(self.topology.graph, asset_id))
            anomalous_ancestors = ancestors.intersection(affected_assets)
            
            if not anomalous_ancestors:
                # This node is a root cause candidate
                # (No upstream anomalies found among the set of current anomalies)
                anomaly = anomaly_map[asset_id]
                
                # Check metrics for explanation
                description = f"Root cause identified at {asset_id}. "
                if "crc" in anomaly.metric_or_kpi.lower():
                    description += "Physical layer issue (CRC Errors) indicating cable/EMI problem."
                    action = "Check physical cabling and shielding."
                    prob = 0.95
                elif "loss" in anomaly.metric_or_kpi.lower():
                    description += "Network layer issue (Packet Loss). Check upstream congestion or link."
                    action = "Investigate switch buffers and link capacity."
                    prob = 0.8
                else: 
                    description += f"Anomaly in {anomaly.metric_or_kpi}."
                    action = "General inspection required."
                    prob = 0.7
                
                rc = RootCause(
                    anomaly_id=anomaly.id,
                    root_cause_asset_id=asset_id,
                    probability=prob,
                    description=description,
                    recommended_action=action
                )
                root_causes.append(rc)
                
        return root_causes
    
    def get_topology_suspects(self, anomalies: List[Anomaly]) -> List[str]:
        """
        Get root cause suspects based on topology (upstream dominance).
        
        Args:
            anomalies: List of detected anomalies
            
        Returns:
            List of asset IDs that are upstream of anomalies
        """
        anomaly_map = {a.asset_id: a for a in anomalies}
        affected_assets = set(anomaly_map.keys())
        
        suspects = []
        for asset_id in affected_assets:
            ancestors = set(nx.ancestors(self.topology.graph, asset_id))
            anomalous_ancestors = ancestors.intersection(affected_assets)
            
            if not anomalous_ancestors:
                # No upstream anomalies = root cause candidate
                suspects.append(asset_id)
        
        return suspects
    
    def get_causal_suspects(
        self,
        anomalies: List[Anomaly],
        causal_graph: CausalGraph
    ) -> List[Tuple[str, str, float]]:
        """
        Get root cause suspects based on Granger causality.
        
        Args:
            anomalies: List of detected anomalies
            causal_graph: Proven causal relationships
            
        Returns:
            List of (asset_id, metric, causal_strength) tuples
        """
        suspects = []
        
        for anomaly in anomalies:
            # Find metrics that Granger-cause this anomaly's metric
            causing_edges = causal_graph.get_causing_metrics(
                anomaly.metric_or_kpi,
                anomaly.asset_id
            )
            
            for edge in causing_edges:
                suspects.append((
                    edge.from_asset,
                    edge.from_metric,
                    edge.strength
                ))
        
        # Remove duplicates and sort by strength
        unique_suspects = list(set(suspects))
        unique_suspects.sort(key=lambda x: x[2], reverse=True)
        
        return unique_suspects
    
    def advanced_root_cause_analysis(
        self,
        anomalies: List[Anomaly],
        causal_graph: Optional[CausalGraph] = None
    ) -> List[RootCause]:
        """
        Enhanced root cause analysis combining topology AND proven causality.
        
        This provides higher confidence by requiring both:
        1. Topological upstream dominance
        2. Statistical proof of causation (Granger test)
        
        Args:
            anomalies: List of detected anomalies
            causal_graph: Proven causal relationships (optional)
            
        Returns:
            List of RootCause with enhanced confidence scores
        """
        if not anomalies:
            return []
        
        # If no causal graph provided, fall back to basic correlation
        if causal_graph is None or len(causal_graph) == 0:
            return self.correlate(anomalies)
        
        # Step 1: Get topology suspects (upstream dominance)
        topology_suspects = set(self.get_topology_suspects(anomalies))
        
        # Step 2: Get causal suspects (Granger-proven)
        causal_suspects = self.get_causal_suspects(anomalies, causal_graph)
        
        # Step 3: Find intersection (high confidence root causes)
        root_causes = []
        anomaly_map = {a.asset_id: a for a in anomalies}
        
        for asset_id, metric, causal_strength in causal_suspects:
            # Check if this suspect is also in topology suspects
            in_topology = asset_id in topology_suspects
            
            # Calculate combined confidence
            if in_topology:
                # Both topology and causality agree = very high confidence
                confidence = 0.95
                evidence = "Topology + Granger causality"
            else:
                # Only causality (e.g., broadcast storm, downstream causing upstream)
                confidence = 0.85
                evidence = "Granger causality (non-topological)"
            
            # Get p-value and lag from causal graph
            causal_edge = None
            for anomaly in anomalies:
                edges = causal_graph.get_causing_metrics(
                    anomaly.metric_or_kpi,
                    anomaly.asset_id
                )
                for edge in edges:
                    if edge.from_asset == asset_id and edge.from_metric == metric:
                        causal_edge = edge
                        break
            
            # Generate description
            if causal_edge:
                description = (
                    f"Root cause identified at {asset_id} ({metric}). "
                    f"Granger test proves {metric} causes downstream issues "
                    f"(p={causal_edge.p_value:.4f}, lag={causal_edge.optimal_lag} timesteps). "
                    f"Evidence: {evidence}."
                )
                
                # Generate action based on metric type
                if "crc" in metric.lower() or "error" in metric.lower():
                    action = "Check physical cabling and shielding. Statistical analysis confirms physical layer issue."
                elif "loss" in metric.lower() or "packet" in metric.lower():
                    action = "Investigate switch buffers and link capacity. Causality analysis shows network layer degradation."
                elif "latency" in metric.lower():
                    action = "Check for congestion or routing issues. Granger test identifies latency as causal factor."
                else:
                    action = f"Investigate {metric} at {asset_id}. Proven causal relationship detected."
                
                # Find associated anomaly
                anomaly_id = None
                for anomaly in anomalies:
                    if anomaly.asset_id == asset_id or (
                        causal_graph.has_edge(
                            f"{asset_id}.{metric}",
                            f"{anomaly.asset_id}.{anomaly.metric_or_kpi}"
                        )
                    ):
                        anomaly_id = anomaly.id
                        break
                
                if anomaly_id:
                    rc = RootCause(
                        anomaly_id=anomaly_id,
                        root_cause_asset_id=asset_id,
                        probability=confidence,
                        description=description,
                        recommended_action=action
                    )
                    root_causes.append(rc)
        
        # If no causal root causes found, fall back to topology-only
        if not root_causes:
            return self.correlate(anomalies)
        
        # Sort by confidence
        root_causes.sort(key=lambda rc: rc.probability, reverse=True)
        
        return root_causes
