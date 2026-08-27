import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    symbol: str
    name: str
    asset_type: str
    exchange: str | None
    currency: str
    active: bool
    created_at: datetime
    updated_at: datetime
