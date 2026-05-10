"""
Services package for local-coder-web.
"""
from services.search import (
    build_bm25_index,
    select_context,
    render_context,
    _search_cache,
    DependencyGraph,
)
from services.indexer import (
    index_folder,
    scan_repo,
    build_tree,
    build_embeddings,
)
from services.context_manager import context_manager, get_context_manager
from services.file_watcher import start_file_watcher, stop_file_watcher, get_file_watcher
from services.chat_history import conversation_store

__all__ = [
    "build_bm25_index",
    "build_embeddings",
    "select_context",
    "render_context",
    "_search_cache",
    "DependencyGraph",
    "index_folder",
    "scan_repo",
    "build_tree",
    "context_manager",
    "get_context_manager",
    "start_file_watcher",
    "stop_file_watcher",
    "get_file_watcher",
    "conversation_store",
]