from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from worker.config import load_settings
from worker.models import Base

config = getattr(context, "config", None)

if config is not None and config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """读取 Alembic 迁移使用的数据库 URL。

    输入：无，间接读取 `.env` 或环境变量。
    输出：SQLAlchemy database URL 字符串。
    """
    return load_settings().database_url


def run_migrations_offline() -> None:
    """以 offline 模式生成/执行迁移上下文。

    输入：Alembic context。
    输出：无返回值；配置 URL 和 metadata 后运行迁移。
    """
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """以 online 模式连接数据库并执行迁移。

    输入：Alembic 配置和当前环境中的 DATABASE_URL。
    输出：无返回值；连接成功后执行 migration scripts。
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if config is not None:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
