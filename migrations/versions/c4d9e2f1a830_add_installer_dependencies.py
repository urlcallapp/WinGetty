"""Add installer dependencies column

Revision ID: c4d9e2f1a830
Revises: 7d373660d724
Create Date: 2026-11-13 21:46:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4d9e2f1a830'
down_revision = '7d373660d724'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('installer', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dependencies', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('installer', schema=None) as batch_op:
        batch_op.drop_column('dependencies')
