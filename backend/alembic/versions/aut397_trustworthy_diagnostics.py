"""AUT-397: Trustworthy AI Diagnostics — evidence, confidence rationale, known vs inferred, limitations, feedback

Add columns to diagnostics table for:
- evidence: raw DTC/freeze-frame/PID context
- confidence_rationale: human-readable explanation of confidence score
- known_vs_inferred: separate observed facts from deduced estimates
- limitations: mandatory disclaimer (rule-based, not physical inspection)
- feedback_helpful: user feedback (helpful/not)
- feedback_comment: optional user comment
- feedback_at: when feedback was given

AUT-510 pattern: DDL ops are guarded so DBs where columns were created by
bootstrap's create_all fallback apply cleanly as no-ops.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "aut397"
down_revision: Union[str, None] = "m3rge08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def _has_table(name: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()


def _has_column(table: str, column: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns(table)}
    return column in cols


def upgrade() -> None:
    if not _has_table("diagnostics"):
        return

    bind = op.get_bind()
    if _online():
        # evidence
        if not _has_column("diagnostics", "evidence"):
            op.add_column(
                "diagnostics",
                sa.Column("evidence", sa.Text, nullable=True),
            )
        # confidence_rationale
        if not _has_column("diagnostics", "confidence_rationale"):
            op.add_column(
                "diagnostics",
                sa.Column("confidence_rationale", sa.Text, nullable=True),
            )
        # known_vs_inferred
        if not _has_column("diagnostics", "known_vs_inferred"):
            op.add_column(
                "diagnostics",
                sa.Column("known_vs_inferred", sa.Text, nullable=True),
            )
        # limitations
        if not _has_column("diagnostics", "limitations"):
            op.add_column(
                "diagnostics",
                sa.Column("limitations", sa.Text, nullable=True),
            )
        # feedback_helpful
        if not _has_column("diagnostics", "feedback_helpful"):
            op.add_column(
                "diagnostics",
                sa.Column("feedback_helpful", sa.Boolean, nullable=True),
            )
        # feedback_comment
        if not _has_column("diagnostics", "feedback_comment"):
            op.add_column(
                "diagnostics",
                sa.Column("feedback_comment", sa.Text, nullable=True),
            )
        # feedback_at
        if not _has_column("diagnostics", "feedback_at"):
            op.add_column(
                "diagnostics",
                sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True),
            )


def downgrade() -> None:
    if not _has_table("diagnostics"):
        return
    bind = op.get_bind()
    if _online():
        for col in (
            "evidence",
            "confidence_rationale",
            "known_vs_inferred",
            "limitations",
            "feedback_helpful",
            "feedback_comment",
            "feedback_at",
        ):
            if _has_column("diagnostics", col):
                op.drop_column("diagnostics", col)