import networkx as nx
from typing import List
from src.data.schemas import Asset

class TopologyBuilder:
    def __init__(self, assets: List[Asset]):
        self.graph = nx.DiGraph()
        self.build_graph(assets)

    def build_graph(self, assets: List[Asset]):
        """
        Builds the graph where edges go from Parent -> Child (Dependency Flow).
        If Switch A is parent of PLC B, then failure of A affects B.
        So Edge: A -> B.
        """
        for asset in assets:
            self.graph.add_node(asset.id, type=asset.type, name=asset.name)
            if asset.parent_id:
                # Add edge from Parent to Child
                self.graph.add_edge(asset.parent_id, asset.id)

    def get_downstream_assets(self, asset_id: str) -> List[str]:
        """
        Returns a list of all asset IDs that are downstream of the given asset.
        """
        if asset_id not in self.graph:
            return []
        
        # Use simple BFS or descendants
        return list(nx.descendants(self.graph, asset_id))

    def get_upstream_impact(self, asset_id: str) -> List[str]:
        """
        Returns ancestors (who impacts me?)
        """
        if asset_id not in self.graph:
            return []
        return list(nx.ancestors(self.graph, asset_id))
