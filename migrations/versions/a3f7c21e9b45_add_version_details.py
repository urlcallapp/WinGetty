"""Add package version details column

Revision ID: a3f7c21e9b45
Revises: c4d9e2f1a830
Create Date: 2026-11-13 22:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3f7c21e9b45'
down_revision = 'c4d9e2f1a830'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('package_version', schema=None) as batch_op:
        batch_op.add_column(sa.Column('details', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('package_version', schema=None) as batch_op:
        batch_op.drop_column('details')
