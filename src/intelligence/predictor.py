import numpy as np
from sklearn.linear_model import LinearRegression
from typing import List, Dict, Tuple, Any, Optional
import pandas as pd

class Predictor:
    def __init__(self, use_thermal_physics: bool = True):
        self.model = LinearRegression()
        self.use_thermal_physics = use_thermal_physics
        
        # Import thermal simulator if enabled
        if self.use_thermal_physics:
            try:
                from src.intelligence.thermal_simulator import ThermalNetworkSimulator
                self.thermal_simulator = ThermalNetworkSimulator()
            except ImportError:
                self.thermal_simulator = None
                self.use_thermal_physics = False

    def predict_next(self, history: List[float], lookahead: int = 1) -> Tuple[float, str]:
        """
        Predicts the next value based on the provided history.
        Returns: (predicted_value, trend_description)
        """
        if len(history) < 2:
            return (history[-1] if history else 0.0, "Insufficient Data")

        # Prepare X (time steps) and y (values)
        X = np.array(range(len(history))).reshape(-1, 1)
        y = np.array(history)

        self.model.fit(X, y)

        # Predict next step
        next_step = np.array([[len(history) + lookahead - 1]])
        prediction = self.model.predict(next_step)[0]

        # Determine Trend
        slope = self.model.coef_[0]
        if slope > 0.5:
            trend = "Increasing Rapidly 📈"
        elif slope > 0.1:
            trend = "Increasing ↗️"
        elif slope < -0.5:
            trend = "Decreasing Rapidly 📉"
        elif slope < -0.1:
            trend = "Decreasing ↘️"
        else:
            trend = "Stable ➡️"

        return (round(prediction, 2), trend)

    def forecast_asset_metrics(self, df: pd.DataFrame, asset_id: str, metric_name: str) -> Dict[str, Any]:
        """
        Extracts history for a specific asset/metric and forecasts the next value.
        """
        # Filter for asset and metric
        mask = (df['asset_id'] == asset_id) & (df['metric_name'] == metric_name)
        series = df[mask].sort_values('timestamp')['value'].values

        if len(series) == 0:
            return {}

        # Use last 10 points for recent trend
        history = series[-10:] if len(series) > 10 else series
        
        pred, trend = self.predict_next(history)
        
        return {
            "current": series[-1],
            "prediction": pred,
            "trend": trend,
            "metric": metric_name
        }
    
    def predict_thermal_failure(
        self,
        asset_id: str,
        asset_metadata: Dict[str, Any],
        current_metrics: Dict[str, float]
    ) -> Optional[Dict[str, Any]]:
        """
        Use thermal physics to predict cable/component failure.
        
        Args:
            asset_id: Asset identifier
            asset_metadata: Asset metadata including thermal parameters
            current_metrics: Current metric values (traffic_load, etc.)
            
        Returns:
            Failure prediction dict or None if thermal simulation unavailable
        """
        if not self.use_thermal_physics or not self.thermal_simulator:
            return None
        
        # Extract thermal parameters from metadata
        cable_length = asset_metadata.get('cable_length_m', 50.0)
        ambient_temp = asset_metadata.get('ambient_temp_c', 25.0)
        age_months = asset_metadata.get('age_months', 12)
        cable_gauge = asset_metadata.get('cable_gauge', '24AWG')
        heat_dissipation = asset_metadata.get('heat_dissipation_factor', 0.8)
        
        # Get current traffic load
        traffic_load = current_metrics.get('throughput', 100.0)  # Mbps
        
        # Run thermal simulation
        prediction = self.thermal_simulator.simulate_cable_degradation(
            asset_id=asset_id,
            ambient_temp=ambient_temp,
            cable_length=cable_length,
            traffic_load=traffic_load,
            age_months=age_months,
            cable_gauge=cable_gauge,
            heat_dissipation_factor=heat_dissipation
        )
        
        # Convert to dict for JSON serialization
        return {
            "asset_id": prediction.asset_id,
            "confidence": prediction.confidence,
            "days_remaining": prediction.days_remaining,
            "failure_probability": prediction.failure_probability,
            "recommended_action": prediction.recommended_action,
            "thermal_state": {
                "operating_temp_c": prediction.thermal_state.operating_temp_c,
                "ber": prediction.thermal_state.ber,
                "snr_db": prediction.thermal_state.snr_db,
                "resistance_ohm": prediction.thermal_state.resistance_ohm
            },
            "prediction_type": "thermal_physics"
        }
    
    def combine_predictions(
        self,
        linear_pred: Dict[str, Any],
        thermal_pred: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Ensemble method combining linear regression and thermal physics.
        
        Args:
            linear_pred: Prediction from linear regression
            thermal_pred: Prediction from thermal physics (optional)
            
        Returns:
            Combined prediction with weighted confidence
        """
        if not thermal_pred:
            return linear_pred
        
        # Weight thermal physics higher for physical layer metrics
        thermal_weight = 0.7
        linear_weight = 0.3
        
        combined = {
            "linear_prediction": linear_pred,
            "thermal_prediction": thermal_pred,
            "combined_confidence": (
                linear_weight * 0.6 +  # Linear regression has moderate confidence
                thermal_weight * thermal_pred["confidence"]
            ),
            "recommended_action": thermal_pred["recommended_action"]
        }
        
        return combined
