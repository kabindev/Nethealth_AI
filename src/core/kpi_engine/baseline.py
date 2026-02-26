import pandas as pd
import numpy as np
from typing import Tuple

class BaselineCalculator:
    def __init__(self, window_size: int = 5):
        self.window_size = window_size

    def calculate_baseline(self, series: pd.Series) -> Tuple[pd.Series, pd.Series]:
        """
        Calculate rolling mean and standard deviation.
        Returns (mean, std).
        """
        rolling = series.rolling(window=self.window_size, min_periods=1)
        mean = rolling.mean()
        std = rolling.std().fillna(0)
        return mean, std

    def is_in_band(self, value: float, mean: float, std: float, n_std: float = 3.0) -> bool:
        """
        Check if value is within n_std of mean.
        """
        upper = mean + (n_std * std)
        lower = mean - (n_std * std)
        return lower <= value <= upper
