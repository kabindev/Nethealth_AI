"""
LSTM Time-Series Forecaster

Multi-variate LSTM for network metric forecasting.
Replaces ARIMA with neural network predictions.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, List, Tuple, Optional
import pandas as pd
import numpy as np
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ForecastResult:
    """Result from LSTM forecasting"""
    values: np.ndarray  # Forecasted values (horizon, num_metrics)
    confidence_intervals: Tuple[np.ndarray, np.ndarray]  # (lower, upper)
    attention_weights: Optional[np.ndarray] = None  # Attention weights over time steps


class TimeSeriesLSTM(nn.Module):
    """
    Multi-variate LSTM for network metric forecasting
    
    Architecture:
    - 2-layer stacked LSTM with dropout
    - Multi-head attention mechanism
    - Multi-step forecasting (1h, 6h, 24h)
    
    Args:
        input_dim: Number of input metrics (features)
        hidden_dim: LSTM hidden dimension
        num_layers: Number of LSTM layers
        forecast_horizon: Number of time steps to forecast
        num_heads: Number of attention heads
        dropout: Dropout probability
    """
    
    def __init__(
        self,
        input_dim: int = 12,
        hidden_dim: int = 128,
        num_layers: int = 2,
        forecast_horizon: int = 24,
        num_heads: int = 4,
        dropout: float = 0.2
    ):
        super().__init__()
        
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.forecast_horizon = forecast_horizon
        self.dropout = dropout
        
        # Input projection
        self.input_proj = nn.Linear(input_dim, hidden_dim)
        
        # Stacked LSTM layers
        self.lstm = nn.LSTM(
            hidden_dim,
            hidden_dim,
            num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0
        )
        
        # Multi-head attention over sequence
        self.attention = nn.MultiheadAttention(
            hidden_dim,
            num_heads,
            dropout=dropout,
            batch_first=True
        )
        
        # Layer normalization
        self.layer_norm1 = nn.LayerNorm(hidden_dim)
        self.layer_norm2 = nn.LayerNorm(hidden_dim)
        
        # Forecast decoder
        self.forecast_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, input_dim * forecast_horizon)
        )
        
        # Uncertainty estimation head (for confidence intervals)
        self.uncertainty_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim // 2, input_dim * forecast_horizon),
            nn.Softplus()  # Ensure positive uncertainty
        )
    
    def forward(
        self,
        x: torch.Tensor,
        return_attention: bool = False
    ) -> Tuple[torch.Tensor, torch.Tensor, Optional[torch.Tensor]]:
        """
        Forward pass
        
        Args:
            x: Input sequence (batch, seq_len, input_dim)
            return_attention: Whether to return attention weights
        
        Returns:
            forecast: Predicted values (batch, horizon, input_dim)
            uncertainty: Prediction uncertainty (batch, horizon, input_dim)
            attention_weights: Optional attention weights
        """
        batch_size, seq_len, _ = x.shape
        
        # Project input to hidden dimension
        x = self.input_proj(x)
        x = self.layer_norm1(x)
        
        # LSTM encoding
        lstm_out, (h_n, c_n) = self.lstm(x)
        
        # Self-attention over sequence
        attn_out, attn_weights = self.attention(lstm_out, lstm_out, lstm_out)
        
        # Residual connection + layer norm
        x = self.layer_norm2(lstm_out + attn_out)
        
        # Use last hidden state for forecasting
        last_hidden = x[:, -1, :]
        
        # Generate forecast
        forecast_flat = self.forecast_head(last_hidden)
        forecast = forecast_flat.view(batch_size, self.forecast_horizon, self.input_dim)
        
        # Generate uncertainty estimates
        uncertainty_flat = self.uncertainty_head(last_hidden)
        uncertainty = uncertainty_flat.view(batch_size, self.forecast_horizon, self.input_dim)
        
        if return_attention:
            return forecast, uncertainty, attn_weights
        else:
            return forecast, uncertainty, None
    
    def predict_with_confidence(
        self,
        x: torch.Tensor,
        num_samples: int = 100
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Predict with confidence intervals using Monte Carlo dropout
        
        Args:
            x: Input sequence
            num_samples: Number of MC samples
        
        Returns:
            mean: Mean prediction
            lower: Lower confidence bound (95%)
            upper: Upper confidence bound (95%)
        """
        self.train()  # Enable dropout for MC sampling
        
        predictions = []
        for _ in range(num_samples):
            with torch.no_grad():
                forecast, _, _ = self.forward(x, return_attention=False)
                predictions.append(forecast)
        
        predictions = torch.stack(predictions)  # (num_samples, batch, horizon, input_dim)
        
        mean = predictions.mean(dim=0)
        std = predictions.std(dim=0)
        
        # 95% confidence interval (1.96 * std)
        lower = mean - 1.96 * std
        upper = mean + 1.96 * std
        
        self.eval()
        
        return mean, lower, upper


class LSTMForecaster:
    """
    LSTM-based time-series forecaster
    
    Replaces ARIMA with neural network predictions.
    Supports multi-variate forecasting with confidence intervals.
    """
    
    METRIC_NAMES = [
        'latency', 'throughput', 'packet_loss', 'jitter',
        'cpu_usage', 'memory_usage', 'temperature',
        'crc_errors', 'retransmissions', 'snr', 'ber', 'link_utilization'
    ]
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        device: str = 'cpu',
        sequence_length: int = 48,
        forecast_horizon: int = 24
    ):
        """
        Initialize LSTM forecaster
        
        Args:
            model_path: Path to trained model weights
            device: 'cpu' or 'cuda'
            sequence_length: Input sequence length (time steps)
            forecast_horizon: Forecast horizon (time steps)
        """
        self.device = torch.device(device)
        self.sequence_length = sequence_length
        self.forecast_horizon = forecast_horizon
        
        # Initialize model
        self.model = TimeSeriesLSTM(
            input_dim=len(self.METRIC_NAMES),
            hidden_dim=128,
            num_layers=2,
            forecast_horizon=forecast_horizon,
            num_heads=4,
            dropout=0.2
        ).to(self.device)
        
        if model_path and Path(model_path).exists():
            self.load_model(model_path)
        
        self.model.eval()
        
        # Statistics for normalization
        self.mean = None
        self.std = None
    
    def load_model(self, model_path: str):
        """Load trained model weights"""
        checkpoint = torch.load(model_path, map_location=self.device)
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.mean = checkpoint.get('mean')
        self.std = checkpoint.get('std')
        print(f"[OK] Loaded LSTM model from {model_path}")
    
    def save_model(self, model_path: str):
        """Save model weights and normalization stats"""
        checkpoint = {
            'model_state_dict': self.model.state_dict(),
            'mean': self.mean,
            'std': self.std
        }
        torch.save(checkpoint, model_path)
        print(f"[OK] Saved LSTM model to {model_path}")
    
    def fit_scaler(self, data: pd.DataFrame):
        """Fit normalization statistics"""
        metric_data = data[self.METRIC_NAMES].values
        self.mean = metric_data.mean(axis=0)
        self.std = metric_data.std(axis=0) + 1e-8  # Avoid division by zero
    
    def normalize(self, data: np.ndarray) -> np.ndarray:
        """Normalize data using fitted statistics"""
        if self.mean is None or self.std is None:
            raise ValueError("Scaler not fitted. Call fit_scaler() first.")
        return (data - self.mean) / self.std
    
    def denormalize(self, data: np.ndarray) -> np.ndarray:
        """Denormalize data"""
        if self.mean is None or self.std is None:
            raise ValueError("Scaler not fitted.")
        return data * self.std + self.mean
    
    def forecast(
        self,
        historical_data: pd.DataFrame,
        horizon: str = '24h',
        return_confidence: bool = True
    ) -> ForecastResult:
        """
        Generate multi-step forecast
        
        Args:
            historical_data: DataFrame with recent time-series data
                Must contain columns: timestamp + METRIC_NAMES
                Must have at least sequence_length rows
            horizon: '1h', '6h', or '24h'
            return_confidence: Whether to compute confidence intervals
        
        Returns:
            ForecastResult with predictions and confidence intervals
        """
        # Parse horizon
        horizon_map = {'1h': 1, '6h': 6, '24h': 24}
        horizon_steps = horizon_map.get(horizon, 24)
        
        # Prepare input sequence
        X = self._prepare_input(historical_data)
        
        # Run inference
        self.model.eval()
        
        if return_confidence:
            # Monte Carlo dropout for confidence intervals
            mean, lower, upper = self.model.predict_with_confidence(X, num_samples=100)
            forecast_values = mean[0, :horizon_steps, :].cpu().numpy()
            lower_bound = lower[0, :horizon_steps, :].cpu().numpy()
            upper_bound = upper[0, :horizon_steps, :].cpu().numpy()
        else:
            with torch.no_grad():
                forecast, _, attention = self.model(X, return_attention=True)
            forecast_values = forecast[0, :horizon_steps, :].cpu().numpy()
            lower_bound = forecast_values  # No confidence intervals
            upper_bound = forecast_values
        
        # Denormalize
        forecast_values = self.denormalize(forecast_values)
        lower_bound = self.denormalize(lower_bound)
        upper_bound = self.denormalize(upper_bound)
        
        return ForecastResult(
            values=forecast_values,
            confidence_intervals=(lower_bound, upper_bound),
            attention_weights=attention.cpu().numpy() if attention is not None else None
        )
    
    def _prepare_input(self, data: pd.DataFrame) -> torch.Tensor:
        """
        Prepare input tensor from DataFrame
        
        Args:
            data: DataFrame with metric columns
        
        Returns:
            Tensor of shape (1, sequence_length, input_dim)
        """
        # Extract last sequence_length rows
        if len(data) < self.sequence_length:
            raise ValueError(f"Need at least {self.sequence_length} time steps, got {len(data)}")
        
        recent_data = data.tail(self.sequence_length)
        
        # Extract metric values
        metric_values = recent_data[self.METRIC_NAMES].values
        
        # Normalize
        metric_values = self.normalize(metric_values)
        
        # Convert to tensor
        X = torch.tensor(metric_values, dtype=torch.float32).unsqueeze(0)  # Add batch dim
        X = X.to(self.device)
        
        return X
    
    def forecast_multiple_assets(
        self,
        asset_data: Dict[str, pd.DataFrame],
        horizon: str = '24h'
    ) -> Dict[str, ForecastResult]:
        """
        Forecast for multiple assets
        
        Args:
            asset_data: Dict mapping asset_id -> historical DataFrame
            horizon: Forecast horizon
        
        Returns:
            Dict mapping asset_id -> ForecastResult
        """
        results = {}
        
        for asset_id, data in asset_data.items():
            try:
                result = self.forecast(data, horizon=horizon)
                results[asset_id] = result
            except Exception as e:
                print(f"[WARNING] Failed to forecast for {asset_id}: {e}")
        
        return results


def create_forecast_dataset(
    metrics_df: pd.DataFrame,
    sequence_length: int = 48,
    forecast_horizon: int = 24
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Create sliding window dataset for LSTM training
    
    Args:
        metrics_df: Time-series metrics DataFrame
        sequence_length: Input sequence length
        forecast_horizon: Forecast horizon
    
    Returns:
        X: Input sequences (num_samples, sequence_length, num_metrics)
        y: Target sequences (num_samples, forecast_horizon, num_metrics)
    """
    metric_cols = LSTMForecaster.METRIC_NAMES
    data = metrics_df[metric_cols].values
    
    X_list = []
    y_list = []
    
    # Sliding window
    for i in range(len(data) - sequence_length - forecast_horizon + 1):
        X_list.append(data[i:i + sequence_length])
        y_list.append(data[i + sequence_length:i + sequence_length + forecast_horizon])
    
    X = np.array(X_list)
    y = np.array(y_list)
    
    return X, y
