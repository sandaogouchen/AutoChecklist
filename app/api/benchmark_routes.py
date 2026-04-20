"""评测基准对比 API 路由。

提供 HTTP 端点：
- ``POST /api/v1/benchmark/runs`` — 创建评测基准对比任务
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.domain.benchmark_models import BenchmarkReport, BenchmarkRequest
from app.services.benchmark_service import BenchmarkService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/benchmark", tags=["benchmark"])


def _get_benchmark_service(request: Request) -> BenchmarkService:
    """从 app.state 中获取评测服务实例。"""
    service = getattr(request.app.state, "benchmark_service", None)
    if service is None:
        raise HTTPException(
            status_code=503,
            detail="评测基准对比服务未初始化",
        )
    return service


@router.post("/runs", response_model=BenchmarkReport)
def create_benchmark_run(
    payload: BenchmarkRequest,
    benchmark_service: BenchmarkService = Depends(_get_benchmark_service),
) -> BenchmarkReport:
    """创建一次评测基准对比任务，同步执行并返回完整报告。

    接收 AI 生成的 XMind 路径和人工基准 XMind 路径，
    执行完整的匹配→评分→聚合→改进建议流程，
    返回包含 Precision/Recall/F1 等指标的 BenchmarkReport。
    """
    try:
        return benchmark_service.run_benchmark(payload)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"XMind 文件未找到: {exc}",
        )
    except Exception as exc:
        logger.exception("评测基准对比任务执行失败")
        raise HTTPException(
            status_code=500,
            detail=f"评测执行失败: {exc}",
        )
