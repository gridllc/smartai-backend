"""add role column to users

Revision ID: eeb0fc129627
Revises: 9a0fca29c633
Create Date: 2025-07-01 14:56:40.716260

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eeb0fc129627'
down_revision: Union[str, Sequence[str], None] = '9a0fca29c633'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column('users', sa.Column('role', sa.String(
        length=20), nullable=False, server_default="owner"))


def downgrade():
    op.drop_column('users', 'role')
