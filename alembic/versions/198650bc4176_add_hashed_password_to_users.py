"""add hashed_password to users

Revision ID: 198650bc4176
Revises: 791d5cda01d5
Create Date: 2025-06-27 08:07:20.011738

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '198650bc4176'
down_revision: Union[str, Sequence[str], None] = '791d5cda01d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        'users',
        sa.Column('hashed_password', sa.String(),
                  nullable=False, server_default='changeme')
    )


def downgrade():
    op.drop_column('users', 'hashed_password')
