import asyncio
import pandas as pd
from typing import List, Dict, Any
from datetime import datetime

from src.data.loader import load_metrics, load_assets
from src.data.schemas import Anomaly, RootCause, Asset, MetricRecord
from src.core.topology.asset_inventory import AssetInventory
from src.core.topology.topology_builder import TopologyBuilder
from src.core.kpi_engine.one_score import OneScoreCalculator
from src.intelligence.anomaly_detector import AnomalyDetector
from src.intelligence.correlator import Correlator
from src.intelligence.explainer import Explainer
from src.intelligence.predictor import Predictor
from src.intelligence.thermal_simulator import ThermalNetworkSimulator
from src.intelligence.causality_engine import CausalityEngine, CausalGraph

# Layer KPI Updater (L2/L5/L6 collectors)
try:
    from src.ingestion.layer_kpi_updater import (
        LayerKPIUpdater, LayerCollectorConfig, LayerHealthSummary,
        init_layer_updater,
    )
    _LAYER_UPDATER_AVAILABLE = True
except ImportError as _e:
    _LAYER_UPDATER_AVAILABLE = False
    print(f"[WARNING] LayerKPIUpdater not available: {_e}")

class Orchestrator:
    def __init__(self):
        self.assets = []
        self.metrics = []
        self.inventory = None
        self.topology = None
        self.one_score_calc = OneScoreCalculator()
        self.anomaly_detector = AnomalyDetector()
        self.correlator = None
        self.explainer = Explainer()
        self.predictor = Predictor()
        self.thermal_simulator = ThermalNetworkSimulator()
        self.causality_engine = CausalityEngine()
        self.latest_kpis = {}
        self.latest_predictions = {}
        self.latest_thermal_predictions = {}
        self.causal_graph: CausalGraph = None

        # ── Layer KPI Updater (L2/L5/L6) ──────────────────────────────────
        self.layer_updater: 'LayerKPIUpdater' = None
        self.latest_layer_summary: 'LayerHealthSummary' = None
        if _LAYER_UPDATER_AVAILABLE:
            try:
                default_config = LayerCollectorConfig()  # demo/simulation mode
                self.layer_updater = init_layer_updater(default_config)
                print("[OK] LayerKPIUpdater initialised (L2+L5+L6 simulation mode)")
            except Exception as _e:
                print(f"[WARNING] LayerKPIUpdater init failed: {_e}")

    def load_data(self, metrics_file: str, assets_file: str):
        self.metrics = load_metrics(metrics_file)
        self.assets = load_assets(assets_file)
        
        self.inventory = AssetInventory(self.assets)
        self.topology = TopologyBuilder(self.assets)
        self.correlator = Correlator(self.topology, self.causality_engine)
        
        # Train anomaly detector on loaded metrics (simulating history)
        # Convert metrics to DataFrame for training
        if self.metrics:
            df = self._metrics_to_df(self.metrics)
            # Train on numerical columns
            self.anomaly_detector.train(df, ['value']) # Simplified to just value for now
            
    def _metrics_to_df(self, metrics: List[MetricRecord]) -> pd.DataFrame:
        data = [m.model_dump() for m in metrics]
        return pd.DataFrame(data)

    def run_kpi_pipeline(self) -> List[Anomaly]:
        """
        Compute KPIs and Detect Anomalies.
        """
        anomalies = []
        
        # Group metrics by asset and timestamp for OneScore
        # This is a bit complex, simplifying for MVP:
        # Just check each metric for detection and compute OneScore for latest state.
        
        df = self._metrics_to_df(self.metrics)
        
        # Detect Anomalies on raw metrics
        # (Real system would do this on KPIs too)
        # Including L7 metrics in detection candidates
        results = self.anomaly_detector.detect(df, ['value'])
        
        for idx, row in results.iterrows():
            if row['is_anomaly']:
                # Create Anomaly object
                # severity based on score or value
                severity = "high" if row['anomaly_score'] < -0.2 else "medium"
                
                anomaly = Anomaly(
                    id=f"evt_{idx}",
                    timestamp=row['timestamp'],
                    asset_id=row['asset_id'],
                    metric_or_kpi=row['metric_name'],
                    severity=severity,
                    description=f"Anomaly detected in {row['metric_name']}",
                    score=float(row['anomaly_score'])
                )
                anomalies.append(anomaly)
                
        # Also compute ONE Score for each asset (based on latest metrics)
        # Group by asset
        asset_groups = df.groupby('asset_id')
        for asset_id, group in asset_groups:
            # Take latest values for each metric type
            latest_metrics = group.sort_values('timestamp').groupby('metric_name').last()['value'].to_dict()
            scores = self.one_score_calc.calculate_one_score(latest_metrics)
            self.latest_kpis[asset_id] = scores
            
            # If ONE score is low, could also flag anomaly
            if scores['one_score'] < 60:
                 anomalies.append(Anomaly(
                    id=f"kpi_{asset_id}",
                    timestamp=datetime.now(),
                    asset_id=asset_id,
                    metric_or_kpi="ONE_SCORE",
                    severity="critical",
                    description=f"Health Score Critical: {scores['one_score']} (L1:{scores['l1_score']}, L3:{scores['l3_score']}, L4:{scores['l4_score']}, L7:{scores['l7_score']})",
                    score=scores['one_score']
                ))

        # Generate Predictions for critical metrics
        prediction_metrics = ['latency', 'cpu_usage', 'throughput']
        for asset_id in self.latest_kpis.keys():
            asset_preds = {}
            for metric in prediction_metrics:
                forecast = self.predictor.forecast_asset_metrics(df, asset_id, metric)
                if forecast:
                    asset_preds[metric] = forecast
            if asset_preds:
                self.latest_predictions[asset_id] = asset_preds

        # ── Update L2/L5/L6 layer scores ───────────────────────────────────
        if self.layer_updater is not None:
            try:
                # Inject existing L1/L3/L4/L7 scores from KPI engine
                if self.latest_kpis:
                    def _avg(k):
                        vals = [v.get(k, 100) for v in self.latest_kpis.values()]
                        return sum(vals) / len(vals) if vals else 100.0
                    self.layer_updater.inject_scores(
                        l1=_avg('l1_score'),
                        l3=_avg('l3_score'),
                        l4=_avg('l4_score'),
                        l7=_avg('l7_score'),
                    )

                # Run async collection in a thread — never block Streamlit render
                try:
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(asyncio.run, self.layer_updater.collect_once_now())
                        self.latest_layer_summary = future.result(timeout=8)
                except Exception:
                    # Fall back to cached summary from previous cycle
                    self.latest_layer_summary = self.layer_updater.get_current_summary()

                # ── KEY FIX: Write L2/L5/L6 scores into every asset's kpi dict
                # This ensures render_layer_heatmap() can read all 7 layers
                # from a single source (latest_kpis) rather than two separate objects
                if self.latest_layer_summary is not None:
                    ls = self.latest_layer_summary
                    for kpi_dict in self.latest_kpis.values():
                        kpi_dict['l2_score'] = ls.l2_score
                        kpi_dict['l5_score'] = ls.l5_score
                        kpi_dict['l6_score'] = ls.l6_score
                        # Recompute ONE score with full 7-layer weights
                        # Weights: L1=20% L2=15% L3=20% L4=20% L5=10% L6=10% L7=5%
                        kpi_dict['one_score'] = round(
                            kpi_dict.get('l1_score', 100) * 0.20
                            + ls.l2_score                 * 0.15
                            + kpi_dict.get('l3_score', 100) * 0.20
                            + kpi_dict.get('l4_score', 100) * 0.20
                            + ls.l5_score                 * 0.10
                            + ls.l6_score                 * 0.10
                            + kpi_dict.get('l7_score', 100) * 0.05,
                            1,
                        )
            except Exception as _e:
                print(f"[WARNING] Layer update failed: {_e}")

        return anomalies

    def run_diagnosis_pipeline(self, anomalies: List[Anomaly]) -> List[Dict[str, Any]]:
        """
        Correlate and Explain using advanced root cause analysis.
        
        If causal graph is available, uses enhanced analysis combining
        topology and Granger causality for higher confidence.
        """
        # Use advanced root cause analysis if causal graph exists
        if self.causal_graph and len(self.causal_graph) > 0:
            root_causes = self.correlator.advanced_root_cause_analysis(
                anomalies,
                self.causal_graph
            )
        else:
            # Fall back to topology-only correlation
            root_causes = self.correlator.correlate(anomalies)
        
        results = []
        for rc in root_causes:
            explanation = self.explainer.explain(rc)
            results.append({
                "root_cause": rc,
                "explanation": explanation
            })
            
        return results
    
    def run_thermal_simulation_pipeline(self) -> Dict[str, Any]:
        """
        Run thermal physics simulation for all assets with thermal metadata.
        
        Returns:
            Dictionary of thermal predictions by asset_id
        """
        thermal_predictions = {}
        
        # Convert metrics to DataFrame for easy access
        df = self._metrics_to_df(self.metrics)
        
        # Iterate through assets with thermal metadata
        for asset in self.assets:
            asset_id = asset.id
            metadata = asset.metadata if hasattr(asset, 'metadata') else {}
            
            # Check if asset has thermal metadata
            if not metadata or 'cable_length_m' not in metadata:
                continue
            
            # Get latest metrics for this asset
            asset_metrics = df[df['asset_id'] == asset_id]
            if asset_metrics.empty:
                continue
            
            # Extract current metric values
            latest_metrics = asset_metrics.sort_values('timestamp').groupby('metric_name').last()['value'].to_dict()
            
            # Run thermal prediction
            try:
                thermal_pred = self.predictor.predict_thermal_failure(
                    asset_id=asset_id,
                    asset_metadata=metadata,
                    current_metrics=latest_metrics
                )
                
                if thermal_pred:
                    thermal_predictions[asset_id] = thermal_pred
                    
            except Exception as e:
                print(f"Warning: Thermal simulation failed for {asset_id}: {e}")
                continue
        
        self.latest_thermal_predictions = thermal_predictions
        return thermal_predictions
    
    def correlate_thermal_with_anomalies(self, anomalies: List[Anomaly]) -> List[Anomaly]:
        """
        Add thermal-based anomalies to the anomaly list.
        
        Args:
            anomalies: Existing anomaly list
            
        Returns:
            Enhanced anomaly list with thermal predictions
        """
        thermal_anomalies = []
        
        for asset_id, thermal_pred in self.latest_thermal_predictions.items():
            # Create anomaly if failure predicted within 90 days
            if thermal_pred.get('days_remaining') and thermal_pred['days_remaining'] < 90:
                severity = "critical" if thermal_pred['days_remaining'] < 30 else "high"
                
                thermal_anomaly = Anomaly(
                    id=f"thermal_{asset_id}",
                    timestamp=datetime.now(),
                    asset_id=asset_id,
                    metric_or_kpi="THERMAL_FAILURE_PREDICTION",
                    severity=severity,
                    description=f"Thermal physics predicts failure in {int(thermal_pred['days_remaining'])} days. {thermal_pred['recommended_action']}",
                    score=thermal_pred['failure_probability']
                )
                thermal_anomalies.append(thermal_anomaly)
            
            # Also flag high operating temperature
            thermal_state = thermal_pred.get('thermal_state', {})
            if thermal_state.get('operating_temp_c', 0) > 60:
                temp_anomaly = Anomaly(
                    id=f"thermal_temp_{asset_id}",
                    timestamp=datetime.now(),
                    asset_id=asset_id,
                    metric_or_kpi="OPERATING_TEMPERATURE",
                    severity="medium",
                    description=f"High operating temperature: {thermal_state['operating_temp_c']:.1f}°C. Consider improving ventilation.",
                    score=0.7
                )
                thermal_anomalies.append(temp_anomaly)
        
        return anomalies + thermal_anomalies
    
    def run_causality_analysis_pipeline(self) -> CausalGraph:
        """
        Build causal graph using Granger causality tests on time-series metrics.
        
        This analyzes historical metric data to prove directional influence
        between metrics using statistical hypothesis testing.
        
        Returns:
            CausalGraph with proven causal relationships
        """
        # Convert metrics to time-series format for Granger tests
        # Group by asset and metric
        metrics_dict = {}
        
        df = self._metrics_to_df(self.metrics)
        
        for asset in self.assets:
            asset_id = asset.id
            asset_metrics = {}
            
            # Get time series for each metric type
            asset_df = df[df['asset_id'] == asset_id]
            
            if len(asset_df) < 30:
                # Need at least 30 points for reliable Granger test
                continue
            
            # Extract time series for common metrics
            metric_columns = ['value']  # Simplified - in production would extract specific metrics
            
            # Group by metric_name and get time series
            for metric_name in asset_df['metric_name'].unique():
                metric_df = asset_df[asset_df['metric_name'] == metric_name]
                if len(metric_df) >= 30:
                    # Extract values as numpy array
                    timeseries = metric_df['value'].values
                    asset_metrics[metric_name] = timeseries
            
            if asset_metrics:
                metrics_dict[asset_id] = asset_metrics
        
        # Build causal graph
        if metrics_dict:
            print(f"Building causal graph from {len(metrics_dict)} assets...")
            self.causal_graph = self.causality_engine.build_causal_graph(metrics_dict)
            print(f"Causal graph built: {len(self.causal_graph)} proven causal relationships")
            
            # Detect feedback loops
            loops = self.causal_graph.detect_feedback_loops()
            if loops:
                print(f"Warning: Detected {len(loops)} feedback loops in causal graph")
        else:
            print("Warning: Insufficient data for causal analysis (need ≥30 time points per metric)")
            self.causal_graph = CausalGraph()  # Empty graph
        
        return self.causal_graph