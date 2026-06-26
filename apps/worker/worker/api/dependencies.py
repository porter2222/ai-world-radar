from __future__ import annotations

from collections.abc import Callable, Iterator

from sqlalchemy.orm import Session

from worker.config import ProductSettings
from worker.db.session import create_session_factory
from worker.services.product_query_service import ProductQueryService

SessionFactory = Callable[[], Session]


def default_session_factory() -> SessionFactory:
    """创建默认数据库 Session 工厂。

    输入：无，内部读取 worker `.env` / 默认数据库配置。
    输出：可被 FastAPI dependency 调用的 Session 工厂。
    """
    return create_session_factory()


def create_product_query_dependency(
    session_factory: SessionFactory,
    *,
    product_settings: ProductSettings | None = None,
) -> Callable[[], Iterator[ProductQueryService]]:
    """创建 ProductQueryService 的 FastAPI dependency。

    输入：Session 工厂和可选产品展示策略。
    输出：每次请求创建并关闭 Session 的 dependency 函数。
    """

    def get_product_query_service() -> Iterator[ProductQueryService]:
        """为一次 HTTP 请求提供产品查询服务。

        输入：FastAPI 请求上下文。
        输出：绑定当前请求 Session 的 ProductQueryService。
        """
        session = session_factory()
        try:
            yield ProductQueryService(session, product_settings=product_settings)
        finally:
            session.close()

    return get_product_query_service
