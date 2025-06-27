"""add user_id to user_files

Revision ID: 791d5cda01d5
Revises: 9f2a282d8325
Create Date: 2025-06-27 07:30:22.857797

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '791d5cda01d5'
down_revision: Union[str, Sequence[str], None] = '9f2a282d8325'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
