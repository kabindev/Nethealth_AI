import sys
import os
from datetime import datetime

# Add project root
sys.path.append(os.getcwd())

from src.data.schemas import Anomaly, RootCause, Asset
from src.core.topology.topology_builder import TopologyBuilder
from src.intelligence.correlator import Correlator

def test_correlation():
    print("\n--- Testing Correlation Engine ---")
    
    # 1. Setup Topology
    # Core Switch -> Edge Switch -> PLC
    assets = [
        Asset(id="core", name="Core", type="switch", role="core"),
        Asset(id="edge", name="Edge", type="switch", role="edge", parent_id="core"),
        Asset(id="plc", name="PLC", type="plc", role="controller", parent_id="edge")
    ]
    topo = TopologyBuilder(assets)
    
    # 2. Simulate Anomalies
    # Simulation: Cable failure between Core and Edge.
    # Edge switch sees CRC errors (L1).
    # PLC sees Packet Loss (L3) because Edge is bad.
    # Core is fine.
    
    anomalies = [
        Anomaly(
            id="a1", timestamp=datetime.now(), asset_id="edge", 
            metric_or_kpi="crc_error", severity="high", description="High CRC", score=0.9
        ),
        Anomaly(
            id="a2", timestamp=datetime.now(), asset_id="plc", 
            metric_or_kpi="packet_loss", severity="medium", description="Packet Loss", score=0.8
        )
    ]
    
    # 3. Correlate
    correlator = Correlator(topo)
    root_causes = correlator.correlate(anomalies)
    
    print(f"Found {len(root_causes)} root causes.")
    for rc in root_causes:
        print(f" - Root Asset: {rc.root_cause_asset_id}, Prob: {rc.probability}")
        print(f"   Desc: {rc.description}")
        
    # Validation
    # We expect 'edge' to be the root cause because it is an ancestor of 'plc'
    # and has no anomalous ancestors itself (core is not anomalous).
    
    rc_assets = [rc.root_cause_asset_id for rc in root_causes]
    assert "edge" in rc_assets
    assert "plc" not in rc_assets
    
    print("\nCorrelation logic verified: Upstream anomaly identified as root cause.")

if __name__ == "__main__":
    test_correlation()
