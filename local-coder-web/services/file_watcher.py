"""
File watcher service - Monitor file changes and trigger re-indexing.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional
from dataclasses import dataclass, field
from threading import Thread, Event

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from logger import logger
from config import IGNORE_DIRS


@dataclass
class FileChange:
    """Represents a file change event."""
    path: Path
    change_type: str  # "created", "modified", "deleted", "moved"
    timestamp: float = field(default_factory=time.time)


class FileChangeHandler(FileSystemEventHandler):
    """Handle file system events."""
    
    def __init__(self, callback: Callable[[FileChange], None], ignore_patterns: set):
        self.callback = callback
        self.ignore_patterns = ignore_patterns
        self._debounce: dict[str, float] = {}
        self._debounce_seconds = 0.5
    
    def should_ignore(self, path: str) -> bool:
        """Check if path should be ignored."""
        path_obj = Path(path)
        
        # Check if any part of path matches ignore patterns
        for part in path_obj.parts:
            if part in self.ignore_patterns or part.startswith("."):
                return True
        
        return False
    
    def _debounce_check(self, path: str) -> bool:
        """Check if event should be debounced."""
        now = time.time()
        last_time = self._debounce.get(path, 0)
        
        if now - last_time < self._debounce_seconds:
            return True
        
        self._debounce[path] = now
        return False
    
    def on_created(self, event: FileSystemEvent):
        if event.is_directory:
            return
        if self.should_ignore(event.src_path):
            return
        if self._debounce_check(event.src_path):
            return
        
        logger.info(f"[FileWatcher] Created: {event.src_path}")
        self.callback(FileChange(Path(event.src_path), "created"))
    
    def on_modified(self, event: FileSystemEvent):
        if event.is_directory:
            return
        if self.should_ignore(event.src_path):
            return
        if self._debounce_check(event.src_path):
            return
        
        logger.info(f"[FileWatcher] Modified: {event.src_path}")
        self.callback(FileChange(Path(event.src_path), "modified"))
    
    def on_deleted(self, event: FileSystemEvent):
        if event.is_directory:
            return
        if self.should_ignore(event.src_path):
            return
        
        logger.info(f"[FileWatcher] Deleted: {event.src_path}")
        self.callback(FileChange(Path(event.src_path), "deleted"))
    
    def on_moved(self, event: FileSystemEvent):
        if event.is_directory:
            return
        if self.should_ignore(event.dest_path):
            return
        
        logger.info(f"[FileWatcher] Moved: {event.src_path} -> {event.dest_path}")
        self.callback(FileChange(Path(event.dest_path), "moved"))


class FileWatcher:
    """Watch directory for file changes."""
    
    def __init__(
        self,
        root: Path,
        on_change: Callable[[list[FileChange]], None],
        batch_interval: float = 2.0,
    ):
        self.root = root
        self.on_change = on_change
        self.batch_interval = batch_interval
        
        self._observer: Optional[Observer] = None
        self._changes: list[FileChange] = []
        self._batch_thread: Optional[Thread] = None
        self._stop_event = Event()
        self._lock = Event()
    
    def start(self) -> None:
        """Start watching the directory."""
        if self._observer is not None:
            logger.warning("[FileWatcher] Already running")
            return
        
        handler = FileChangeHandler(self._on_file_change, IGNORE_DIRS)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.root), recursive=True)
        self._observer.start()
        
        # Start batch processing thread
        self._stop_event.clear()
        self._batch_thread = Thread(target=self._batch_processor, daemon=True)
        self._batch_thread.start()
        
        logger.info(f"[FileWatcher] Started watching: {self.root}")
    
    def stop(self) -> None:
        """Stop watching."""
        self._stop_event.set()
        
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
        
        if self._batch_thread:
            self._batch_thread.join(timeout=5)
            self._batch_thread = None
        
        logger.info("[FileWatcher] Stopped")
    
    def _on_file_change(self, change: FileChange) -> None:
        """Handle file change event."""
        with self._lock:
            self._changes.append(change)
    
    def _batch_processor(self) -> None:
        """Process changes in batches."""
        while not self._stop_event.is_set():
            time.sleep(self.batch_interval)
            
            with self._lock:
                if not self._changes:
                    continue
                
                changes = self._changes.copy()
                self._changes.clear()
            
            # Notify callback with batch of changes
            if changes:
                logger.info(f"[FileWatcher] Batch: {len(changes)} changes")
                try:
                    self.on_change(changes)
                except Exception as e:
                    logger.error(f"[FileWatcher] Callback error: {e}")
    
    def is_running(self) -> bool:
        """Check if watcher is running."""
        return self._observer is not None and self._observer.is_alive()


# Global file watcher instance
_file_watcher: Optional[FileWatcher] = None


def start_file_watcher(
    root: Path,
    on_change: Callable[[list[FileChange]], None],
) -> FileWatcher:
    """Start file watcher for given root."""
    global _file_watcher
    
    if _file_watcher and _file_watcher.is_running():
        _file_watcher.stop()
    
    _file_watcher = FileWatcher(root, on_change)
    _file_watcher.start()
    
    return _file_watcher


def stop_file_watcher() -> None:
    """Stop file watcher."""
    global _file_watcher
    
    if _file_watcher:
        _file_watcher.stop()
        _file_watcher = None


def get_file_watcher() -> Optional[FileWatcher]:
    """Get current file watcher."""
    return _file_watcher