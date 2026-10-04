"""Promo-owned frozen orders and canonical archive/payment state."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0032_photo_orders'
down_revision = '0031_public_search_results'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('photo_orders',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('profile_id', sa.Uuid(), sa.ForeignKey('face_moment.browser_search_profiles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('client_request_id', sa.Text(), nullable=False),
        sa.Column('request_digest', sa.String(64), nullable=False),
        sa.Column('items', postgresql.JSONB(), nullable=False),
        sa.Column('total_kopecks', sa.Numeric(), nullable=False),
        sa.Column('email', sa.String(320), nullable=True),
        sa.Column('payment_method', sa.String(16), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('archive_status', sa.String(16), nullable=False),
        sa.Column('archive_object_key', sa.Text(), nullable=True),
        sa.Column('ready_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('archive_failure_reason', sa.Text(), nullable=True),
        sa.Column('provider_payment_id', sa.Text(), nullable=True, unique=True),
        sa.Column('payment_idempotence_key', sa.String(36), nullable=False),
        sa.Column('payment_requested_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('payment_status', sa.String(16), nullable=False),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('profile_id', 'client_request_id', name='uq_photo_order_profile_request'),
        sa.CheckConstraint("archive_status IN ('requested','preparing','ready','failed')", name='ck_photo_order_archive_status'),
        sa.CheckConstraint("payment_status IN ('not_required','pending','succeeded','canceled')", name='ck_photo_order_payment_status'),
        sa.CheckConstraint("payment_method IS NULL OR payment_method IN ('bank_card','sbp')", name='ck_photo_order_payment_method'),
        sa.CheckConstraint("total_kopecks >= 0 AND total_kopecks = trunc(total_kopecks) AND total_kopecks < 'Infinity'::numeric", name='ck_photo_order_total'),
        schema='face_moment')


def downgrade() -> None:
    op.drop_table('photo_orders', schema='face_moment')
