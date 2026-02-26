from typing import List, Dict, Optional
from src.data.schemas import Asset

class AssetInventory:
    def __init__(self, assets: List[Asset]):
        self.assets = assets
        self.asset_map = {a.id: a for a in assets}

    def get_asset(self, asset_id: str) -> Optional[Asset]:
        return self.asset_map.get(asset_id)

    def get_assets_by_type(self, asset_type: str) -> List[Asset]:
        return [a for a in self.assets if a.type == asset_type]

    def get_all_ids(self) -> List[str]:
        return list(self.asset_map.keys())
