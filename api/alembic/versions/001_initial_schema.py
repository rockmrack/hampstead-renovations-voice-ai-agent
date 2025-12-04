"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2024-01-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create conversations table
    op.create_table(
        'conversations',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('phone', sa.String(20), nullable=False, index=True),
        sa.Column('channel', sa.String(20), nullable=False, default='whatsapp'),
        sa.Column('status', sa.String(20), nullable=False, default='active'),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Create messages table
    op.create_table(
        'messages',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('conversation_id', sa.UUID(), sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('direction', sa.String(10), nullable=False),  # inbound/outbound
        sa.Column('type', sa.String(20), nullable=False),  # text/audio/image
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('audio_url', sa.Text(), nullable=True),
        sa.Column('transcript', sa.Text(), nullable=True),
        sa.Column('external_id', sa.String(100), nullable=True),  # WhatsApp message ID
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'])
    op.create_index('ix_messages_created_at', 'messages', ['created_at'])

    # Create leads table
    op.create_table(
        'leads',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('phone', sa.String(20), nullable=False, unique=True),
        sa.Column('name', sa.String(200), nullable=True),
        sa.Column('email', sa.String(200), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('postcode', sa.String(10), nullable=True),
        sa.Column('project_type', sa.String(100), nullable=True),
        sa.Column('project_description', sa.Text(), nullable=True),
        sa.Column('budget_range', sa.String(50), nullable=True),
        sa.Column('timeline', sa.String(50), nullable=True),
        sa.Column('property_type', sa.String(50), nullable=True),
        sa.Column('lead_score', sa.Integer(), nullable=True),
        sa.Column('lead_tier', sa.String(20), nullable=True),
        sa.Column('urgency', sa.String(30), nullable=True),
        sa.Column('source', sa.String(50), nullable=True, default='voice_agent'),
        sa.Column('hubspot_contact_id', sa.String(50), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index('ix_leads_phone', 'leads', ['phone'])
    op.create_index('ix_leads_lead_tier', 'leads', ['lead_tier'])

    # Create bookings table
    op.create_table(
        'bookings',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('lead_id', sa.UUID(), sa.ForeignKey('leads.id'), nullable=True),
        sa.Column('phone', sa.String(20), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('email', sa.String(200), nullable=True),
        sa.Column('address', sa.Text(), nullable=False),
        sa.Column('postcode', sa.String(10), nullable=True),
        sa.Column('project_type', sa.String(100), nullable=True),
        sa.Column('booking_date', sa.Date(), nullable=False),
        sa.Column('booking_time', sa.Time(), nullable=False),
        sa.Column('duration_minutes', sa.Integer(), nullable=False, default=60),
        sa.Column('status', sa.String(20), nullable=False, default='confirmed'),
        sa.Column('calendar_event_id', sa.String(200), nullable=True),
        sa.Column('confirmation_sent', sa.Boolean(), default=False),
        sa.Column('reminder_sent', sa.Boolean(), default=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index('ix_bookings_phone', 'bookings', ['phone'])
    op.create_index('ix_bookings_booking_date', 'bookings', ['booking_date'])
    op.create_index('ix_bookings_status', 'bookings', ['status'])

    # Create call_logs table
    op.create_table(
        'call_logs',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('conversation_id', sa.UUID(), sa.ForeignKey('conversations.id'), nullable=True),
        sa.Column('phone', sa.String(20), nullable=False),
        sa.Column('direction', sa.String(10), nullable=False),  # inbound/outbound
        sa.Column('vapi_call_id', sa.String(100), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('transcript', sa.Text(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('sentiment', sa.String(20), nullable=True),
        sa.Column('outcome', sa.String(50), nullable=True),  # booking_made/callback_requested/info_provided
        sa.Column('recording_url', sa.Text(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_call_logs_phone', 'call_logs', ['phone'])
    op.create_index('ix_call_logs_vapi_call_id', 'call_logs', ['vapi_call_id'])

    # Create escalations table
    op.create_table(
        'escalations',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('conversation_id', sa.UUID(), sa.ForeignKey('conversations.id'), nullable=True),
        sa.Column('phone', sa.String(20), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('urgency', sa.String(20), nullable=False),  # immediate/same-day/next-day
        sa.Column('status', sa.String(20), nullable=False, default='pending'),
        sa.Column('assigned_to', sa.String(100), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index('ix_escalations_phone', 'escalations', ['phone'])
    op.create_index('ix_escalations_status', 'escalations', ['status'])


def downgrade() -> None:
    op.drop_table('escalations')
    op.drop_table('call_logs')
    op.drop_table('bookings')
    op.drop_table('leads')
    op.drop_table('messages')
    op.drop_table('conversations')
