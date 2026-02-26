from sklearn.ensemble import IsolationForest
import pandas as pd
import numpy as np
from typing import List, Dict, Any
import pickle

class AnomalyDetector:
    def __init__(self, contamination: float = 0.05):
        self.model = IsolationForest(contamination=contamination, random_state=42)
        self.is_fitted = False

    def train(self, data: pd.DataFrame, features: List[str]):
        """
        Train the model on historical data.
        """
        X = data[features].fillna(0)
        self.model.fit(X)
        self.is_fitted = True

    def detect(self, data: pd.DataFrame, features: List[str]) -> pd.DataFrame:
        """
        Detect anomalies in new data.
        Returns DataFrame with 'anomaly_score' and 'is_anomaly' columns.
        """
        if not self.is_fitted:
            raise ValueError("Model not fitted yet.")

        X = data[features].fillna(0)
        
        # decision_function: lower is more anomalous. 
        # predict: -1 is anomaly, 1 is normal.
        
        scores = self.model.decision_function(X)
        preds = self.model.predict(X)
        
        results = data.copy()
        results['anomaly_score'] = scores
        results['is_anomaly'] = preds == -1
        
        return results

    def save_model(self, path: str):
        with open(path, 'wb') as f:
            pickle.dump(self.model, f)

    def load_model(self, path: str):
        with open(path, 'rb') as f:
            self.model = pickle.load(f)
        self.is_fitted = True
