"""baseline harness schema

Revision ID: 20260303_0001
Revises:
Create Date: 2026-03-03 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260303_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "test_results",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project", sa.String(), nullable=False),
        sa.Column("test_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_results_project", "test_results", ["project"], unique=False)
    op.create_index("idx_results_run_id", "test_results", ["run_id"], unique=False)
    op.create_index("idx_results_timestamp", "test_results", ["timestamp"], unique=False)
    op.create_index("idx_results_status", "test_results", ["status"], unique=False)

    op.create_table(
        "run_history",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("parent_run_id", sa.String(), nullable=True),
        sa.Column("project", sa.String(), nullable=False),
        sa.Column("total_tests", sa.Integer(), nullable=False),
        sa.Column("passed", sa.Integer(), nullable=False),
        sa.Column("failed", sa.Integer(), nullable=False),
        sa.Column("skipped", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index("idx_run_history_project", "run_history", ["project"], unique=False)
    op.create_index("idx_run_history_timestamp", "run_history", ["timestamp"], unique=False)
    op.create_index("idx_run_history_parent_run_id", "run_history", ["parent_run_id"], unique=False)

    op.create_table(
        "traces",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_traces_run_id", "traces", ["run_id"], unique=False)
    op.create_index("idx_traces_timestamp", "traces", ["timestamp"], unique=False)
    op.create_index("idx_traces_event_type", "traces", ["event_type"], unique=False)
    op.create_index("idx_traces_status", "traces", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_traces_status", table_name="traces")
    op.drop_index("idx_traces_event_type", table_name="traces")
    op.drop_index("idx_traces_timestamp", table_name="traces")
    op.drop_index("idx_traces_run_id", table_name="traces")
    op.drop_table("traces")

    op.drop_index("idx_run_history_parent_run_id", table_name="run_history")
    op.drop_index("idx_run_history_timestamp", table_name="run_history")
    op.drop_index("idx_run_history_project", table_name="run_history")
    op.drop_table("run_history")

    op.drop_index("idx_results_status", table_name="test_results")
    op.drop_index("idx_results_timestamp", table_name="test_results")
    op.drop_index("idx_results_run_id", table_name="test_results")
    op.drop_index("idx_results_project", table_name="test_results")
    op.drop_table("test_results")

