"""add invites table

Revision ID: ffaf0cc528bf
Revises: eeb0fc129627
Create Date: 2025-07-01 15:14:42.903614

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ffaf0cc528bf'
down_revision: Union[str, Sequence[str], None] = 'eeb0fc129627'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        'invites',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('code', sa.String, nullable=False, unique=True),
        sa.Column('owner_id', sa.Integer, sa.ForeignKey(
            'users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime, nullable=False,
                  server_default=sa.func.now()),
        sa.Column('used', sa.Boolean, nullable=False,
                  server_default=sa.text('false'))
    )


def downgrade():
    op.drop_table('invites')
