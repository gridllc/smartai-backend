"""add UserFile table

Revision ID: 0d806488435b
Revises: c26b2643283c
Create Date: 2025-06-28 20:31:28.533756

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0d806488435b'
down_revision: Union[str, Sequence[str], None] = 'c26b2643283c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('user_files',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('filename', sa.String(), nullable=False),
    sa.Column('file_size', sa.Integer(), nullable=True),
    sa.Column('upload_timestamp', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('user_files')
    # ### end Alembic commands ###
