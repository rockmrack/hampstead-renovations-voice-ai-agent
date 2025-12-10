"""Add new feature tables for photo analysis, summaries, follow-ups, etc.

Revision ID: 002
Revises: 001
Create Date: 2025-01-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add property analysis columns to leads table
    op.add_column("leads", sa.Column("property_analysis", sa.JSON(), nullable=True))
    op.add_column("leads", sa.Column("property_images", sa.ARRAY(sa.String()), nullable=True))
    op.add_column("leads", sa.Column("followup_count", sa.Integer(), default=0))
    op.add_column("leads", sa.Column("last_followup_at", sa.DateTime(), nullable=True))
    op.add_column("leads", sa.Column("status", sa.String(50), default="active", nullable=True))

    # Create message_log table
    op.create_table(
        "message_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id"), nullable=True),
        sa.Column("direction", sa.String(10), nullable=False),  # inbound, outbound
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("channel", sa.String(20), nullable=True),
        sa.Column("message_type", sa.String(20), nullable=True),  # response, followup, reminder
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_message_log_lead_id", "message_log", ["lead_id"])
    op.create_index("ix_message_log_created_at", "message_log", ["created_at"])

    # Create appointments table
    op.create_table(
        "appointments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lead_id", sa.Integer(), sa.ForeignKey("leads.id"), nullable=True),
        sa.Column("calendar_event_id", sa.String(255), nullable=True),
        sa.Column("appointment_time", sa.DateTime(), nullable=False),
        sa.Column("appointment_type", sa.String(50), default="site_survey", nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), default="confirmed", nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_appointments_lead_id", "appointments", ["lead_id"])
    op.create_index("ix_appointments_appointment_time", "appointments", ["appointment_time"])
    op.create_index("ix_appointments_status", "appointments", ["status"])

    # Create appointment_reminders table
    op.create_table(
        "appointment_reminders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "appointment_id",
            sa.Integer(),
            sa.ForeignKey("appointments.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("reminder_24h_sent", sa.Boolean(), default=False),
        sa.Column("reminder_2h_sent", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # Create portfolio_projects table
    op.create_table(
        "portfolio_projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("project_type", sa.String(50), nullable=True),
        sa.Column("location", sa.String(100), nullable=True),
        sa.Column("postcode_prefix", sa.String(10), nullable=True),
        sa.Column("budget_range", sa.String(50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("completion_date", sa.Date(), nullable=True),
        sa.Column("tags", sa.ARRAY(sa.String()), nullable=True),
        sa.Column("featured", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_portfolio_projects_project_type", "portfolio_projects", ["project_type"])
    op.create_index(
        "ix_portfolio_projects_postcode_prefix",
        "portfolio_projects",
        ["postcode_prefix"],
    )

    # Create portfolio_images table
    op.create_table(
        "portfolio_images",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("portfolio_projects.id"),
            nullable=False,
        ),
        sa.Column("image_url", sa.String(500), nullable=False),
        sa.Column("image_type", sa.String(20), nullable=True),  # before, after, progress
        sa.Column("caption", sa.String(255), nullable=True),
        sa.Column("display_order", sa.Integer(), default=0),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_portfolio_images_project_id", "portfolio_images", ["project_id"])

    # Create conversation_summaries table
    op.create_table(
        "conversation_summaries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("channel", sa.String(20), nullable=True),
        sa.Column("customer_name", sa.String(255), nullable=True),
        sa.Column("project_type", sa.String(100), nullable=True),
        sa.Column("budget_signals", sa.Text(), nullable=True),
        sa.Column("key_objections", sa.ARRAY(sa.String()), nullable=True),
        sa.Column("sentiment", sa.String(20), nullable=True),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("hot_lead", sa.Boolean(), default=False),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("email_sent", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_conversation_summaries_phone", "conversation_summaries", ["phone"])
    op.create_index(
        "ix_conversation_summaries_conversation_id",
        "conversation_summaries",
        ["conversation_id"],
    )

    # Create conversation_flags table
    op.create_table(
        "conversation_flags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("customer_name", sa.String(255), nullable=True),
        sa.Column("flag_reason", sa.Text(), nullable=True),
        sa.Column("sentiment", sa.String(20), nullable=True),
        sa.Column("urgency", sa.String(20), default="normal"),
        sa.Column("reviewed", sa.Boolean(), default=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_conversation_flags_phone", "conversation_flags", ["phone"])
    op.create_index("ix_conversation_flags_reviewed", "conversation_flags", ["reviewed"])
    op.create_index("ix_conversation_flags_urgency", "conversation_flags", ["urgency"])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("conversation_flags")
    op.drop_table("conversation_summaries")
    op.drop_table("portfolio_images")
    op.drop_table("portfolio_projects")
    op.drop_table("appointment_reminders")
    op.drop_table("appointments")
    op.drop_table("message_log")

    # Remove columns from leads table
    op.drop_column("leads", "status")
    op.drop_column("leads", "last_followup_at")
    op.drop_column("leads", "followup_count")
    op.drop_column("leads", "property_images")
    op.drop_column("leads", "property_analysis")
