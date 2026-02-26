import sys
import os

# Add project root
sys.path.append(os.getcwd())

from src.data.schemas import Asset
from src.core.topology.asset_inventory import AssetInventory
from src.core.topology.topology_builder import TopologyBuilder

def test_topology():
    print("\n--- Testing Topology ---")
    
    # Create sample assets
    assets = [
        Asset(id="core-sw", name="Core Switch", type="switch", role="core"),
        Asset(id="dist-sw", name="Distribution Switch", type="switch", role="distribution", parent_id="core-sw"),
        Asset(id="edge-sw", name="Edge Switch", type="switch", role="edge", parent_id="dist-sw"),
        Asset(id="plc-1", name="PLC 1", type="plc", role="controller", parent_id="edge-sw"),
        Asset(id="plc-2", name="PLC 2", type="plc", role="controller", parent_id="edge-sw"),
        Asset(id="server", name="Server", type="server", role="db", parent_id="core-sw")
    ]
    
    # 1. Test Inventory
    print("1. Asset Inventory")
    inv = AssetInventory(assets)
    print(f"Total assets: {len(inv.get_all_ids())}")
    switches = inv.get_assets_by_type("switch")
    print(f"Switches found: {len(switches)}")
    
    # 2. Test Topology
    print("\n2. Topology Builder")
    topo = TopologyBuilder(assets)
    
    # Check dependencies
    print("Downstream of Core Switch:")
    downstream = topo.get_downstream_assets("core-sw")
    print(downstream)
    assert "plc-1" in downstream
    assert "edge-sw" in downstream
    
    print("Upstream of PLC 1:")
    upstream = topo.get_upstream_impact("plc-1")
    print(upstream)
    assert "core-sw" in upstream
    
    print("Topology verification passed!")

if __name__ == "__main__":
    test_topology()
