from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Query

from worker.api.dependencies import SessionFactory, create_product_query_dependency, default_session_factory
from worker.services.product_query_service import ProductQueryService


def create_app(session_factory: SessionFactory | None = None) -> FastAPI:
    """创建 AI World Radar 产品接口 FastAPI 应用。

    输入：可选 Session 工厂；测试可注入内存数据库，生产默认读取配置。
    输出：只注册只读产品接口的 FastAPI 应用。
    """
    resolved_session_factory = session_factory or default_session_factory()
    query_dependency = create_product_query_dependency(resolved_session_factory)
    app = FastAPI(title="AI World Radar Product API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        """返回接口进程健康状态。

        输入：无。
        输出：固定健康状态 JSON，不触发数据库写入。
        """
        return {"status": "ok"}

    @app.get("/events")
    def list_events(
        service: ProductQueryService = Depends(query_dependency),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        category: str | None = None,
    ) -> dict[str, object]:
        """查询前台已发布事件列表。

        输入：分页参数、可选分类和 ProductQueryService。
        输出：包含 items、limit、offset 的列表响应。
        """
        return {
            "items": service.list_published_events(limit=limit, offset=offset, category=category),
            "limit": limit,
            "offset": offset,
        }

    @app.get("/events/{slug}")
    def get_event_detail(
        slug: str,
        service: ProductQueryService = Depends(query_dependency),
    ) -> object:
        """查询前台事件详情。

        输入：事件 slug 和 ProductQueryService。
        输出：事件详情；不存在时返回 404。
        """
        detail = service.get_event_by_slug(slug)
        if detail is None:
            raise HTTPException(status_code=404, detail="Event not found")
        return detail

    @app.get("/admin/pipeline-runs")
    def list_pipeline_runs(
        service: ProductQueryService = Depends(query_dependency),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ) -> dict[str, object]:
        """查询后台 pipeline run 列表。

        输入：分页参数和 ProductQueryService。
        输出：包含 items、limit、offset 的运行列表响应。
        """
        return {
            "items": service.list_pipeline_runs(limit=limit, offset=offset),
            "limit": limit,
            "offset": offset,
        }

    @app.get("/admin/pipeline-runs/{run_id}")
    def get_pipeline_run(
        run_id: str,
        service: ProductQueryService = Depends(query_dependency),
    ) -> object:
        """查询单次 pipeline run 详情。

        输入：pipeline run ID 和 ProductQueryService。
        输出：运行详情；不存在时返回 404。
        """
        run = service.get_pipeline_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Pipeline run not found")
        return run

    @app.get("/admin/pipeline-runs/{run_id}/agent-runs")
    def list_agent_runs(
        run_id: str,
        service: ProductQueryService = Depends(query_dependency),
    ) -> dict[str, object]:
        """查询某次 pipeline run 的 Agent 运行记录。

        输入：pipeline run ID 和 ProductQueryService。
        输出：不包含完整 raw trace 的 Agent run 列表响应。
        """
        return {"items": service.list_agent_runs(run_id)}

    @app.get("/admin/review-queue")
    def list_review_queue(
        service: ProductQueryService = Depends(query_dependency),
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ) -> dict[str, object]:
        """查询人工审核队列。

        输入：分页参数和 ProductQueryService。
        输出：包含 items、limit、offset 的人工审核队列响应。
        """
        return {
            "items": service.list_manual_review_items(limit=limit, offset=offset),
            "limit": limit,
            "offset": offset,
        }

    return app
