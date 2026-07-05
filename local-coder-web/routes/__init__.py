"""
Routes package for local-coder-web.
定义所有 API 路由。
"""
from __future__ import annotations

from fastapi import APIRouter

from .main import router as main_router
from .ask import router as ask_router
from .files import router as files_router
from .complete import router as complete_router
from .comment import router as comment_router
from .agent import router as agent_router
from .intelligence import router as intelligence_router

# Main router includes all non-agent routes
router = APIRouter()
router.include_router(main_router)
router.include_router(ask_router)
router.include_router(files_router)
router.include_router(complete_router)
router.include_router(comment_router)
router.include_router(intelligence_router)
router.include_router(agent_router, tags=["agent"])
