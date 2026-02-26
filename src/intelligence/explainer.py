from src.data.schemas import RootCause

class Explainer:
    def explain(self, root_cause: RootCause) -> str:
        """
        Generates a natural language explanation for a root cause.
        """
        confidence = "Low"
        if root_cause.probability > 0.9:
            confidence = "Very High"
        elif root_cause.probability > 0.7:
            confidence = "High"
        elif root_cause.probability > 0.5:
            confidence = "Moderate"
            
        summary = (
            f"**Root Cause Analysis**\n"
            f"Asset: {root_cause.root_cause_asset_id}\n"
            f"Issue: {root_cause.description}\n"
            f"Confidence: {confidence} ({int(root_cause.probability * 100)}%)\n"
            f"**Recommendation**: {root_cause.recommended_action}"
        )
        return summary
