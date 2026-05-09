"""
Services package for local-coder-web.
"""
from services.search import (
    build_bm25_index,
    build_embeddings,
    select_context,
    render_context,
)

__all__ = [
    "build_bm25_index",
    "build_embeddings",
    "select_context",
    "render_context",
]