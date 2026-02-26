from datetime import datetime
from src.data.schemas import Anomaly, Asset
from src.core.topology.topology_builder import TopologyBuilder
from src.intelligence.correlator import Correlator

def test_upstream_dominance():
    # A -> B
    assets = [
        Asset(id="A", name="A", type="switch", role="core"),
        Asset(id="B", name="B", type="plc", role="edge", parent_id="A")
    ]
    topo = TopologyBuilder(assets)
    
    anomalies = [
        Anomaly(id="1", timestamp=datetime.now(), asset_id="A", metric_or_kpi="crc", severity="high", description="bad", score=0.9),
        Anomaly(id="2", timestamp=datetime.now(), asset_id="B", metric_or_kpi="loss", severity="med", description="bad", score=0.8)
    ]
    
    correlator = Correlator(topo)
    roots = correlator.correlate(anomalies)
    
    # A is upstream of B, and both are anomalous.
    # Root cause should be A.
    assert len(roots) == 1
    assert roots[0].root_cause_asset_id == "A"
