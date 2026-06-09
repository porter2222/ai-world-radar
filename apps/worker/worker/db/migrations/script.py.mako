"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    """执行本 migration 的升级逻辑。

    输入：当前 Alembic 数据库连接。
    输出：本版本需要创建或修改的 schema。
    """
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """执行本 migration 的回滚逻辑。

    输入：当前 Alembic 数据库连接。
    输出：撤销本版本 schema 变化。
    """
    ${downgrades if downgrades else "pass"}
