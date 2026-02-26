"""
GNN Training Pipeline

Converts synthetic time-series data to graph snapshots and trains
the NetworkGNN model for fault correlation.
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torch_geometric.data import Data, Dataset, DataLoader
from torch_geometric.loader import DataLoader as PyGDataLoader
from typing import List, Dict, Tuple, Optional
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime
from tqdm import tqdm
import matplotlib.pyplot as plt
import seaborn as sns

from src.intelligence.gnn_correlator import NetworkGNN, GNNCorrelator
from src.data.schemas import Asset


class NetworkGraphDataset(Dataset):
    """
    PyTorch Geometric Dataset for network fault graphs
    
    Converts time-series snapshots to graph representations
    """
    
    def __init__(
        self,
        data_dir: str = 'data/synthetic',
        transform=None,
        pre_transform=None
    ):
        super().__init__(None, transform, pre_transform)
        
        self.data_dir = Path(data_dir)
        self.graphs = []
        
        # Load and process data
        self._load_data()
    
    def _load_data(self):
        """Load synthetic data and convert to graphs"""
        print("[INFO] Loading synthetic data...")
        
        # Load ground truth
        ground_truth_path = self.data_dir / 'ground_truth.json'
        with open(ground_truth_path, 'r') as f:
            ground_truth = json.load(f)
        
        # Load metrics
        metrics_path = self.data_dir / 'metrics_extended.csv'
        metrics_df = pd.read_csv(metrics_path)
        
        # Load assets
        assets_path = self.data_dir.parent / 'raw' / 'assets.json'
        with open(assets_path, 'r') as f:
            assets = json.load(f)
        
        # Load topology
        topology_path = self.data_dir.parent / 'raw' / 'topology.json'
        with open(topology_path, 'r') as f:
            topology = json.load(f)
        
        print(f"[INFO] Processing {len(ground_truth)} scenarios...")
        
        # Convert each scenario to a graph
        for scenario in tqdm(ground_truth[:100], desc="Creating graphs"):  # Limit to 100 for now
            graph = self._scenario_to_graph(
                scenario,
                metrics_df,
                assets,
                topology
            )
            if graph is not None:
                self.graphs.append(graph)
        
        print(f"[OK] Created {len(self.graphs)} graph snapshots")
    
    def _scenario_to_graph(
        self,
        scenario: Dict,
        metrics_df: pd.DataFrame,
        assets: List[Dict],
        topology: Dict
    ) -> Optional[Data]:
        """
        Convert a fault scenario to a PyTorch Geometric graph
        
        Args:
            scenario: Ground truth scenario
            metrics_df: Time-series metrics
            assets: Asset definitions
            topology: Network topology
        
        Returns:
            PyTorch Geometric Data object
        """
        try:
            scenario_id = scenario['scenario_id']
            fault_type = scenario['fault_type']
            affected_asset = scenario['affected_asset']
            fault_start_idx = scenario['fault_start_idx']
            
            # Get metrics at fault time
            fault_metrics = metrics_df[
                (metrics_df['scenario_id'] == scenario_id) &
                (metrics_df['time_idx'] == fault_start_idx)
            ]
            
            if fault_metrics.empty:
                return None
            
            # Create node features
            node_features = []
            node_to_idx = {}
            asset_ids = []
            
            for idx, asset in enumerate(assets):
                asset_id = asset['id']
                node_to_idx[asset_id] = idx
                asset_ids.append(asset_id)
                
                # Get metrics for this asset
                asset_metrics = fault_metrics[fault_metrics['asset_id'] == asset_id]
                
                if not asset_metrics.empty:
                    features = self._extract_node_features(asset, asset_metrics.iloc[0])
                else:
                    features = self._extract_node_features(asset, None)
                
                node_features.append(features)
            
            # Create edge index and edge features
            edge_index, edge_attr = self._create_edges(topology, node_to_idx)
            
            # Create labels
            # Node labels: which nodes are affected
            node_labels = torch.zeros(len(assets), dtype=torch.long)
            if affected_asset in node_to_idx:
                node_labels[node_to_idx[affected_asset]] = self._fault_type_to_idx(fault_type)
            
            # Graph label: root cause fault type
            graph_label = self._fault_type_to_idx(fault_type)
            
            # Create PyG Data object
            data = Data(
                x=torch.tensor(node_features, dtype=torch.float),
                edge_index=edge_index,
                edge_attr=edge_attr,
                y=graph_label,
                node_y=node_labels,
                scenario_id=scenario_id,
                affected_asset=affected_asset
            )
            
            return data
            
        except Exception as e:
            print(f"[WARNING] Failed to create graph for scenario {scenario.get('scenario_id')}: {e}")
            return None
    
    def _extract_node_features(self, asset: Dict, metrics: Optional[pd.Series]) -> List[float]:
        """
        Extract node features from asset and metrics
        
        Features (32-dim):
        - Device type (one-hot, 8 dims)
        - Current metrics (12 dims)
        - Historical statistics (6 dims)
        - Anomaly flags (6 dims)
        """
        features = []
        
        # Device type one-hot encoding
        device_types = ['switch', 'plc', 'hmi', 'firewall', 'router', 'sensor', 'actuator', 'other']
        device_type = asset.get('type', 'other')
        type_onehot = [1.0 if dt == device_type else 0.0 for dt in device_types]
        features.extend(type_onehot)
        
        # Current metrics (normalized)
        if metrics is not None:
            metric_values = [
                metrics.get('latency', 0.0) / 100.0,  # Normalize
                metrics.get('throughput', 0.0) / 1000.0,
                metrics.get('packet_loss', 0.0),
                metrics.get('jitter', 0.0) / 10.0,
                metrics.get('cpu_usage', 0.0),
                metrics.get('memory_usage', 0.0),
                metrics.get('temperature', 0.0) / 100.0,
                metrics.get('crc_errors', 0.0) / 100.0,
                metrics.get('retransmissions', 0.0) / 100.0,
                metrics.get('snr', 0.0) / 50.0,
                metrics.get('ber', 0.0) * 1000.0,
                metrics.get('link_utilization', 0.0)
            ]
        else:
            metric_values = [0.0] * 12
        
        features.extend(metric_values)
        
        # Historical statistics (placeholder - would compute from time-series)
        historical_stats = [0.0] * 6
        features.extend(historical_stats)
        
        # Anomaly flags (placeholder - would come from anomaly detector)
        anomaly_flags = [0.0] * 6
        features.extend(anomaly_flags)
        
        return features
    
    def _create_edges(
        self,
        topology: Dict,
        node_to_idx: Dict[str, int]
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Create edge index and edge attributes from topology
        
        Returns:
            edge_index: (2, num_edges) tensor
            edge_attr: (num_edges, edge_features) tensor
        """
        edges = topology.get('edges', [])
        
        edge_list = []
        edge_features = []
        
        for edge in edges:
            source = edge.get('source')
            target = edge.get('target')
            
            if source in node_to_idx and target in node_to_idx:
                src_idx = node_to_idx[source]
                tgt_idx = node_to_idx[target]
                
                # Add bidirectional edges
                edge_list.append([src_idx, tgt_idx])
                edge_list.append([tgt_idx, src_idx])
                
                # Edge features (16-dim)
                edge_feat = self._extract_edge_features(edge)
                edge_features.append(edge_feat)
                edge_features.append(edge_feat)  # Same for reverse edge
        
        if not edge_list:
            # Create self-loops if no edges
            num_nodes = len(node_to_idx)
            edge_list = [[i, i] for i in range(num_nodes)]
            edge_features = [[0.0] * 16 for _ in range(num_nodes)]
        
        edge_index = torch.tensor(edge_list, dtype=torch.long).t().contiguous()
        edge_attr = torch.tensor(edge_features, dtype=torch.float)
        
        return edge_index, edge_attr
    
    def _extract_edge_features(self, edge: Dict) -> List[float]:
        """Extract edge features (16-dim)"""
        # Connection type one-hot (4 dims)
        conn_types = ['ethernet', 'profinet', 'modbus', 'other']
        conn_type = edge.get('type', 'ethernet')
        type_onehot = [1.0 if ct == conn_type else 0.0 for ct in conn_types]
        
        # Edge metrics (12 dims)
        edge_metrics = [
            edge.get('bandwidth', 1000.0) / 10000.0,  # Normalized
            edge.get('utilization', 0.0),
            edge.get('latency', 0.0) / 100.0,
            edge.get('packet_loss', 0.0),
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0  # Padding
        ]
        
        return type_onehot + edge_metrics
    
    def _fault_type_to_idx(self, fault_type: str) -> int:
        """Convert fault type string to index"""
        mapping = {
            'cable_failure': 0,
            'emi_interference': 1,
            'config_error': 2,
            'thermal_stress': 3,
            'normal': 4
        }
        return mapping.get(fault_type, 4)
    
    def len(self) -> int:
        return len(self.graphs)
    
    def get(self, idx: int) -> Data:
        return self.graphs[idx]


class GNNTrainer:
    """
    Trainer for NetworkGNN model
    """
    
    def __init__(
        self,
        model: NetworkGNN,
        device: str = 'cpu',
        learning_rate: float = 0.001,
        weight_decay: float = 1e-5
    ):
        self.model = model.to(device)
        self.device = torch.device(device)
        
        # Optimizer
        self.optimizer = optim.Adam(
            model.parameters(),
            lr=learning_rate,
            weight_decay=weight_decay
        )
        
        # Learning rate scheduler
        self.scheduler = optim.lr_scheduler.ReduceLROnPlateau(
            self.optimizer,
            mode='min',
            factor=0.5,
            patience=5,
            verbose=True
        )
        
        # Loss functions
        self.node_criterion = nn.CrossEntropyLoss()
        self.graph_criterion = nn.CrossEntropyLoss()
        
        # Training history
        self.history = {
            'train_loss': [],
            'val_loss': [],
            'train_acc': [],
            'val_acc': []
        }
    
    def train_epoch(self, train_loader: PyGDataLoader) -> Tuple[float, float]:
        """Train for one epoch"""
        self.model.train()
        total_loss = 0
        correct = 0
        total = 0
        
        for batch in tqdm(train_loader, desc="Training"):
            batch = batch.to(self.device)
            
            # Forward pass
            node_preds, graph_preds, _ = self.model(
                batch.x,
                batch.edge_index,
                batch.edge_attr,
                batch.batch
            )
            
            # Compute losses
            node_loss = self.node_criterion(node_preds, batch.node_y)
            graph_loss = self.graph_criterion(graph_preds, batch.y)
            
            # Combined loss (weighted)
            loss = 0.4 * node_loss + 0.6 * graph_loss
            
            # Backward pass
            self.optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
            self.optimizer.step()
            
            # Track metrics
            total_loss += loss.item()
            pred = graph_preds.argmax(dim=1)
            correct += (pred == batch.y).sum().item()
            total += batch.y.size(0)
        
        avg_loss = total_loss / len(train_loader)
        accuracy = correct / total
        
        return avg_loss, accuracy
    
    def validate(self, val_loader: PyGDataLoader) -> Tuple[float, float]:
        """Validate model"""
        self.model.eval()
        total_loss = 0
        correct = 0
        total = 0
        
        with torch.no_grad():
            for batch in val_loader:
                batch = batch.to(self.device)
                
                node_preds, graph_preds, _ = self.model(
                    batch.x,
                    batch.edge_index,
                    batch.edge_attr,
                    batch.batch
                )
                
                node_loss = self.node_criterion(node_preds, batch.node_y)
                graph_loss = self.graph_criterion(graph_preds, batch.y)
                loss = 0.4 * node_loss + 0.6 * graph_loss
                
                total_loss += loss.item()
                pred = graph_preds.argmax(dim=1)
                correct += (pred == batch.y).sum().item()
                total += batch.y.size(0)
        
        avg_loss = total_loss / len(val_loader)
        accuracy = correct / total
        
        return avg_loss, accuracy
    
    def train(
        self,
        train_loader: PyGDataLoader,
        val_loader: PyGDataLoader,
        num_epochs: int = 50,
        save_dir: str = 'models/gnn'
    ):
        """
        Full training loop
        """
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)
        
        best_val_loss = float('inf')
        patience_counter = 0
        max_patience = 10
        
        print(f"\n{'='*60}")
        print(f"Starting GNN Training")
        print(f"{'='*60}")
        print(f"Epochs: {num_epochs}")
        print(f"Device: {self.device}")
        print(f"Train samples: {len(train_loader.dataset)}")
        print(f"Val samples: {len(val_loader.dataset)}")
        print(f"{'='*60}\n")
        
        for epoch in range(num_epochs):
            # Train
            train_loss, train_acc = self.train_epoch(train_loader)
            
            # Validate
            val_loss, val_acc = self.validate(val_loader)
            
            # Update scheduler
            self.scheduler.step(val_loss)
            
            # Save history
            self.history['train_loss'].append(train_loss)
            self.history['val_loss'].append(val_loss)
            self.history['train_acc'].append(train_acc)
            self.history['val_acc'].append(val_acc)
            
            # Print progress
            print(f"Epoch {epoch+1}/{num_epochs}")
            print(f"  Train Loss: {train_loss:.4f} | Train Acc: {train_acc:.4f}")
            print(f"  Val Loss:   {val_loss:.4f} | Val Acc:   {val_acc:.4f}")
            
            # Save best model
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                torch.save(
                    self.model.state_dict(),
                    save_path / 'best_model.pth'
                )
                print(f"  ✓ Saved best model (val_loss: {val_loss:.4f})")
            else:
                patience_counter += 1
            
            # Early stopping
            if patience_counter >= max_patience:
                print(f"\nEarly stopping after {epoch+1} epochs")
                break
            
            print()
        
        # Save final model
        torch.save(self.model.state_dict(), save_path / 'final_model.pth')
        
        # Plot training history
        self.plot_history(save_path / 'training_history.png')
        
        print(f"\n{'='*60}")
        print(f"Training Complete!")
        print(f"Best Val Loss: {best_val_loss:.4f}")
        print(f"Models saved to: {save_path}")
        print(f"{'='*60}\n")
    
    def plot_history(self, save_path: Path):
        """Plot training history"""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
        
        # Loss plot
        ax1.plot(self.history['train_loss'], label='Train Loss')
        ax1.plot(self.history['val_loss'], label='Val Loss')
        ax1.set_xlabel('Epoch')
        ax1.set_ylabel('Loss')
        ax1.set_title('Training and Validation Loss')
        ax1.legend()
        ax1.grid(True)
        
        # Accuracy plot
        ax2.plot(self.history['train_acc'], label='Train Acc')
        ax2.plot(self.history['val_acc'], label='Val Acc')
        ax2.set_xlabel('Epoch')
        ax2.set_ylabel('Accuracy')
        ax2.set_title('Training and Validation Accuracy')
        ax2.legend()
        ax2.grid(True)
        
        plt.tight_layout()
        plt.savefig(save_path, dpi=150)
        plt.close()
        
        print(f"[OK] Saved training history plot to {save_path}")


def main():
    """Main training script"""
    # Create dataset
    print("Creating dataset...")
    dataset = NetworkGraphDataset(data_dir='data/synthetic')
    
    # Split dataset
    train_size = int(0.7 * len(dataset))
    val_size = int(0.15 * len(dataset))
    test_size = len(dataset) - train_size - val_size
    
    train_dataset, val_dataset, test_dataset = torch.utils.data.random_split(
        dataset,
        [train_size, val_size, test_size]
    )
    
    print(f"Train: {len(train_dataset)}, Val: {len(val_dataset)}, Test: {len(test_dataset)}")
    
    # Create data loaders
    train_loader = PyGDataLoader(train_dataset, batch_size=16, shuffle=True)
    val_loader = PyGDataLoader(val_dataset, batch_size=16, shuffle=False)
    test_loader = PyGDataLoader(test_dataset, batch_size=16, shuffle=False)
    
    # Create model
    model = NetworkGNN(
        node_features=32,
        edge_features=16,
        hidden_dim=64,
        num_fault_types=5,
        num_heads=4,
        dropout=0.3
    )
    
    # Create trainer
    trainer = GNNTrainer(model, device='cpu', learning_rate=0.001)
    
    # Train
    trainer.train(
        train_loader,
        val_loader,
        num_epochs=50,
        save_dir='models/gnn'
    )
    
    print("Training complete!")


if __name__ == '__main__':
    main()
