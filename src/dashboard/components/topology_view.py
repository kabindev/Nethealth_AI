import streamlit as st
import networkx as nx
import graphviz
from typing import List
from src.data.schemas import Anomaly
from src.core.topology.topology_builder import TopologyBuilder

def render_topology(topology: TopologyBuilder, anomalies: List[Anomaly]):
    st.subheader("Network Topology")
    
    if not topology or not topology.graph:
        st.warning("No topology data available.")
        return

    # Identify anomalous assets
    anomalous_assets = {a.asset_id for a in anomalies}
    
    # Create Graphviz object with Dark Theme
    dot = graphviz.Digraph(engine='dot')
    dot.attr(rankdir='TB')
    dot.attr(bgcolor='black')
    dot.attr('node', shape='box', style='filled', fontname='Arial', fontcolor='black')
    dot.attr('edge', color='white', arrowsize='0.8')
    
    # Add Nodes
    for node in topology.graph.nodes(data=True):
        node_id = node[0]
        node_attrs = node[1]
        
        # Color logic
        fillcolor = "#aec7e8" # default light blue
        fontcolor = "black"
        
        if node_id in anomalous_assets:
            fillcolor = "#ff4b4b" # Streamlit Red
            fontcolor = "white"
        elif node_attrs.get('type') == 'switch':
            fillcolor = "#00c0f2" # Belden Blue-ish
        elif node_attrs.get('type') == 'plc':
            fillcolor = "#90ee90" # Light Green
        elif node_attrs.get('type') == 'firewall':
            fillcolor = "#ffaaaa"
            
        label = f"{node_attrs.get('name', node_id)}\n({node_attrs.get('role', node_attrs.get('type'))})"
        dot.node(node_id, label=label, fillcolor=fillcolor, fontcolor=fontcolor)
        
    # Add Edges
    for u, v in topology.graph.edges():
        dot.edge(u, v)
        
    st.graphviz_chart(dot, use_container_width=True)
