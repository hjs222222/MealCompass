"""推荐与检索端点（薄路由：只做依赖注入与序列化，业务全在 ``services``）。

路径与现有 ``GET /health`` 保持一致，**不带** ``/api/v1`` 前缀：
前端 ``lib/api.ts`` 以 ``http://localhost:8000`` 为基址直连这两个路径。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from api.deps import get_recommend_service
from domain.models.recommend import RecommendRequest, RecommendResponse, SearchRequest, SearchResponse
from services.recommend_service import RecommendService

router = APIRouter(tags=["recommend"])
RecommendServiceDep = Annotated[RecommendService, Depends(get_recommend_service)]


@router.post("/recommend", response_model=RecommendResponse)
async def recommend(request: RecommendRequest, service: RecommendServiceDep) -> RecommendResponse:
    """跑一次推荐 Agent 闭环（解析 → 检索 → 生成 → 引用校验）。"""
    return await service.recommend(request)


@router.post("/recipes/search", response_model=SearchResponse)
async def search_recipes(request: SearchRequest, service: RecommendServiceDep) -> SearchResponse:
    """纯检索：只返回候选，不调用 LLM 生成推荐理由。"""
    return await service.search(request)
