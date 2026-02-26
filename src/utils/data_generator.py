"""
Comprehensive Synthetic Data Generator for NetHealth AI

Generates realistic time-series data with:
- 1000+ fault scenarios across multiple fault types
- 100+ time points per metric for ARIMA/Granger analysis
- Realistic noise and correlations
- Labeled ground truth for validation
"""

import numpy as np
import pandas as pd
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any
from pathlib import Path
import argparse


class NetworkDataGenerator:
    """Generate synthetic network metrics with realistic fault patterns"""
    
    FAULT_TYPES = [
        'cable_failure',
        'emi_interference', 
        'config_error',
        'thermal_stress'
    ]
    
    ASSETS = [
        'core-switch-1',
        'edge-switch-a',
        'edge-switch-b',
        'plc-1',
        'plc-2',
        'hmi-1',
        'firewall-1'
    ]
    
    def __init__(self, seed: int = 42):
        """Initialize generator with random seed for reproducibility"""
        np.random.seed(seed)
        self.scenarios = []
        
    def generate_baseline_metrics(
        self,
        asset_id: str,
        num_points: int = 120,
        start_time: datetime = None
    ) -> pd.DataFrame:
        """
        Generate baseline (healthy) metrics for an asset.
        
        Args:
            asset_id: Asset identifier
            num_points: Number of time points to generate
            start_time: Starting timestamp
            
        Returns:
            DataFrame with baseline metrics
        """
        if start_time is None:
            start_time = datetime.now() - timedelta(hours=num_points)
        
        timestamps = [start_time + timedelta(hours=i) for i in range(num_points)]
        
        # Baseline values with realistic ranges
        baseline = {
            'latency': 5.0,  # ms
            'packet_loss': 0.01,  # %
            'throughput': 950.0,  # Mbps
            'cpu_usage': 25.0,  # %
            'snr': 35.0,  # dB
            'ber': 1e-9,  # bit error rate
            'crc_errors': 10,  # count per hour
            'temperature': 25.0,  # Celsius
            'jitter': 0.5,  # ms
            'retransmissions': 5  # count per hour
        }
        
        records = []
        for ts in timestamps:
            for metric_name, base_value in baseline.items():
                # Add realistic noise (±5%)
                noise_factor = 1 + np.random.normal(0, 0.05)
                value = base_value * noise_factor
                
                # Add daily pattern (higher load during work hours)
                hour = ts.hour
                if 8 <= hour <= 18:
                    if metric_name in ['latency', 'cpu_usage', 'throughput']:
                        value *= 1.2
                
                records.append({
                    'timestamp': ts,
                    'asset_id': asset_id,
                    'metric_name': metric_name,
                    'value': max(0, value),  # Ensure non-negative
                    'unit': self._get_unit(metric_name)
                })
        
        return pd.DataFrame(records)
    
    def inject_fault(
        self,
        baseline_df: pd.DataFrame,
        fault_type: str,
        fault_start_idx: int,
        severity: float = 0.7
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Inject a fault into baseline metrics.
        
        Args:
            baseline_df: Baseline metrics DataFrame
            fault_type: Type of fault to inject
            fault_start_idx: Time point where fault begins
            severity: Fault severity (0-1)
            
        Returns:
            Tuple of (faulted DataFrame, ground truth metadata)
        """
        df = baseline_df.copy()
        
        # Define fault signatures
        fault_signatures = {
            'cable_failure': {
                'crc_errors': lambda x: x * (1 + severity * 50),
                'packet_loss': lambda x: x * (1 + severity * 100),
                'snr': lambda x: x * (1 - severity * 0.4),
                'ber': lambda x: x * (1 + severity * 1000),
                'latency': lambda x: x * (1 + severity * 2)
            },
            'emi_interference': {
                'crc_errors': lambda x: x * (1 + severity * 30),
                'snr': lambda x: x * (1 - severity * 0.5),
                'ber': lambda x: x * (1 + severity * 500),
                'packet_loss': lambda x: x * (1 + severity * 50)
            },
            'config_error': {
                'packet_loss': lambda x: x * (1 + severity * 80),
                'latency': lambda x: x * (1 + severity * 3),
                'retransmissions': lambda x: x * (1 + severity * 40),
                'jitter': lambda x: x * (1 + severity * 10)
            },
            'thermal_stress': {
                'temperature': lambda x: x * (1 + severity * 1.5),
                'ber': lambda x: x * (1 + severity * 200),
                'snr': lambda x: x * (1 - severity * 0.3),
                'crc_errors': lambda x: x * (1 + severity * 20)
            }
        }
        
        signature = fault_signatures.get(fault_type, {})
        
        # Apply fault to metrics after fault_start_idx
        for metric_name, transform in signature.items():
            mask = (df['metric_name'] == metric_name) & (df.index >= fault_start_idx)
            df.loc[mask, 'value'] = df.loc[mask, 'value'].apply(transform)
        
        # Create ground truth metadata
        ground_truth = {
            'fault_type': fault_type,
            'fault_start_idx': fault_start_idx,
            'fault_start_time': df.iloc[fault_start_idx]['timestamp'].isoformat(),
            'severity': severity,
            'affected_asset': df.iloc[0]['asset_id'],
            'affected_metrics': list(signature.keys())
        }
        
        return df, ground_truth
    
    def generate_scenario(
        self,
        scenario_id: int,
        fault_type: str = None,
        num_points: int = 120
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Generate a complete fault scenario.
        
        Args:
            scenario_id: Unique scenario identifier
            fault_type: Type of fault (random if None)
            num_points: Number of time points
            
        Returns:
            Tuple of (metrics DataFrame, ground truth)
        """
        # Random fault type if not specified
        if fault_type is None:
            fault_type = np.random.choice(self.FAULT_TYPES)
        
        # Random asset
        asset_id = np.random.choice(self.ASSETS)
        
        # Generate baseline
        start_time = datetime.now() - timedelta(hours=num_points)
        baseline_df = self.generate_baseline_metrics(asset_id, num_points, start_time)
        
        # Inject fault at random point (after 30% of timeline)
        fault_start_idx = int(num_points * 0.3) + np.random.randint(0, int(num_points * 0.3))
        
        # Random severity
        severity = np.random.uniform(0.5, 0.9)
        
        # Inject fault
        faulted_df, ground_truth = self.inject_fault(
            baseline_df,
            fault_type,
            fault_start_idx,
            severity
        )
        
        # Add scenario metadata
        ground_truth['scenario_id'] = scenario_id
        ground_truth['num_time_points'] = num_points
        
        return faulted_df, ground_truth
    
    def generate_multi_asset_scenario(
        self,
        scenario_id: int,
        num_assets: int = 5,
        num_points: int = 120
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Generate scenario with multiple assets (fault propagation).
        
        Args:
            scenario_id: Unique scenario identifier
            num_assets: Number of assets to include
            num_points: Number of time points
            
        Returns:
            Tuple of (combined metrics DataFrame, ground truth)
        """
        # Select random assets
        selected_assets = np.random.choice(self.ASSETS, size=min(num_assets, len(self.ASSETS)), replace=False)
        
        # Primary fault asset
        primary_asset = selected_assets[0]
        fault_type = np.random.choice(self.FAULT_TYPES)
        
        all_dfs = []
        
        # Generate primary fault
        start_time = datetime.now() - timedelta(hours=num_points)
        primary_df = self.generate_baseline_metrics(primary_asset, num_points, start_time)
        fault_start_idx = int(num_points * 0.3) + np.random.randint(0, int(num_points * 0.2))
        severity = np.random.uniform(0.6, 0.9)
        
        faulted_primary_df, ground_truth = self.inject_fault(
            primary_df,
            fault_type,
            fault_start_idx,
            severity
        )
        all_dfs.append(faulted_primary_df)
        
        # Generate secondary assets (with propagated effects)
        for asset in selected_assets[1:]:
            secondary_df = self.generate_baseline_metrics(asset, num_points, start_time)
            
            # Propagated fault (lower severity, slight delay)
            propagated_start_idx = fault_start_idx + np.random.randint(2, 10)
            propagated_severity = severity * np.random.uniform(0.3, 0.6)
            
            if propagated_start_idx < num_points:
                faulted_secondary_df, _ = self.inject_fault(
                    secondary_df,
                    fault_type,
                    propagated_start_idx,
                    propagated_severity
                )
                all_dfs.append(faulted_secondary_df)
            else:
                all_dfs.append(secondary_df)
        
        # Combine all DataFrames
        combined_df = pd.concat(all_dfs, ignore_index=True)
        
        # Update ground truth
        ground_truth['scenario_id'] = scenario_id
        ground_truth['num_time_points'] = num_points
        ground_truth['num_assets'] = len(selected_assets)
        ground_truth['all_assets'] = list(selected_assets)
        ground_truth['root_cause_asset'] = primary_asset
        
        return combined_df, ground_truth
    
    def generate_dataset(
        self,
        num_scenarios: int = 1000,
        num_points: int = 120,
        multi_asset_ratio: float = 0.3
    ) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
        """
        Generate complete dataset with multiple scenarios.
        
        Args:
            num_scenarios: Number of fault scenarios to generate
            num_points: Time points per scenario
            multi_asset_ratio: Ratio of multi-asset scenarios
            
        Returns:
            Tuple of (all metrics DataFrame, ground truth list)
        """
        all_metrics = []
        all_ground_truths = []
        
        print(f"Generating {num_scenarios} scenarios...")
        
        for i in range(num_scenarios):
            if i % 100 == 0:
                print(f"  Progress: {i}/{num_scenarios}")
            
            # Decide single vs multi-asset
            if np.random.random() < multi_asset_ratio:
                metrics_df, ground_truth = self.generate_multi_asset_scenario(i, num_points=num_points)
            else:
                metrics_df, ground_truth = self.generate_scenario(i, num_points=num_points)
            
            all_metrics.append(metrics_df)
            all_ground_truths.append(ground_truth)
        
        # Combine all metrics
        combined_metrics = pd.concat(all_metrics, ignore_index=True)
        
        print(f"[OK] Generated {len(combined_metrics)} metric records across {num_scenarios} scenarios")
        
        return combined_metrics, all_ground_truths
    
    def _get_unit(self, metric_name: str) -> str:
        """Get unit for metric"""
        units = {
            'latency': 'ms',
            'packet_loss': '%',
            'throughput': 'Mbps',
            'cpu_usage': '%',
            'snr': 'dB',
            'ber': 'ratio',
            'crc_errors': 'count',
            'temperature': 'C',
            'jitter': 'ms',
            'retransmissions': 'count'
        }
        return units.get(metric_name, '')
    
    def save_dataset(
        self,
        metrics_df: pd.DataFrame,
        ground_truths: List[Dict[str, Any]],
        output_dir: str = 'data/synthetic'
    ):
        """Save generated dataset to files"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Save metrics
        metrics_file = output_path / 'metrics_extended.csv'
        metrics_df.to_csv(metrics_file, index=False)
        print(f"[OK] Saved metrics to {metrics_file}")
        
        # Save ground truth
        ground_truth_file = output_path / 'ground_truth.json'
        with open(ground_truth_file, 'w') as f:
            json.dump(ground_truths, f, indent=2, default=str)
        print(f"[OK] Saved ground truth to {ground_truth_file}")
        
        # Generate summary statistics
        self._generate_summary(metrics_df, ground_truths, output_path)
    
    def _generate_summary(
        self,
        metrics_df: pd.DataFrame,
        ground_truths: List[Dict[str, Any]],
        output_path: Path
    ):
        """Generate dataset summary statistics"""
        summary = {
            'total_scenarios': len(ground_truths),
            'total_metric_records': len(metrics_df),
            'unique_assets': metrics_df['asset_id'].nunique(),
            'unique_metrics': metrics_df['metric_name'].nunique(),
            'time_range': {
                'start': metrics_df['timestamp'].min().isoformat(),
                'end': metrics_df['timestamp'].max().isoformat()
            },
            'fault_type_distribution': {},
            'severity_stats': {
                'mean': np.mean([gt['severity'] for gt in ground_truths]),
                'std': np.std([gt['severity'] for gt in ground_truths]),
                'min': np.min([gt['severity'] for gt in ground_truths]),
                'max': np.max([gt['severity'] for gt in ground_truths])
            }
        }
        
        # Fault type distribution
        for fault_type in self.FAULT_TYPES:
            count = sum(1 for gt in ground_truths if gt['fault_type'] == fault_type)
            summary['fault_type_distribution'][fault_type] = count
        
        # Save summary
        summary_file = output_path / 'dataset_summary.json'
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        print(f"[OK] Saved summary to {summary_file}")
        
        # Print summary
        print("\n" + "="*60)
        print("DATASET SUMMARY")
        print("="*60)
        print(f"Total Scenarios: {summary['total_scenarios']}")
        print(f"Total Metric Records: {summary['total_metric_records']:,}")
        print(f"Unique Assets: {summary['unique_assets']}")
        print(f"Unique Metrics: {summary['unique_metrics']}")
        print(f"\nFault Type Distribution:")
        for fault_type, count in summary['fault_type_distribution'].items():
            print(f"  {fault_type}: {count}")
        print(f"\nSeverity Statistics:")
        print(f"  Mean: {summary['severity_stats']['mean']:.2f}")
        print(f"  Std: {summary['severity_stats']['std']:.2f}")
        print("="*60)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Generate synthetic network data')
    parser.add_argument('--scenarios', type=int, default=1000, help='Number of scenarios')
    parser.add_argument('--points', type=int, default=120, help='Time points per scenario')
    parser.add_argument('--output', type=str, default='data/synthetic', help='Output directory')
    parser.add_argument('--validate', action='store_true', help='Validate generated data')
    parser.add_argument('--seed', type=int, default=42, help='Random seed')
    
    args = parser.parse_args()
    
    # Generate data
    generator = NetworkDataGenerator(seed=args.seed)
    metrics_df, ground_truths = generator.generate_dataset(
        num_scenarios=args.scenarios,
        num_points=args.points
    )
    
    # Save data
    generator.save_dataset(metrics_df, ground_truths, args.output)
    
    # Validate if requested
    if args.validate:
        print("\n" + "="*60)
        print("VALIDATION")
        print("="*60)
        
        # Check requirements
        checks = {
            f'>={args.scenarios} scenarios': len(ground_truths) >= args.scenarios,
            f'>={args.points} time points per scenario': all(gt['num_time_points'] >= args.points for gt in ground_truths),
            'All fault types represented': len(set(gt['fault_type'] for gt in ground_truths)) == len(generator.FAULT_TYPES),
            'No missing values': not metrics_df.isnull().any().any(),
            'Positive values': (metrics_df['value'] >= 0).all()
        }
        
        for check, passed in checks.items():
            status = "[OK]" if passed else "[FAIL]"
            print(f"{status} {check}")
        
        if all(checks.values()):
            print("\n[OK] ALL VALIDATION CHECKS PASSED!")
        else:
            print("\n[FAIL] SOME VALIDATION CHECKS FAILED!")
        
        print("="*60)


if __name__ == '__main__':
    main()
