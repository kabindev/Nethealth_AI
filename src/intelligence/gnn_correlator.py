"""
Graph Neural Network for Network Fault Correlation

Implements topology-aware fault detection and root cause analysis using
Graph Attention Networks (GAT) with PyTorch Geometric.

Replaces statistical Granger causality with learned graph representations.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GATConv, global_mean_pool, global_max_pool
from torch_geometric.data import Data, Batch
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import pandas as pd
import numpy as np
from pathlib import Path


@dataclass
class CorrelationResult:
    """Result from GNN fault correlation"""
    node_probabilities: torch.Tensor  # (num_nodes, num_fault_types)
    root_cause_prediction: int  # Predicted fault type
    root_cause_confidence: float  # Confidence score
    node_embeddings: torch.Tensor  # Learned node representations
    attention_weights: Optional[torch.Tensor] = None  # GAT attention weights


class NetworkGNN(nn.Module):
    """
    Graph Neural Network for network fault correlation
    
    Architecture:
    - 3 Graph Attention layers (GAT) for message passing
    - Node-level predictions (fault probability per device)
    - Graph-level predictions (root cause classification)
    
    Args:
        node_features: Dimension of node feature vectors
        edge_features: Dimension of edge feature vectors
        hidden_dim: Hidden layer dimension
        num_fault_types: Number of fault types to classify
        num_heads: Number of attention heads in GAT
    """
    
    def __init__(
        self,
        node_features: int = 32,
        edge_features: int = 16,
        hidden_dim: int = 64,
        num_fault_types: int = 5,
        num_heads: int = 4,
        dropout: float = 0.3
    ):
        super().__init__()
        
        self.node_features = node_features
        self.edge_features = edge_features
        self.hidden_dim = hidden_dim
        self.num_fault_types = num_fault_types
        self.dropout = dropout
        
        # Graph Attention layers
        self.conv1 = GATConv(
            node_features,
            hidden_dim // num_heads,
            heads=num_heads,
            edge_dim=edge_features,
            dropout=dropout
        )
        
        self.conv2 = GATConv(
            hidden_dim,
            hidden_dim // num_heads,
            heads=num_heads,
            edge_dim=edge_features,
            dropout=dropout
        )
        
        self.conv3 = GATConv(
            hidden_dim,
            hidden_dim // num_heads,
            heads=num_heads,
            edge_dim=edge_features,
            dropout=dropout,
            concat=False  # Average instead of concatenate
        )
        
        # Batch normalization layers
        self.bn1 = nn.BatchNorm1d(hidden_dim)
        self.bn2 = nn.BatchNorm1d(hidden_dim)
        self.bn3 = nn.BatchNorm1d(hidden_dim // num_heads)
        
        # Node-level prediction head (fault probability per device)
        self.node_classifier = nn.Sequential(
            nn.Linear(hidden_dim // num_heads, 32),
            nn.ReLU(),
            nn.BatchNorm1d(32),
            nn.Dropout(dropout),
            nn.Linear(32, num_fault_types)
        )
        
        # Graph-level prediction head (root cause identification)
        self.graph_classifier = nn.Sequential(
            nn.Linear(hidden_dim // num_heads * 2, 64),  # *2 for mean+max pooling
            nn.ReLU(),
            nn.BatchNorm1d(64),
            nn.Dropout(dropout),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, num_fault_types)
        )
    
    def forward(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        edge_attr: torch.Tensor,
        batch: torch.Tensor,
        return_attention: bool = False
    ) -> Tuple[torch.Tensor, torch.Tensor, Optional[torch.Tensor]]:
        """
        Forward pass through GNN
        
        Args:
            x: Node features (num_nodes, node_features)
            edge_index: Edge connectivity (2, num_edges)
            edge_attr: Edge features (num_edges, edge_features)
            batch: Batch assignment for each node
            return_attention: Whether to return attention weights
        
        Returns:
            node_preds: Node-level fault probabilities (num_nodes, num_fault_types)
            graph_pred: Graph-level root cause prediction (batch_size, num_fault_types)
            attention_weights: Optional attention weights from last GAT layer
        """
        # First GAT layer
        x, attn1 = self.conv1(x, edge_index, edge_attr, return_attention_weights=True)
        x = self.bn1(x)
        x = F.relu(x)
        x = F.dropout(x, p=self.dropout, training=self.training)
        
        # Second GAT layer
        x, attn2 = self.conv2(x, edge_index, edge_attr, return_attention_weights=True)
        x = self.bn2(x)
        x = F.relu(x)
        x = F.dropout(x, p=self.dropout, training=self.training)
        
        # Third GAT layer
        x, attn3 = self.conv3(x, edge_index, edge_attr, return_attention_weights=True)
        x = self.bn3(x)
        
        # Node-level predictions
        node_preds = self.node_classifier(x)
        
        # Graph-level pooling (combine mean and max)
        graph_mean = global_mean_pool(x, batch)
        graph_max = global_max_pool(x, batch)
        graph_embedding = torch.cat([graph_mean, graph_max], dim=1)
        
        # Graph-level prediction
        graph_pred = self.graph_classifier(graph_embedding)
        
        # Return attention weights if requested
        attention_weights = attn3 if return_attention else None
        
        return node_preds, graph_pred, attention_weights
    
    def get_embeddings(
        self,
        x: torch.Tensor,
        edge_index: torch.Tensor,
        edge_attr: torch.Tensor
    ) -> torch.Tensor:
        """
        Get learned node embeddings without classification
        
        Useful for visualization and analysis
        """
        with torch.no_grad():
            # Pass through GAT layers
            x = F.relu(self.bn1(self.conv1(x, edge_index, edge_attr)))
            x = F.relu(self.bn2(self.conv2(x, edge_index, edge_attr)))
            x = self.bn3(self.conv3(x, edge_index, edge_attr))
        
        return x


class GNNCorrelator:
    """
    Graph Neural Network-based fault correlator
    
    Replaces Granger causality with learned topology-aware patterns.
    Provides node-level fault probabilities and graph-level root cause prediction.
    """
    
    FAULT_TYPE_MAPPING = {
        0: 'cable_failure',
        1: 'emi_interference',
        2: 'config_error',
        3: 'thermal_stress',
        4: 'normal'
    }
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        device: str = 'cpu'
    ):
        """
        Initialize GNN correlator
        
        Args:
            model_path: Path to trained model weights (optional)
            device: 'cpu' or 'cuda'
        """
        self.device = torch.device(device)
        self.model = NetworkGNN().to(self.device)
        
        if model_path and Path(model_path).exists():
            self.load_model(model_path)
        
        self.model.eval()
    
    def load_model(self, model_path: str):
        """Load trained model weights"""
        state_dict = torch.load(model_path, map_location=self.device)
        self.model.load_state_dict(state_dict)
        print(f"[OK] Loaded GNN model from {model_path}")
    
    def save_model(self, model_path: str):
        """Save model weights"""
        torch.save(self.model.state_dict(), model_path)
        print(f"[OK] Saved GNN model to {model_path}")
    
    def predict_fault_correlation(
        self,
        graph_data: Data,
        return_attention: bool = False
    ) -> CorrelationResult:
        """
        Predict fault correlations using GNN
        
        Args:
            graph_data: PyTorch Geometric Data object with:
                - x: Node features
                - edge_index: Edge connectivity
                - edge_attr: Edge features
            return_attention: Whether to return attention weights
        
        Returns:
            CorrelationResult with predictions and embeddings
        """
        self.model.eval()
        
        with torch.no_grad():
            # Move data to device
            graph_data = graph_data.to(self.device)
            
            # Create batch tensor (single graph)
            batch = torch.zeros(graph_data.x.size(0), dtype=torch.long, device=self.device)
            
            # Run inference
            node_preds, graph_pred, attention = self.model(
                graph_data.x,
                graph_data.edge_index,
                graph_data.edge_attr,
                batch,
                return_attention=return_attention
            )
            
            # Get root cause prediction
            root_cause_idx = graph_pred.argmax(dim=1).item()
            root_cause_confidence = F.softmax(graph_pred, dim=1)[0, root_cause_idx].item()
            
            # Get node embeddings
            embeddings = self.model.get_embeddings(
                graph_data.x,
                graph_data.edge_index,
                graph_data.edge_attr
            )
        
        return CorrelationResult(
            node_probabilities=F.softmax(node_preds, dim=1).cpu(),
            root_cause_prediction=root_cause_idx,
            root_cause_confidence=root_cause_confidence,
            node_embeddings=embeddings.cpu(),
            attention_weights=attention
        )
    
    def get_fault_type_name(self, fault_idx: int) -> str:
        """Convert fault index to human-readable name"""
        return self.FAULT_TYPE_MAPPING.get(fault_idx, 'unknown')


def create_graph_from_topology(
    topology: Dict,
    metrics: Dict[str, pd.DataFrame],
    device_types: Dict[str, str]
) -> Data:
    """
    Convert network topology and metrics to PyTorch Geometric graph
    
    Args:
        topology: Network topology dictionary
        metrics: Time-series metrics per device
        device_types: Device type mapping
    
    Returns:
        PyTorch Geometric Data object
    """
    # TODO: Implement topology to graph conversion
    # This will be implemented in the training pipeline
    pass
