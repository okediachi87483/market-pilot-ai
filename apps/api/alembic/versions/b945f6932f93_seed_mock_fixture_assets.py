"""seed mock fixture assets

Revision ID: b945f6932f93
Revises: 973483b300ce
Create Date: 2026-08-26 19:06:55.889225

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b945f6932f93"
down_revision: Union[str, None] = "973483b300ce"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Development fixtures only — backs the deterministic mock market-data
# provider (docs/market-data.md). Not real securities data.
FIXTURE_ASSETS = [
    {"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ"},
    {"symbol": "MSFT", "name": "Microsoft Corporation", "exchange": "NASDAQ"},
    {"symbol": "NVDA", "name": "NVIDIA Corporation", "exchange": "NASDAQ"},
    {"symbol": "AMZN", "name": "Amazon.com, Inc.", "exchange": "NASDAQ"},
    {"symbol": "TSLA", "name": "Tesla, Inc.", "exchange": "NASDAQ"},
]

assets_table = sa.table(
    "assets",
    sa.column("id", UUID(as_uuid=True)),
    sa.column("symbol", sa.String),
    sa.column("name", sa.String),
    sa.column("asset_type", sa.String),
    sa.column("exchange", sa.String),
    sa.column("currency", sa.String),
    sa.column("active", sa.Boolean),
)


def upgrade() -> None:
    op.bulk_insert(
        assets_table,
        [
            {
                "id": uuid.uuid4(),
                "symbol": fixture["symbol"],
                "name": fixture["name"],
                "asset_type": "equity",
                "exchange": fixture["exchange"],
                "currency": "USD",
                "active": True,
            }
            for fixture in FIXTURE_ASSETS
        ],
    )


def downgrade() -> None:
    for fixture in FIXTURE_ASSETS:
        op.execute(
            sa.text("DELETE FROM assets WHERE symbol = :symbol").bindparams(symbol=fixture["symbol"])
        )
