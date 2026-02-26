"""
LSTM Training Pipeline

Trains the TimeSeriesLSTM model for network metric forecasting.
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, random_split
from typing import Tuple, Dict, List
import pandas as pd
import numpy as np
from pathlib import Path
from tqdm import tqdm
import matplotlib.pyplot as plt
import json

from src.intelligence.lstm_forecaster import TimeSeriesLSTM, LSTMForecaster, create_forecast_dataset


class TimeSeriesDataset(Dataset):
    """
    PyTorch Dataset for time-series forecasting
    """
    
    def __init__(
        self,
        X: np.ndarray,
        y: np.ndarray,
        mean: Optional[np.ndarray] = None,
        std: Optional[np.ndarray] = None
    ):
        """
        Args:
            X: Input sequences (num_samples, seq_len, num_features)
            y: Target sequences (num_samples, horizon, num_features)
            mean: Mean for normalization
            std: Std for normalization
        """
        self.X = X
        self.y = y
        
        # Normalize
        if mean is None:
            self.mean = X.reshape(-1, X.shape[-1]).mean(axis=0)
            self.std = X.reshape(-1, X.shape[-1]).std(axis=0) + 1e-8
        else:
            self.mean = mean
            self.std = std
        
        self.X_norm = (X - self.mean) / self.std
        self.y_norm = (y - self.mean) / self.std
    
    def __len__(self) -> int:
        return len(self.X)
    
    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        X = torch.tensor(self.X_norm[idx], dtype=torch.float32)
        y = torch.tensor(self.y_norm[idx], dtype=torch.float32)
        return X, y


class LSTMTrainer:
    """
    Trainer for TimeSeriesLSTM model
    """
    
    def __init__(
        self,
        model: TimeSeriesLSTM,
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
        
        # Loss function (Huber loss - robust to outliers)
        self.criterion = nn.HuberLoss(delta=1.0)
        
        # Training history
        self.history = {
            'train_loss': [],
            'val_loss': [],
            'train_mae': [],
            'val_mae': []
        }
    
    def train_epoch(self, train_loader: DataLoader) -> Tuple[float, float]:
        """Train for one epoch"""
        self.model.train()
        total_loss = 0
        total_mae = 0
        num_batches = 0
        
        for X_batch, y_batch in tqdm(train_loader, desc="Training"):
            X_batch = X_batch.to(self.device)
            y_batch = y_batch.to(self.device)
            
            # Forward pass
            forecast, uncertainty, _ = self.model(X_batch)
            
            # Compute loss
            loss = self.criterion(forecast, y_batch)
            
            # Add uncertainty regularization (encourage calibrated uncertainty)
            uncertainty_loss = 0.01 * uncertainty.mean()
            total_loss_with_reg = loss + uncertainty_loss
            
            # Backward pass
            self.optimizer.zero_grad()
            total_loss_with_reg.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
            self.optimizer.step()
            
            # Track metrics
            total_loss += loss.item()
            mae = torch.abs(forecast - y_batch).mean().item()
            total_mae += mae
            num_batches += 1
        
        avg_loss = total_loss / num_batches
        avg_mae = total_mae / num_batches
        
        return avg_loss, avg_mae
    
    def validate(self, val_loader: DataLoader) -> Tuple[float, float]:
        """Validate model"""
        self.model.eval()
        total_loss = 0
        total_mae = 0
        num_batches = 0
        
        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                X_batch = X_batch.to(self.device)
                y_batch = y_batch.to(self.device)
                
                forecast, _, _ = self.model(X_batch)
                
                loss = self.criterion(forecast, y_batch)
                mae = torch.abs(forecast - y_batch).mean().item()
                
                total_loss += loss.item()
                total_mae += mae
                num_batches += 1
        
        avg_loss = total_loss / num_batches
        avg_mae = total_mae / num_batches
        
        return avg_loss, avg_mae
    
    def train(
        self,
        train_loader: DataLoader,
        val_loader: DataLoader,
        num_epochs: int = 50,
        save_dir: str = 'models/lstm',
        mean: np.ndarray = None,
        std: np.ndarray = None
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
        print(f"Starting LSTM Training")
        print(f"{'='*60}")
        print(f"Epochs: {num_epochs}")
        print(f"Device: {self.device}")
        print(f"Train batches: {len(train_loader)}")
        print(f"Val batches: {len(val_loader)}")
        print(f"{'='*60}\n")
        
        for epoch in range(num_epochs):
            # Train
            train_loss, train_mae = self.train_epoch(train_loader)
            
            # Validate
            val_loss, val_mae = self.validate(val_loader)
            
            # Update scheduler
            self.scheduler.step(val_loss)
            
            # Save history
            self.history['train_loss'].append(train_loss)
            self.history['val_loss'].append(val_loss)
            self.history['train_mae'].append(train_mae)
            self.history['val_mae'].append(val_mae)
            
            # Print progress
            print(f"Epoch {epoch+1}/{num_epochs}")
            print(f"  Train Loss: {train_loss:.4f} | Train MAE: {train_mae:.4f}")
            print(f"  Val Loss:   {val_loss:.4f} | Val MAE:   {val_mae:.4f}")
            
            # Save best model
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
                
                checkpoint = {
                    'model_state_dict': self.model.state_dict(),
                    'mean': mean,
                    'std': std,
                    'epoch': epoch,
                    'val_loss': val_loss
                }
                torch.save(checkpoint, save_path / 'best_model.pth')
                print(f"  ✓ Saved best model (val_loss: {val_loss:.4f})")
            else:
                patience_counter += 1
            
            # Early stopping
            if patience_counter >= max_patience:
                print(f"\nEarly stopping after {epoch+1} epochs")
                break
            
            print()
        
        # Save final model
        final_checkpoint = {
            'model_state_dict': self.model.state_dict(),
            'mean': mean,
            'std': std
        }
        torch.save(final_checkpoint, save_path / 'final_model.pth')
        
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
        ax1.set_ylabel('Huber Loss')
        ax1.set_title('Training and Validation Loss')
        ax1.legend()
        ax1.grid(True)
        
        # MAE plot
        ax2.plot(self.history['train_mae'], label='Train MAE')
        ax2.plot(self.history['val_mae'], label='Val MAE')
        ax2.set_xlabel('Epoch')
        ax2.set_ylabel('Mean Absolute Error')
        ax2.set_title('Training and Validation MAE')
        ax2.legend()
        ax2.grid(True)
        
        plt.tight_layout()
        plt.savefig(save_path, dpi=150)
        plt.close()
        
        print(f"[OK] Saved training history plot to {save_path}")


def main():
    """Main training script"""
    print("Loading data...")
    
    # Load synthetic metrics
    metrics_df = pd.read_csv('data/synthetic/metrics_extended.csv')
    
    # Create dataset
    print("Creating sliding window dataset...")
    X, y = create_forecast_dataset(
        metrics_df,
        sequence_length=48,
        forecast_horizon=24
    )
    
    print(f"Dataset shape: X={X.shape}, y={y.shape}")
    
    # Create PyTorch dataset
    dataset = TimeSeriesDataset(X, y)
    
    # Split dataset
    train_size = int(0.7 * len(dataset))
    val_size = int(0.15 * len(dataset))
    test_size = len(dataset) - train_size - val_size
    
    train_dataset, val_dataset, test_dataset = random_split(
        dataset,
        [train_size, val_size, test_size]
    )
    
    print(f"Train: {len(train_dataset)}, Val: {len(val_dataset)}, Test: {len(test_dataset)}")
    
    # Create data loaders
    train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=32, shuffle=False)
    
    # Create model
    model = TimeSeriesLSTM(
        input_dim=12,
        hidden_dim=128,
        num_layers=2,
        forecast_horizon=24,
        num_heads=4,
        dropout=0.2
    )
    
    # Create trainer
    trainer = LSTMTrainer(model, device='cpu', learning_rate=0.001)
    
    # Train
    trainer.train(
        train_loader,
        val_loader,
        num_epochs=50,
        save_dir='models/lstm',
        mean=dataset.mean,
        std=dataset.std
    )
    
    print("Training complete!")


if __name__ == '__main__':
    main()
