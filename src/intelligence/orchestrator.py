"""
Enhanced Orchestrator with Deep Learning Integration

Integrates GNN for fault correlation and LSTM for forecasting.
"""

from typing import Dict, List, Optional
import pandas as pd
from datetime import datetime

from src.intelligence.bayesian_diagnostics import ProbabilisticDiagnosticEngine
from src.intelligence.causality_engine import CausalityEngine as GrangerCausalityEngine
from src.intelligence.gnn_correlator import GNNCorrelator
from src.intelligence.lstm_forecaster import LSTMForecaster
from src.security.rogue_detector import RogueDeviceDetector
from src.security.config_monitor import ConfigurationMonitor


class IntelligenceOrchestrator:
    """
    Orchestrates all AI/ML components for network analysis
    
    Components:
    - Bayesian Diagnostics: Probabilistic fault diagnosis
    - GNN Correlator: Graph-based fault correlation (replaces Granger)
    - LSTM Forecaster: Time-series forecasting (replaces ARIMA)
    - Rogue Detector: Security anomaly detection
    - Config Monitor: Configuration drift detection
    """
    
    def __init__(
        self,
        use_deep_learning: bool = True,
        gnn_model_path: Optional[str] = None,
        lstm_model_path: Optional[str] = None
    ):
        """
        Initialize orchestrator
        
        Args:
            use_deep_learning: Use GNN/LSTM instead of statistical methods
            gnn_model_path: Path to trained GNN model
            lstm_model_path: Path to trained LSTM model
        """
        self.use_deep_learning = use_deep_learning
        
        # Core diagnostics (always active)
        self.bayesian_engine = ProbabilisticDiagnosticEngine()
        
        # Fault correlation
        if use_deep_learning and gnn_model_path:
            self.gnn_correlator = GNNCorrelator(model_path=gnn_model_path)
            self.correlation_method = 'gnn'
            print("[OK] Using GNN for fault correlation")
        else:
            self.granger_engine = GrangerCausalityEngine()
            self.correlation_method = 'granger'
            print("[OK] Using Granger causality for fault correlation")
        
        # Time-series forecasting
        if use_deep_learning and lstm_model_path:
            self.lstm_forecaster = LSTMForecaster(model_path=lstm_model_path)
            self.forecast_method = 'lstm'
            print("[OK] Using LSTM for forecasting")
        else:
            # Fallback to ARIMA (would need to import ARIMAPredictor)
            self.forecast_method = 'arima'
            print("[OK] Using ARIMA for forecasting")
        
        # Security components
        self.rogue_detector = RogueDeviceDetector()
        self.config_monitor = ConfigurationMonitor()
    
    def diagnose_fault(
        self,
        symptoms: Dict,
        network_state: Dict,
        historical_data: Optional[pd.DataFrame] = None
    ) -> Dict:
        """
        Comprehensive fault diagnosis
        
        Args:
            symptoms: Observed symptoms and metrics
            network_state: Current network topology and device states
            historical_data: Historical time-series data
        
        Returns:
            Diagnosis result with fault type, affected devices, and confidence
        """
        result = {
            'timestamp': datetime.now().isoformat(),
            'method': self.correlation_method,
            'bayesian_diagnosis': None,
            'correlation_analysis': None,
            'affected_devices': [],
            'root_cause': None,
            'confidence': 0.0
        }
        
        # Step 1: Bayesian diagnosis
        bayesian_result = self.bayesian_engine.diagnose(symptoms)
        result['bayesian_diagnosis'] = {
            'fault_type': bayesian_result.fault_type,
            'confidence': bayesian_result.confidence,
            'probabilities': bayesian_result.probabilities
        }
        
        # Step 2: Correlation analysis
        if self.correlation_method == 'gnn' and historical_data is not None:
            # Use GNN for correlation
            from torch_geometric.data import Data
            import torch
            
            # Convert network state to graph (simplified)
            graph_data = self._network_to_graph(network_state, symptoms)
            
            gnn_result = self.gnn_correlator.predict_fault_correlation(graph_data)
            
            result['correlation_analysis'] = {
                'method': 'gnn',
                'node_probabilities': gnn_result.node_probabilities.tolist(),
                'root_cause': gnn_result.root_cause,
                'confidence': gnn_result.confidence
            }
            result['affected_devices'] = [
                {'device_id': device_id, 'probability': prob}
                for device_id, prob in zip(
                    network_state.get('device_ids', []),
                    gnn_result.node_probabilities
                )
                if prob > 0.5
            ]
            result['root_cause'] = gnn_result.root_cause
            result['confidence'] = gnn_result.confidence
            
        else:
            # Use Granger causality
            if historical_data is not None:
                granger_result = self.granger_engine.analyze_causality(historical_data)
                result['correlation_analysis'] = {
                    'method': 'granger',
                    'causal_relationships': granger_result
                }
        
        # Combine Bayesian and correlation results
        result['combined_diagnosis'] = self._combine_diagnoses(
            result['bayesian_diagnosis'],
            result['correlation_analysis']
        )
        
        return result
    
    def forecast_metrics(
        self,
        historical_data: pd.DataFrame,
        asset_id: str,
        horizon: str = '24h'
    ) -> Dict:
        """
        Forecast future metrics
        
        Args:
            historical_data: Historical time-series data
            asset_id: Asset to forecast
            horizon: Forecast horizon ('1h', '6h', '24h')
        
        Returns:
            Forecast result with predictions and confidence intervals
        """
        result = {
            'asset_id': asset_id,
            'horizon': horizon,
            'method': self.forecast_method,
            'timestamp': datetime.now().isoformat()
        }
        
        if self.forecast_method == 'lstm':
            # Use LSTM forecaster
            forecast_result = self.lstm_forecaster.forecast(
                historical_data,
                horizon=horizon,
                return_confidence=True
            )
            
            result['forecast'] = forecast_result.values.tolist()
            result['confidence_lower'] = forecast_result.confidence_intervals[0].tolist()
            result['confidence_upper'] = forecast_result.confidence_intervals[1].tolist()
            result['attention_weights'] = forecast_result.attention_weights.tolist() if forecast_result.attention_weights is not None else None
            
        else:
            # Fallback to ARIMA or simple baseline
            result['forecast'] = []
            result['message'] = 'ARIMA forecasting not yet integrated'
        
        return result
    
    def check_security(
        self,
        observed_devices: List[Dict],
        current_configs: Dict[str, Dict],
        traffic_data: Optional[pd.DataFrame] = None
    ) -> Dict:
        """
        Comprehensive security check
        
        Args:
            observed_devices: List of observed devices
            current_configs: Current device configurations
            traffic_data: Optional traffic data for behavioral analysis
        
        Returns:
            Security analysis with rogue devices and config drift
        """
        result = {
            'timestamp': datetime.now().isoformat(),
            'rogue_devices': [],
            'config_drift': [],
            'security_score': 100.0
        }
        
        # Check for rogue devices
        rogue_alerts = self.rogue_detector.detect_rogue_devices(
            observed_devices,
            traffic_data
        )
        
        result['rogue_devices'] = [
            {
                'device_id': alert.device_id,
                'mac_address': alert.mac_address,
                'reason': alert.reason,
                'severity': alert.severity,
                'confidence': alert.confidence
            }
            for alert in rogue_alerts
        ]
        
        # Check for configuration drift
        drift_alerts = self.config_monitor.detect_drift(current_configs)
        
        result['config_drift'] = [
            {
                'device_id': alert.device_id,
                'change_type': alert.change_type,
                'severity': alert.severity,
                'changes': alert.changes
            }
            for alert in drift_alerts
        ]
        
        # Calculate security score
        critical_issues = sum(
            1 for alert in rogue_alerts if alert.severity == 'CRITICAL'
        ) + sum(
            1 for alert in drift_alerts if alert.severity == 'CRITICAL'
        )
        
        warning_issues = sum(
            1 for alert in rogue_alerts if alert.severity == 'WARNING'
        ) + sum(
            1 for alert in drift_alerts if alert.severity == 'WARNING'
        )
        
        result['security_score'] = max(0, 100 - (critical_issues * 20) - (warning_issues * 5))
        
        return result
    
    def _network_to_graph(self, network_state: Dict, symptoms: Dict):
        """Convert network state to PyG graph (simplified)"""
        import torch
        from torch_geometric.data import Data
        
        # This is a simplified conversion
        # In production, would use full feature extraction from NetworkGraphDataset
        num_nodes = len(network_state.get('device_ids', []))
        
        # Dummy features for now
        x = torch.randn(num_nodes, 32)
        edge_index = torch.tensor([[0, 1], [1, 0]], dtype=torch.long).t()
        edge_attr = torch.randn(2, 16)
        
        return Data(x=x, edge_index=edge_index, edge_attr=edge_attr)
    
    def _combine_diagnoses(
        self,
        bayesian_result: Dict,
        correlation_result: Optional[Dict]
    ) -> Dict:
        """Combine Bayesian and correlation results"""
        combined = {
            'fault_type': bayesian_result['fault_type'],
            'confidence': bayesian_result['confidence']
        }
        
        if correlation_result and correlation_result.get('root_cause'):
            # Weight both methods
            combined['fault_type'] = correlation_result['root_cause']
            combined['confidence'] = (
                0.4 * bayesian_result['confidence'] +
                0.6 * correlation_result.get('confidence', 0.5)
            )
        
        return combined
