"""merge m3rge07 + aut3588 heads (AUT-4535)

m3rge07_merge_engineers_and_passkeys is the trunk head on main
(a3661engineers + aut3447_passkey_credentials unified in AUT-4259). This
PR adds aut3588_vehicle_is_financed, which chains off
aut3447_passkey_credentials, so after it lands the script tree has two
heads: m3rge07 and aut3588_vehicle_is_financed. Alembic then refuses
``upgrade head`` and every deploy silently falls back to ``create_all``
(same failure class as AUT-675 / AUT-918 / AUT-4259). This mergepoint
re-unifies them so the AUT-702 single-head guard passes. No schema change.

The previous mergepoint in this PR (m3rge07_merge_four_heads) referenced
aut3005_fuel_price_snapshots, aut3612_track_car_support and
aut4032_booking_requests_quotes_earnings, none of which exist on main, and
reused the m3rge07 revision id already taken by
m3rge07_merge_engineers_and_passkeys. It was stale and broken; this file
replaces it with a mergepoint over the real current heads.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "m3rge08"
down_revision: Union[str, Sequence[str], None] = (
    "m3rge07",
    "aut3588_vehicle_is_financed",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    pass

def downgrade() -> None:
    pass
