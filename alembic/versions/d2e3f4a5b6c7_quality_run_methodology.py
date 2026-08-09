"""persist quality-run methodology version

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-08-09 05:35:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quality_runs",
        sa.Column(
            "methodology_version",
            sa.String(length=20),
            nullable=False,
            server_default="1",
        ),
    )
    op.execute(
        """
        UPDATE quality_runs
           SET methodology_version = '2'
         WHERE EXISTS (
           SELECT 1
             FROM jsonb_array_elements(COALESCE(findings_json, '[]'::jsonb)) AS finding
            WHERE finding ? 'analysis_status'
         )
        """
    )


def downgrade() -> None:
    op.drop_column("quality_runs", "methodology_version")
