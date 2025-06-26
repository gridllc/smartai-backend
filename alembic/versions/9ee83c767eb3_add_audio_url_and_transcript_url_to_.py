"""add audio_url and transcript_url to user_files

Revision ID: 9ee83c767eb3
Revises: bc277fd952af
Create Date: 2025-06-25 19:02:15.876212

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9ee83c767eb3'
down_revision: Union[str, Sequence[str], None] = 'bc277fd952af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user_files', sa.Column(
        'audio_url', sa.String(), nullable=True))
    op.add_column('user_files', sa.Column(
        'transcript_url', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('user_files', 'transcript_url')
    op.drop_column('user_files', 'audio_url')
