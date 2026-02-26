"""
Thermal Network Digital Twin Simulator

Physics-based network component degradation prediction using:
- Maxwell's equations for electromagnetic properties
- Thermal dynamics for temperature rise
- Material science for aging and degradation
"""

import numpy as np
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from pydantic import BaseModel
from dataclasses import dataclass


class ThermalState(BaseModel):
    """Real-time thermal state of a network component"""
    asset_id: str
    timestamp: datetime
    ambient_temp_c: float
    operating_temp_c: float
    resistance_ohm: float
    snr_db: float
    ber: float
    traffic_load_mbps: float


class FailurePrediction(BaseModel):
    """Physics-based failure prediction"""
    asset_id: str
    timestamp: datetime
    confidence: float  # 0-1
    days_remaining: Optional[float]
    failure_probability: float
    recommended_action: str
    thermal_state: ThermalState
    prediction_type: str = "thermal_physics"


class ThermalNetworkSimulator:
    """
    Predicts network degradation based on environmental conditions
    using physics-based modeling.
    """
    
    # Physics constants
    R_BASE = 0.0175  # Copper resistance at 20°C (Ω·mm²/m)
    ALPHA = 0.00393  # Temperature coefficient for copper (/°C)
    AGING_RATE = 0.15  # 15% degradation over 10 years (120 months)
    BER_THRESHOLD = 1e-9  # Bit Error Rate threshold for failure warning
    REFERENCE_TEMP = 20.0  # Reference temperature (°C)
    
    # Cable specifications (can be customized per cable type)
    CABLE_SPECS = {
        "24AWG": {"cross_section_mm2": 0.205, "max_current_a": 0.577},
        "22AWG": {"cross_section_mm2": 0.326, "max_current_a": 0.92},
        "26AWG": {"cross_section_mm2": 0.129, "max_current_a": 0.361},
    }
    
    def __init__(self):
        """Initialize the thermal network simulator"""
        pass
    
    def calculate_current_from_traffic(
        self, 
        traffic_load_mbps: float,
        cable_gauge: str = "24AWG"
    ) -> float:
        """
        Convert network traffic load to RMS current.
        
        Simplified model: Assumes PoE (Power over Ethernet) or similar
        where data traffic correlates with power consumption.
        
        Args:
            traffic_load_mbps: Network traffic in Mbps
            cable_gauge: Cable gauge specification
            
        Returns:
            RMS current in Amperes
        """
        # Simplified model: 1 Gbps ≈ 0.35A for PoE+ (25W)
        # Linear approximation for lower speeds
        base_current_per_gbps = 0.35  # Amperes per Gbps
        current_a = (traffic_load_mbps / 1000.0) * base_current_per_gbps
        
        # Cap at maximum rated current for cable gauge
        max_current = self.CABLE_SPECS.get(cable_gauge, self.CABLE_SPECS["24AWG"])["max_current_a"]
        return min(current_a, max_current)
    
    def calculate_temperature_rise(
        self,
        current_rms: float,
        cable_length_m: float,
        cable_gauge: str = "24AWG",
        heat_dissipation_factor: float = 0.8
    ) -> float:
        """
        Calculate temperature rise due to I²R heating.
        
        Args:
            current_rms: RMS current in Amperes
            cable_length_m: Cable length in meters
            cable_gauge: Cable gauge specification
            heat_dissipation_factor: Heat dissipation efficiency (0-1)
            
        Returns:
            Temperature rise in °C
        """
        # Get cable cross-section
        cross_section = self.CABLE_SPECS.get(cable_gauge, self.CABLE_SPECS["24AWG"])["cross_section_mm2"]
        
        # Calculate resistance at reference temperature
        R_cable = (self.R_BASE / cross_section) * cable_length_m
        
        # Power dissipation: P = I²R
        power_watts = (current_rms ** 2) * R_cable
        
        # Temperature rise (simplified convection model)
        # ΔT = P / (h × A) where h is heat transfer coefficient, A is surface area
        # Simplified: ΔT ≈ P × thermal_resistance
        # For typical Ethernet cables: ~10°C per Watt with poor ventilation
        thermal_resistance = 10.0 / heat_dissipation_factor  # °C/W
        
        delta_t = power_watts * thermal_resistance
        
        return delta_t
    
    def calculate_resistance_at_temp(
        self,
        temp_c: float,
        cable_length_m: float,
        cable_gauge: str = "24AWG"
    ) -> float:
        """
        Calculate cable resistance at operating temperature.
        
        Uses temperature coefficient of copper:
        R(T) = R₀ × [1 + α(T - T₀)]
        
        Args:
            temp_c: Operating temperature in °C
            cable_length_m: Cable length in meters
            cable_gauge: Cable gauge specification
            
        Returns:
            Resistance in Ohms
        """
        cross_section = self.CABLE_SPECS.get(cable_gauge, self.CABLE_SPECS["24AWG"])["cross_section_mm2"]
        
        # Base resistance at reference temperature
        R_base = (self.R_BASE / cross_section) * cable_length_m
        
        # Apply temperature coefficient
        R_actual = R_base * (1 + self.ALPHA * (temp_c - self.REFERENCE_TEMP))
        
        return R_actual
    
    def calculate_snr_loss(
        self,
        resistance_ohm: float,
        cable_length_m: float,
        frequency_mhz: float = 100.0
    ) -> float:
        """
        Calculate SNR degradation due to increased resistance.
        
        Higher resistance → higher attenuation → lower SNR
        
        Args:
            resistance_ohm: Cable resistance in Ohms
            cable_length_m: Cable length in meters
            frequency_mhz: Signal frequency in MHz
            
        Returns:
            SNR in dB
        """
        # Attenuation increases with resistance and frequency
        # Simplified model: α ≈ k × √(R × f)
        attenuation_db_per_m = 0.05 * np.sqrt(resistance_ohm * frequency_mhz / 100.0)
        total_attenuation_db = attenuation_db_per_m * cable_length_m
        
        # Assume baseline SNR of 40 dB for good cable
        baseline_snr = 40.0
        snr_db = baseline_snr - total_attenuation_db
        
        return max(snr_db, 0.0)  # SNR can't be negative
    
    def ber_from_snr(self, snr_db: float) -> float:
        """
        Calculate Bit Error Rate from Signal-to-Noise Ratio.
        
        Uses simplified BER formula for QPSK modulation:
        BER ≈ 0.5 × erfc(√(SNR_linear))
        
        Args:
            snr_db: Signal-to-Noise Ratio in dB
            
        Returns:
            Bit Error Rate
        """
        # Convert SNR from dB to linear
        snr_linear = 10 ** (snr_db / 10.0)
        
        # Calculate BER (simplified for QPSK)
        # For very high SNR, BER approaches 0
        if snr_linear > 100:
            ber = 1e-12
        else:
            # Approximation: BER ≈ 0.5 × exp(-SNR_linear)
            ber = 0.5 * np.exp(-snr_linear / 2.0)
        
        return max(ber, 1e-15)  # Floor at very low BER
    
    def calculate_aging_factor(self, age_months: int) -> float:
        """
        Calculate degradation factor due to insulation aging.
        
        Assumes linear degradation: 15% over 10 years
        
        Args:
            age_months: Age of cable in months
            
        Returns:
            Aging factor (1.0 = new, 1.15 = 10 years old)
        """
        aging_factor = 1.0 + (age_months / 120.0) * self.AGING_RATE
        return min(aging_factor, 1.5)  # Cap at 50% degradation
    
    def extrapolate_failure(
        self,
        current_ber: float,
        predicted_ber: float,
        time_horizon_days: int = 90
    ) -> Optional[float]:
        """
        Extrapolate time until failure based on BER trend.
        
        Args:
            current_ber: Current bit error rate
            predicted_ber: Predicted BER at time horizon
            time_horizon_days: Prediction time horizon
            
        Returns:
            Days until failure, or None if no failure predicted
        """
        if current_ber >= self.BER_THRESHOLD:
            return 0.0  # Already failing
        
        if predicted_ber <= self.BER_THRESHOLD:
            return None  # No failure predicted
        
        # Linear extrapolation
        ber_rate = (predicted_ber - current_ber) / time_horizon_days
        days_until_threshold = (self.BER_THRESHOLD - current_ber) / ber_rate
        
        return max(days_until_threshold, 0.0)
    
    def simulate_cable_degradation(
        self,
        asset_id: str,
        ambient_temp: float,
        cable_length: float,
        traffic_load: float,
        age_months: int,
        cable_gauge: str = "24AWG",
        heat_dissipation_factor: float = 0.8
    ) -> FailurePrediction:
        """
        Main simulation method: Predicts network degradation based on 
        environmental conditions.
        
        Args:
            asset_id: Asset identifier
            ambient_temp: Ambient temperature in °C
            cable_length: Cable length in meters
            traffic_load: Network traffic in Mbps
            age_months: Age of cable in months
            cable_gauge: Cable gauge specification
            heat_dissipation_factor: Heat dissipation efficiency (0-1)
            
        Returns:
            FailurePrediction with thermal state and recommendations
        """
        # Step 1: Calculate current from traffic load
        I_rms = self.calculate_current_from_traffic(traffic_load, cable_gauge)
        
        # Step 2: Calculate temperature rise from I²R heating
        delta_t_traffic = self.calculate_temperature_rise(
            I_rms, cable_length, cable_gauge, heat_dissipation_factor
        )
        
        # Step 3: Total operating temperature
        T_operating = ambient_temp + delta_t_traffic
        
        # Step 4: Calculate resistance at operating temperature
        R_actual = self.calculate_resistance_at_temp(T_operating, cable_length, cable_gauge)
        
        # Step 5: Apply aging factor
        aging_factor = self.calculate_aging_factor(age_months)
        R_aged = R_actual * aging_factor
        
        # Step 6: Calculate SNR degradation
        snr_db = self.calculate_snr_loss(R_aged, cable_length)
        
        # Step 7: Calculate current BER
        current_ber = self.ber_from_snr(snr_db)
        
        # Step 8: Predict future state (90 days ahead with increased aging)
        future_age_months = age_months + 3  # 90 days ≈ 3 months
        future_aging_factor = self.calculate_aging_factor(future_age_months)
        R_future = R_actual * future_aging_factor
        snr_future = self.calculate_snr_loss(R_future, cable_length)
        predicted_ber = self.ber_from_snr(snr_future)
        
        # Step 9: Extrapolate failure
        days_until_failure = self.extrapolate_failure(current_ber, predicted_ber, 90)
        
        # Step 10: Calculate confidence and failure probability
        # Confidence based on data quality (simplified: based on age and temperature)
        confidence = 0.95 if age_months > 6 else 0.75  # More data = higher confidence
        
        # Failure probability based on BER proximity to threshold
        if current_ber >= self.BER_THRESHOLD:
            failure_probability = 1.0
        else:
            failure_probability = min(current_ber / self.BER_THRESHOLD, 1.0)
        
        # Step 11: Generate recommendation
        if days_until_failure is not None and days_until_failure < 30:
            recommended_action = f"URGENT: Schedule cable replacement within {int(days_until_failure)} days"
        elif days_until_failure is not None and days_until_failure < 90:
            recommended_action = f"Schedule cable replacement during next maintenance window ({int(days_until_failure)} days)"
        elif T_operating > 60:
            recommended_action = "Monitor temperature closely. Consider improving ventilation or reducing load."
        elif age_months > 60:
            recommended_action = "Cable aging detected. Plan replacement in next 6 months."
        else:
            recommended_action = "Cable health is good. Continue monitoring."
        
        # Create thermal state
        thermal_state = ThermalState(
            asset_id=asset_id,
            timestamp=datetime.now(),
            ambient_temp_c=ambient_temp,
            operating_temp_c=T_operating,
            resistance_ohm=R_aged,
            snr_db=snr_db,
            ber=current_ber,
            traffic_load_mbps=traffic_load
        )
        
        # Create failure prediction
        prediction = FailurePrediction(
            asset_id=asset_id,
            timestamp=datetime.now(),
            confidence=confidence,
            days_remaining=days_until_failure,
            failure_probability=failure_probability,
            recommended_action=recommended_action,
            thermal_state=thermal_state,
            prediction_type="thermal_physics"
        )
        
        return prediction
    
    def simulate_what_if_scenario(
        self,
        asset_id: str,
        base_params: Dict,
        scenario_changes: Dict
    ) -> Tuple[FailurePrediction, FailurePrediction]:
        """
        Run what-if scenario analysis.
        
        Args:
            asset_id: Asset identifier
            base_params: Baseline parameters
            scenario_changes: Changes to apply (e.g., {"ambient_temp": +10})
            
        Returns:
            Tuple of (baseline_prediction, scenario_prediction)
        """
        # Run baseline simulation
        baseline = self.simulate_cable_degradation(
            asset_id=asset_id,
            **base_params
        )
        
        # Apply scenario changes
        scenario_params = base_params.copy()
        for key, value in scenario_changes.items():
            if key in scenario_params:
                # Handle relative changes (e.g., +10) vs absolute (e.g., 35)
                if isinstance(value, str) and (value.startswith('+') or value.startswith('-')):
                    scenario_params[key] += float(value)
                else:
                    scenario_params[key] = value
        
        # Run scenario simulation
        scenario = self.simulate_cable_degradation(
            asset_id=asset_id,
            **scenario_params
        )
        
        return baseline, scenario
