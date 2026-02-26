"""
Unit tests for Thermal Network Simulator

Tests physics calculations, degradation modeling, and failure predictions.
"""

import pytest
import numpy as np
from src.intelligence.thermal_simulator import ThermalNetworkSimulator


class TestThermalPhysics:
    """Test core physics calculations"""
    
    def setup_method(self):
        """Setup test simulator"""
        self.simulator = ThermalNetworkSimulator()
    
    def test_current_from_traffic(self):
        """Test traffic load to current conversion"""
        # 1 Gbps should produce ~0.35A
        current = self.simulator.calculate_current_from_traffic(1000.0, "24AWG")
        assert 0.3 < current < 0.4, f"Expected ~0.35A, got {current}A"
        
        # 100 Mbps should produce ~0.035A
        current_low = self.simulator.calculate_current_from_traffic(100.0, "24AWG")
        assert 0.03 < current_low < 0.04, f"Expected ~0.035A, got {current_low}A"
    
    def test_temperature_rise_calculation(self):
        """Test temperature rise from I²R heating"""
        # Low current should produce minimal temperature rise
        delta_t_low = self.simulator.calculate_temperature_rise(
            current_rms=0.1,
            cable_length_m=50.0,
            cable_gauge="24AWG",
            heat_dissipation_factor=0.8
        )
        assert delta_t_low < 5.0, f"Low current should produce <5°C rise, got {delta_t_low}°C"
        
        # Higher current should produce more heat
        delta_t_high = self.simulator.calculate_temperature_rise(
            current_rms=0.5,
            cable_length_m=50.0,
            cable_gauge="24AWG",
            heat_dissipation_factor=0.8
        )
        assert delta_t_high > delta_t_low, "Higher current should produce more heat"
    
    def test_resistance_temperature_coefficient(self):
        """Test copper resistance increases with temperature"""
        # Resistance at 20°C (reference)
        R_20 = self.simulator.calculate_resistance_at_temp(20.0, 50.0, "24AWG")
        
        # Resistance at 60°C should be higher
        R_60 = self.simulator.calculate_resistance_at_temp(60.0, 50.0, "24AWG")
        
        assert R_60 > R_20, "Resistance should increase with temperature"
        
        # Check temperature coefficient (α = 0.00393 /°C)
        # R(60) = R(20) × [1 + 0.00393 × (60-20)]
        expected_ratio = 1 + self.simulator.ALPHA * (60 - 20)
        actual_ratio = R_60 / R_20
        
        assert abs(actual_ratio - expected_ratio) < 0.01, \
            f"Temperature coefficient mismatch: expected {expected_ratio}, got {actual_ratio}"
    
    def test_aging_factor(self):
        """Test insulation degradation over time"""
        # New cable (0 months)
        aging_new = self.simulator.calculate_aging_factor(0)
        assert aging_new == 1.0, "New cable should have no aging"
        
        # 5 year old cable (60 months)
        aging_5yr = self.simulator.calculate_aging_factor(60)
        expected_5yr = 1 + (60 / 120) * 0.15  # 7.5% degradation
        assert abs(aging_5yr - expected_5yr) < 0.01, \
            f"5-year aging mismatch: expected {expected_5yr}, got {aging_5yr}"
        
        # 10 year old cable (120 months)
        aging_10yr = self.simulator.calculate_aging_factor(120)
        expected_10yr = 1.15  # 15% degradation
        assert abs(aging_10yr - expected_10yr) < 0.01, \
            f"10-year aging mismatch: expected {expected_10yr}, got {aging_10yr}"
    
    def test_snr_degradation(self):
        """Test SNR decreases with resistance"""
        # Low resistance should give high SNR
        snr_low_r = self.simulator.calculate_snr_loss(0.5, 50.0)
        
        # High resistance should give lower SNR
        snr_high_r = self.simulator.calculate_snr_loss(2.0, 50.0)
        
        assert snr_high_r < snr_low_r, "Higher resistance should reduce SNR"
        assert snr_low_r > 20, "Good cable should have SNR > 20 dB"
    
    def test_ber_from_snr(self):
        """Test BER calculation from SNR"""
        # High SNR should give very low BER
        ber_high_snr = self.simulator.ber_from_snr(40.0)
        assert ber_high_snr < 1e-9, f"High SNR should give BER < 1e-9, got {ber_high_snr}"
        
        # Low SNR should give higher BER
        ber_low_snr = self.simulator.ber_from_snr(10.0)
        assert ber_low_snr > ber_high_snr, "Lower SNR should increase BER"
    
    def test_ber_threshold_detection(self):
        """Test failure detection at BER threshold"""
        # BER above threshold should trigger failure
        assert self.simulator.BER_THRESHOLD == 1e-9, "BER threshold should be 1e-9"
        
        # Test extrapolation
        current_ber = 1e-10
        predicted_ber = 2e-9  # Above threshold
        
        days = self.simulator.extrapolate_failure(current_ber, predicted_ber, 90)
        assert days is not None, "Should predict failure when BER exceeds threshold"
        assert 0 < days < 90, f"Failure should be within 90 days, got {days}"


class TestCableDegradation:
    """Test complete cable degradation simulation"""
    
    def setup_method(self):
        """Setup test simulator"""
        self.simulator = ThermalNetworkSimulator()
    
    def test_normal_operation(self):
        """Test cable under normal conditions"""
        prediction = self.simulator.simulate_cable_degradation(
            asset_id="test-cable",
            ambient_temp=25.0,
            cable_length=50.0,
            traffic_load=100.0,  # 100 Mbps
            age_months=12,
            cable_gauge="24AWG",
            heat_dissipation_factor=0.8
        )
        
        assert prediction.asset_id == "test-cable"
        assert prediction.confidence > 0.5, "Should have reasonable confidence"
        assert prediction.thermal_state.operating_temp_c > 25.0, "Operating temp should be above ambient"
        assert prediction.thermal_state.ber < 1e-9, "Normal operation should have low BER"
    
    def test_high_temperature_stress(self):
        """Test cable under high temperature"""
        prediction = self.simulator.simulate_cable_degradation(
            asset_id="hot-cable",
            ambient_temp=45.0,  # High ambient
            cable_length=75.0,  # Long cable
            traffic_load=800.0,  # High traffic
            age_months=60,  # Older cable
            cable_gauge="26AWG",  # Thinner gauge
            heat_dissipation_factor=0.5  # Poor ventilation
        )
        
        assert prediction.thermal_state.operating_temp_c > 50.0, "Should have elevated temperature"
        # Note: Even under stress, modern cables maintain low BER until critical failure
        # Check that temperature is elevated and recommendation is appropriate
        assert "temperature" in prediction.recommended_action.lower() or \
               "ventilation" in prediction.recommended_action.lower(), \
               "Should recommend temperature/ventilation action"
    
    def test_aging_impact(self):
        """Test impact of cable aging"""
        # New cable
        pred_new = self.simulator.simulate_cable_degradation(
            asset_id="new-cable",
            ambient_temp=25.0,
            cable_length=50.0,
            traffic_load=500.0,
            age_months=6,
            cable_gauge="24AWG",
            heat_dissipation_factor=0.8
        )
        
        # Old cable (same conditions)
        pred_old = self.simulator.simulate_cable_degradation(
            asset_id="old-cable",
            ambient_temp=25.0,
            cable_length=50.0,
            traffic_load=500.0,
            age_months=96,  # 8 years
            cable_gauge="24AWG",
            heat_dissipation_factor=0.8
        )
        
        assert pred_old.thermal_state.resistance_ohm > pred_new.thermal_state.resistance_ohm, \
            "Older cable should have higher resistance"
        assert pred_old.thermal_state.snr_db < pred_new.thermal_state.snr_db, \
            "Older cable should have lower SNR due to higher resistance"
        # Check that aging is reflected in recommendation
        assert "aging" in pred_old.recommended_action.lower() or \
               "replacement" in pred_old.recommended_action.lower(), \
               "Old cable should recommend replacement"
    
    def test_edge_cases(self):
        """Test edge cases"""
        # Zero traffic
        pred_zero = self.simulator.simulate_cable_degradation(
            asset_id="idle-cable",
            ambient_temp=25.0,
            cable_length=50.0,
            traffic_load=0.0,
            age_months=12,
            cable_gauge="24AWG",
            heat_dissipation_factor=0.8
        )
        
        assert pred_zero.thermal_state.operating_temp_c <= 25.5, \
            "Zero traffic should produce minimal temperature rise"
        
        # Very short cable
        pred_short = self.simulator.simulate_cable_degradation(
            asset_id="short-cable",
            ambient_temp=25.0,
            cable_length=1.0,
            traffic_load=1000.0,
            age_months=12,
            cable_gauge="24AWG",
            heat_dissipation_factor=0.8
        )
        
        assert pred_short.thermal_state.resistance_ohm < 0.1, \
            "Short cable should have very low resistance"


class TestWhatIfScenarios:
    """Test what-if scenario simulation"""
    
    def setup_method(self):
        """Setup test simulator"""
        self.simulator = ThermalNetworkSimulator()
    
    def test_scenario_comparison(self):
        """Test baseline vs scenario comparison"""
        base_params = {
            "ambient_temp": 25.0,
            "cable_length": 50.0,
            "traffic_load": 500.0,
            "age_months": 36,
            "cable_gauge": "24AWG",
            "heat_dissipation_factor": 0.8
        }
        
        scenario_changes = {
            "ambient_temp": 35.0,  # +10°C
            "traffic_load": 750.0  # +50% traffic
        }
        
        baseline, scenario = self.simulator.simulate_what_if_scenario(
            asset_id="test-asset",
            base_params=base_params,
            scenario_changes=scenario_changes
        )
        
        assert scenario.thermal_state.operating_temp_c > baseline.thermal_state.operating_temp_c, \
            "Scenario should have higher temperature"
        assert scenario.failure_probability >= baseline.failure_probability, \
            "Scenario should have equal or higher failure risk"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
