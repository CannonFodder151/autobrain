"""AUT-857: Add performance indexes for common query patterns.

Revision ID: aut857_performance_indexes
Revises: aut2375_fuel_history_index
Create Date: 2026-11-27
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "aut857_performance_indexes"
down_revision = "aut2375_fuel_history_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Service records: composite index for vehicle + status + date ordering
    op.create_index(
        "ix_service_records_vehicle_status_date",
        "service_records",
        ["vehicle_id", "status", "service_date"],
    )
    
    # Service records: index for completed services ordering
    op.create_index(
        "ix_service_records_vehicle_completed_date",
        "service_records",
        ["vehicle_id", "completed_date"],
        postgresql_where="status = 'completed'",
    )
    
    # Diagnostics: index for vehicle + created_at ordering
    op.create_index(
        "ix_diagnostics_vehicle_created",
        "diagnostics",
        ["vehicle_id", "created_at"],
    )
    
    # Diagnostics: index for status filtering
    op.create_index(
        "ix_diagnostics_vehicle_status",
        "diagnostics",
        ["vehicle_id", "status"],
    )
    
    # Fuel logs: composite index for vehicle + fill_date ordering
    op.create_index(
        "ix_fuel_logs_vehicle_fill_date",
        "fuel_logs",
        ["vehicle_id", "fill_date"],
    )
    
    # Modifications: index for vehicle + created_at ordering
    op.create_index(
        "ix_modifications_vehicle_created",
        "modifications",
        ["vehicle_id", "created_at"],
    )
    
    # Valuation snapshots: index for vehicle + created_at ordering
    op.create_index(
        "ix_valuation_snapshots_vehicle_created",
        "valuation_snapshots",
        ["vehicle_id", "created_at"],
    )
    
    # Market listing cache: composite index for make + model + year
    op.create_index(
        "ix_market_listing_cache_make_model_year",
        "market_listing_cache",
        ["make", "model", "year"],
    )
    
    # Vehicle shares: index for invitee lookups
    op.create_index(
        "ix_vehicle_shares_invitee_status",
        "vehicle_shares",
        ["invitee_user_id", "status"],
    )
    
    # Vehicle events: index for vehicle + occurred_on ordering
    op.create_index(
        "ix_vehicle_events_vehicle_occurred",
        "vehicle_events",
        ["vehicle_id", "occurred_on"],
    )


def downgrade() -> None:
    op.drop_index("ix_service_records_vehicle_status_date", table_name="service_records")
    op.drop_index("ix_service_records_vehicle_completed_date", table_name="service_records")
    op.drop_index("ix_diagnostics_vehicle_created", table_name="diagnostics")
    op.drop_index("ix_diagnostics_vehicle_status", table_name="diagnostics")
    op.drop_index("ix_fuel_logs_vehicle_fill_date", table_name="fuel_logs")
    op.drop_index("ix_modifications_vehicle_created", table_name="modifications")
    op.drop_index("ix_valuation_snapshots_vehicle_created", table_name="valuation_snapshots")
    op.drop_index("ix_market_listing_cache_make_model_year", table_name="market_listing_cache")
    op.drop_index("ix_vehicle_shares_invitee_status", table_name="vehicle_shares")
    op.drop_index("ix_vehicle_events_vehicle_occurred", table_name="vehicle_events")