"""add UserFile user_id foreign key

Revision ID: 0bcdc6df1f45
Revises: 0d806488435b
Create Date: 2025-06-28 21:05:41.030024

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0bcdc6df1f45'
down_revision: Union[str, Sequence[str], None] = '0d806488435b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('user_files', sa.Column('user_id', sa.Integer(), nullable=False))
    op.create_foreign_key(None, 'user_files', 'users', ['user_id'], ['id'])
    op.drop_column('user_files', 'email')
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('user_files', sa.Column('email', sa.VARCHAR(), autoincrement=False, nullable=False))
    op.drop_constraint(None, 'user_files', type_='foreignkey')
    op.drop_column('user_files', 'user_id')
    # ### end Alembic commands ###
