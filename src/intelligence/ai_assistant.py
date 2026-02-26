from typing import List, Dict, Any
import random
from src.data.schemas import Anomaly, RootCause

class AIAssistant:
    def __init__(self):
        self.context = {}
        
    def update_context(self, anomalies: List[Anomaly], kpis: Dict[str, Any], topology: Any, predictions: Dict[str, Any] = None):
        """
        Updates the internal context with the latest system state.
        """
        self.context = {
            "anomalies": anomalies,
            "kpis": kpis,
            "topology": topology,
            "predictions": predictions or {}
        }

    def generate_response(self, prompt: str) -> str:
        """
        Generates a response based on the prompt and current context.
        Simulates RAG by looking for keywords and formatting system data.
        """
        prompt = prompt.lower()
        
        # 1. Health / Status Queries
        if "health" in prompt or "status" in prompt or "how are you" in prompt:
            return self._summarize_health()
            
        # 2. Anomaly / Alert Queries
        if "anomaly" in prompt or "alert" in prompt or "problem" in prompt or "issue" in prompt:
            return self._summarize_anomalies()
            
        # 3. Root Cause Queries
        if "cause" in prompt or "why" in prompt:
            return self._explain_root_cause()
            
        # 4. Prediction Queries
        if "predict" in prompt or "forecast" in prompt or "future" in prompt:
            return self._summarize_predictions()

        # 5. Specific Asset Queries
        for asset_id in self.context.get("kpis", {}).keys():
            if asset_id.lower() in prompt:
                return self._analyze_asset(asset_id)
                
        # Default / Fallback
        return "I'm analyzing the network telemetry. You can ask me about **system health**, **active anomalies**, or **root causes**."

    def _summarize_health(self) -> str:
        kpis = self.context.get("kpis", {})
        if not kpis:
            return "I don't have enough data yet. System is initializing."
            
        # Calculate overall avg
        total = sum(d['one_score'] for d in kpis.values())
        avg = total / len(kpis)
        
        status = "Healthy"
        if avg < 60: status = "Critical"
        elif avg < 80: status = "Degraded"
        
        return f"The overall network health is **{status}** (Average ONE Score: {avg:.1f}). I am monitoring {len(kpis)} assets."

    def _summarize_anomalies(self) -> str:
        anomalies = self.context.get("anomalies", [])
        if not anomalies:
            return "✅ **No active anomalies detected.** The system is running smoothly."
            
        count = len(anomalies)
        summary = f"⚠️ **I have detected {count} active anomalies:**\n\n"
        
        for a in anomalies[:3]: # Limit to 3
            summary += f"- **{a.asset_id}**: {a.description} (Severity: {a.severity})\n"
            
        if count > 3:
            summary += f"\n*...and {count - 3} more.*"
            
        return summary

    def _explain_root_cause(self) -> str:
        anomalies = self.context.get("anomalies", [])
        if not anomalies:
            return "There are no issues to explain right now."
            
        # Look for critical anomalies that might be root causes
        # In a real system, we'd use the Correlator's output directly.
        # Here we simulate finding the "worst" one.
        
        critical_anomalies = [a for a in anomalies if a.severity in ["critical", "high"]]
        
        if not critical_anomalies:
             return "I see some minor anomalies, but no clear critical root cause yet. Monitoring continues."
             
        # Pick the most severe one (simplified)
        root = critical_anomalies[0]
        
        explanation = f"**Root Cause Analysis**:\n"
        explanation += f"It appears **{root.asset_id}** is the primary source of instability.\n"
        explanation += f"Reason: {root.description}\n"
        
        if "firewall" in root.asset_id.lower() and "dropped" in root.metric_or_kpi.lower():
             explanation += "\n🔍 **Insight**: High packet drops on a firewall often indicate a Denial of Service (DoS) attack or extreme congestion. Check DDoS mitigation systems."
        elif "crc" in root.metric_or_kpi.lower():
             explanation += "\n🔍 **Insight**: CRC errors are almost always physical. Check the cable integrity and connectors."
             
        return explanation

    def _analyze_asset(self, asset_id: str) -> str:
        kpis = self.context.get("kpis", {})
        data = kpis.get(asset_id)
        
        if not data:
            return f"I have no data for {asset_id}."
            
        score = data['one_score']
        status = "Good"
        if score < 60: status = "Critical"
        elif score < 80: status = "Warning"
        
        response = (
            f"**Analysis for {asset_id}**:\n"
            f"- Status: **{status}** (Score: {score})\n"
            f"- Network (L3): {data.get('l3_score')}\n"
            f"- Application (L7): {data.get('l7_score')}\n"
        )
        
        # Add Predictions
        preds = self.context.get("predictions", {}).get(asset_id, {})
        if preds:
            response += "\n**AI Forecast (Next 15 mins)**:\n"
            for metric, p_data in preds.items():
                response += f"- **{metric}**: Predicted {p_data['prediction']:.1f} ({p_data['trend']})\n"
                
        return response

    def _summarize_predictions(self) -> str:
        predictions = self.context.get("predictions", {})
        if not predictions:
            return "I don't have enough data to generate forecasts yet."
            
        summary = "🔮 **Network Forecast**:\n\n"
        interesting_found = False
        
        for asset_id, preds in predictions.items():
            for metric, p_data in preds.items():
                # Only show interesting trends
                if "Rapidly" in p_data['trend'] or "Increasing" in p_data['trend']:
                    summary += f"- **{asset_id}**: {metric} is {p_data['trend']} (Next: {p_data['prediction']:.1f})\n"
                    interesting_found = True
                    
        if not interesting_found:
            summary += "All metrics are forecasted to remain stable. No major fluctuations predicted."
            
        return summary
