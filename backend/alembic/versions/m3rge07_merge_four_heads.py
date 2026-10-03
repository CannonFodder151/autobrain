"""merge four heads: a3661engineers, aut3005, aut3612, aut4032 (AUT-4259)

a3661engineers (engineer marketplace), aut3005_fuel_price_snapshots,
aut3612_track_car_support (via aut3588/aut3447), and
aut4032_booking_requests_quotes_earnings are all heads diverging from
the common trunk. This merge re-unifies them so alembic upgrade head
has a single resolution path. No schema change.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "m3rge07"
down_revision: Union[str, Sequence[str], None] = (
    "a3661engineers",
    "aut3005_fuel_price_snapshots",
    "aut3612_track_car_support",
    "aut4032_booking_requests_quotes_earnings",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    pass

def downgrade() -> None:
    pass