"""PostgreSQL schema and immutable print audit, frozen initial revision."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(80), nullable=False, unique=True),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('admin','engineer','team_leader','viewer')", name="user_role"),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_login_attempts_source", "login_attempts", ["source"])
    op.create_index("ix_login_attempts_created_at", "login_attempts", ["created_at"])
    op.create_table(
        "templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False, unique=True),
        sa.Column("width_mm", sa.Float(), nullable=False),
        sa.Column("height_mm", sa.Float(), nullable=False),
        sa.Column("elements", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("width_mm > 0 AND height_mm > 0", name="template_dimensions"),
    )
    op.create_table(
        "printers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False, unique=True),
        sa.Column("host", sa.String(253), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("protocol", sa.String(16), nullable=False),
        sa.Column("dpi", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("location", sa.String(200), nullable=False),
        sa.Column("side", sa.String(32), nullable=False),
        sa.Column("group", sa.String(80), nullable=False),
        sa.CheckConstraint("port BETWEEN 1 AND 65535", name="printer_port"),
        sa.CheckConstraint("protocol = 'zpl'", name="printer_protocol"),
        sa.CheckConstraint("dpi IN (203,300,600)", name="printer_dpi"),
    )
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_code", sa.String(120), nullable=False, unique=True),
        sa.Column("description", sa.String(500), nullable=False),
        *[
            sa.Column(k, sa.Text(), nullable=False)
            for k in ("qr_content", "text_content", "text2", "text3", "text4")
        ],
        sa.Column("side", sa.String(32), nullable=False),
        sa.Column("highlight_right", sa.Boolean(), nullable=False),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("templates.id", ondelete="RESTRICT")),
        sa.Column(
            "preferred_printer_id", sa.Integer(), sa.ForeignKey("printers.id", ondelete="SET NULL")
        ),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_products_template_id", "products", ["template_id"])
    op.create_table(
        "settings",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
    )
    op.create_table(
        "print_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        *[
            sa.Column(k, sa.JSON(), nullable=False)
            for k in ("user_snapshot", "product_snapshot", "template_snapshot", "printer_snapshot")
        ],
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("reference", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("zpl", sa.Text()),
        sa.Column("zpl_hash", sa.String(64)),
        sa.Column(
            "original_job_id", sa.String(36), sa.ForeignKey("print_jobs.id", ondelete="RESTRICT")
        ),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_job_request"),
        sa.CheckConstraint("quantity BETWEEN 1 AND 99999", name="job_quantity"),
        sa.CheckConstraint("status IN ('queued','sent','failed')", name="job_status"),
    )
    op.create_index("ix_print_jobs_user_id", "print_jobs", ["user_id"])
    op.create_index("ix_jobs_timestamp", "print_jobs", ["created_at"])
    op.create_table(
        "import_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION protect_print_jobs() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Print audit cannot be deleted'; END IF;
          IF OLD.status <> 'queued' OR NEW.status NOT IN ('sent','failed') OR NEW.finished_at IS NULL
             OR (to_jsonb(OLD) - ARRAY['status','error','finished_at'])
                IS DISTINCT FROM (to_jsonb(NEW) - ARRAY['status','error','finished_at']) THEN
            RAISE EXCEPTION 'Print audit is immutable except a single terminal transition';
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
        op.execute(
            "CREATE TRIGGER print_jobs_immutable BEFORE UPDATE OR DELETE ON print_jobs FOR EACH ROW EXECUTE FUNCTION protect_print_jobs()"
        )
    elif op.get_bind().dialect.name == "sqlite":
        op.execute(
            "CREATE TRIGGER print_jobs_no_delete BEFORE DELETE ON print_jobs BEGIN SELECT RAISE(ABORT, 'Print audit cannot be deleted'); END"
        )
        cols = (
            "id",
            "user_id",
            "idempotency_key",
            "request_hash",
            "created_at",
            "user_snapshot",
            "product_snapshot",
            "template_snapshot",
            "printer_snapshot",
            "quantity",
            "reason",
            "note",
            "reference",
            "zpl",
            "zpl_hash",
            "original_job_id",
        )
        unchanged = " OR ".join(f"NEW.{col} IS NOT OLD.{col}" for col in cols)
        op.execute(
            f"CREATE TRIGGER print_jobs_immutable BEFORE UPDATE ON print_jobs WHEN OLD.status != 'queued' OR NEW.status NOT IN ('sent','failed') OR NEW.finished_at IS NULL OR {unchanged} BEGIN SELECT RAISE(ABORT, 'Print audit is immutable'); END"
        )


def downgrade():
    for table in (
        "import_runs",
        "print_jobs",
        "settings",
        "products",
        "printers",
        "templates",
        "login_attempts",
        "auth_sessions",
        "users",
    ):
        op.drop_table(table)
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION protect_print_jobs()")
