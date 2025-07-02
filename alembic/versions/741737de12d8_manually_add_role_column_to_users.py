"""Manually add role column to users

Revision ID: 741737de12d8
Revises: be557c4c2320
Create Date: 2025-07-02 07:58:23.027728

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '741737de12d8'
down_revision: Union[str, Sequence[str], None] = 'be557c4c2320'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    op.drop_column('users', 'role')
