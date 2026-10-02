"""Preserve printserver_win single-line text behavior for imported templates."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    # Do not rebuild a templates table already referenced by products.
    op.add_column(
        "templates",
        sa.Column(
            "render_mode",
            sa.String(16),
            sa.CheckConstraint("render_mode IN ('bounded','legacy')", name="template_render_mode"),
            nullable=False,
            server_default="bounded",
        ),
    )


def downgrade():
    op.drop_column("templates", "render_mode")
