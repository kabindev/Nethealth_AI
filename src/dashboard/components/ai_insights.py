import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from typing import List, Dict, Any, Optional


def render_ai_insights(
    diagnosis_results: List[Dict[str, Any]],
    bayesian_diagnosis: Optional[Any] = None,
    causal_graph: Optional[Any] = None
):
    """
    Render AI insights with enhanced Bayesian and causality visualizations.
    
    Args:
        diagnosis_results: Traditional root cause analysis results
        bayesian_diagnosis: ProbabilisticDiagnosis object (if available)
        causal_graph: CausalGraph object (if available)
    """
    st.subheader("🤖 AI Root Cause Analysis")
    
    # Bayesian Probabilistic Diagnosis
    if bayesian_diagnosis:
        render_bayesian_diagnosis(bayesian_diagnosis)
        st.markdown("---")
    
    # Traditional Root Cause Analysis
    if not diagnosis_results:
        st.info("No active root causes identified. System looks healthy!")
    else:
        render_traditional_diagnosis(diagnosis_results)
    
    # Granger Causality Proof
    if causal_graph:
        st.markdown("---")
        render_granger_causality(causal_graph)


def render_bayesian_diagnosis(diagnosis):
    """Render Bayesian probabilistic diagnosis with visualization"""
    st.markdown("### 🎲 Probabilistic Diagnosis (Bayesian Network)")

    # Confidence badge with color
    conf_colors = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}
    conf_icon = conf_colors.get(diagnosis.confidence_level, "⚪")

    # Show primary probability as a real percentage (not decimal)
    primary_pct = diagnosis.primary_probability * 100
    st.markdown(f"""
    **Confidence Level**: {conf_icon} {diagnosis.confidence_level}  
    **Primary Hypothesis**: {diagnosis.primary_cause.replace('_', ' ')} — **{primary_pct:.1f}% probability**
    """)

    # Probability Distribution Bar Chart
    col1, col2 = st.columns([2, 1])

    with col1:
        causes = list(diagnosis.cause_probabilities.keys())
        probabilities = list(diagnosis.cause_probabilities.values())
        formatted_causes = [c.replace('_', ' ').title() for c in causes]

        # Check if all probabilities are effectively equal (degenerate case)
        prob_range = max(probabilities) - min(probabilities)
        all_equal = prob_range < 0.05

        # Color: primary = red, second = orange, rest = teal
        sorted_probs = sorted(probabilities, reverse=True)
        def bar_color(p):
            rank = sorted_probs.index(p)
            if rank == 0:   return '#FF4B4B'
            elif rank == 1: return '#FF8C42'
            elif rank == 2: return '#4ECDC4'
            else:           return '#2C7873'
        colors = [bar_color(p) for p in probabilities]

        # Text labels: show as "XX.X%" not ".0%" format
        text_labels = [f'{p*100:.1f}%' for p in probabilities]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=formatted_causes,
            y=[p * 100 for p in probabilities],   # multiply by 100 → show as 0-100
            marker_color=colors,
            text=text_labels,
            textposition='outside',
            hovertemplate='<b>%{x}</b><br>Probability: %{text}<extra></extra>',
        ))

        max_p_pct = max(probabilities) * 100
        fig.update_layout(
            title='Root Cause Probability Distribution',
            xaxis_title='Potential Root Cause',
            yaxis=dict(
                title='Probability (%)',
                ticksuffix='%',
                range=[0, min(max_p_pct * 1.40, 100)],
                tickfont=dict(size=11),
            ),
            height=380,
            showlegend=False,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#E0E0E0'),
        )
        st.plotly_chart(fig, use_container_width=True)

        if all_equal:
            st.caption(
                "⚠️ Probabilities are near-equal — insufficient evidence to distinguish "
                "cause. More symptoms (CRC errors, packet loss) would sharpen the diagnosis."
            )

    with col2:
        st.markdown("**Evidence Used:**")
        for var, value in diagnosis.evidence_used.items():
            color = "🔴" if value in ("High", "VeryHigh") else "🟡" if value == "Medium" else "🟢"
            st.markdown(f"- {var.replace('_',' ')}: {color} `{value}`")

        # Show what evidence is MISSING that would help
        observed = set(diagnosis.evidence_used.keys())
        all_obs = {"CRCErrors", "PacketLoss", "Latency"}
        missing = all_obs - observed
        if missing:
            st.markdown("**Missing Evidence:**")
            for m in missing:
                st.caption(f"  ➕ {m.replace('_',' ')} not observed")
    
    # Multi-Hypothesis Action Plan
    st.markdown("### 🎯 Recommended Investigation Plan")
    st.markdown("""
    The following actions are ranked by probability. Consider parallel investigation
    for high-probability hypotheses to minimize troubleshooting time.
    """)
    
    for i, action in enumerate(diagnosis.multi_hypothesis_actions, 1):
        # Extract probability from action string
        if '%' in action:
            # Color code by probability
            prob_str = action.split('- ')[-1].split(' probability')[0]
            try:
                prob_val = float(prob_str.strip('%')) / 100
                if prob_val > 0.5:
                    st.error(f"**{i}.** {action}")
                elif prob_val > 0.2:
                    st.warning(f"**{i}.** {action}")
                else:
                    st.info(f"**{i}.** {action}")
            except:
                st.write(f"**{i}.** {action}")
        else:
            st.write(f"**{i}.** {action}")
    
    # Explanation
    with st.expander("📖 Detailed Explanation"):
        st.markdown(diagnosis.explanation)


def render_traditional_diagnosis(diagnosis_results: List[Dict[str, Any]]):
    """Render traditional rule-based diagnosis"""
    st.markdown("### 🔍 Rule-Based Analysis")
    
    for res in diagnosis_results:
        rc = res['root_cause']
        explanation = res['explanation']
        
        with st.expander(
            f"🔴 Root Cause: {rc.root_cause_asset_id} ({int(rc.probability*100)}%)",
            expanded=True
        ):
            st.markdown(explanation)
            st.info(f"**Recommended Action**: {rc.recommended_action}")


def render_granger_causality(causal_graph):
    """Render Granger causality proof section"""
    with st.expander("🔗 Granger Causality Proof (Advanced)", expanded=False):
        st.markdown("""
        **What is Granger Causality?**  
        Statistical hypothesis testing that proves one time-series *causes* another
        (not just correlation). A metric X "Granger-causes" Y if past values of X
        help predict future values of Y beyond what Y's own history provides.
        """)

        # Get significant edges — CausalEdge is a dataclass, use attribute access
        if hasattr(causal_graph, 'edges') and len(causal_graph.edges) > 0:
            st.markdown("### ✅ Proven Causal Relationships (p < 0.05)")

            significant_edges = [
                edge for edge in causal_graph.edges
                if getattr(edge, 'p_value', 1.0) < 0.05
            ]

            if significant_edges:
                causal_data = []
                for edge in significant_edges:
                    # CausalEdge fields: from_metric, from_asset, to_metric, to_asset,
                    #                    strength, optimal_lag, p_value, test_type
                    source = f"{getattr(edge, 'from_asset', '?')}.{getattr(edge, 'from_metric', '?')}"
                    target = f"{getattr(edge, 'to_asset', '?')}.{getattr(edge, 'to_metric', '?')}"
                    p_value = getattr(edge, 'p_value', 1.0)
                    lag = getattr(edge, 'optimal_lag', 0)
                    strength = getattr(edge, 'strength', 0.0)

                    causal_data.append({
                        'Cause': source,
                        'Effect': target,
                        'Strength': f'{strength:.2f}',
                        'p-value': f'{p_value:.4f}',
                        'Lag (steps)': lag,
                        'Sig.': '***' if p_value < 0.001 else ('**' if p_value < 0.01 else '*'),
                    })

                import pandas as pd
                st.dataframe(pd.DataFrame(causal_data), use_container_width=True, hide_index=True)

                st.success(
                    f"💡 **{len(significant_edges)} statistically proven** causal relationships "
                    f"found via Granger hypothesis testing (p < 0.05)."
                )

                # Causal strength bar chart (top 15 edges)
                top_edges = sorted(significant_edges, key=lambda e: getattr(e, 'strength', 0), reverse=True)[:15]
                labels = [
                    f"{getattr(e,'from_metric','?')} → {getattr(e,'to_metric','?')}"
                    for e in top_edges
                ]
                strengths = [getattr(e, 'strength', 0) for e in top_edges]

                fig = go.Figure(go.Bar(
                    x=strengths,
                    y=labels,
                    orientation='h',
                    marker_color='steelblue',
                    text=[f'{s:.2f}' for s in strengths],
                    textposition='outside',
                ))
                fig.update_layout(
                    title='Top Causal Relationships by Strength',
                    xaxis_title='Causal Strength (1 − p-value)',
                    height=max(300, len(top_edges) * 28),
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=200),
                )
                st.plotly_chart(fig, use_container_width=True)

            else:
                st.info("No statistically significant causal relationships found (p ≥ 0.05)")

        else:
            st.warning(
                "⚠️ Granger causality analysis requires ≥30 time points per metric. "
                "Current dataset may be insufficient."
            )

        # Feedback loops warning (cannot use nested expander — Streamlit restriction)
        if hasattr(causal_graph, 'detect_feedback_loops'):
            loops = causal_graph.detect_feedback_loops()
            if loops:
                st.warning(f"🔄 **{len(loops)} feedback loops** detected in causal graph (expected for correlated network metrics).")
                for i, loop in enumerate(loops[:5], 1):
                    st.caption(f"{i}. {' → '.join(loop)}")
                if len(loops) > 5:
                    st.caption(f"... and {len(loops) - 5} more")