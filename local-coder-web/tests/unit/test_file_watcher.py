"""Tests for file watcher service."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.file_watcher import (
    FileChange, FileChangeHandler, FileWatcher,
    start_file_watcher, stop_file_watcher,
)
from watchdog.events import FileSystemEvent


class TestFileChange:
    def test_creation(self):
        fc = FileChange(path=Path("/tmp/test.py"), change_type="created")
        assert fc.path == Path("/tmp/test.py")
        assert fc.change_type == "created"
        assert fc.timestamp > 0


class TestFileChangeHandler:
    def test_should_ignore_dotfile(self):
        handler = FileChangeHandler(MagicMock(), set())
        assert handler.should_ignore(".git/config") is True

    def test_should_ignore_dirs(self):
        handler = FileChangeHandler(MagicMock(), {".git"})
        assert handler.should_ignore("src/.git/config") is True

    def test_should_not_ignore_code_file(self):
        handler = FileChangeHandler(MagicMock(), set())
        assert handler.should_ignore("src/main.py") is False

    def test_debounce(self):
        events = []
        handler = FileChangeHandler(lambda c: events.append(c), set())
        handler._debounce_seconds = 1.0
        handler.on_created(_make_event("created", "/tmp/test.py"))
        handler.on_created(_make_event("created", "/tmp/test.py"))
        assert len(events) == 1  # Second event debounced


def _make_event(event_type, path):
    """Create a mock FileSystemEvent."""
    event = MagicMock(spec=FileSystemEvent)
    event.is_directory = False
    event.src_path = path
    event.dest_path = path
    return event


class TestFileWatcher:
    def test_lock_is_mutex(self):
        """BUG-07: _lock must be a Lock, not an Event."""
        fw = FileWatcher(Path("/tmp"), MagicMock())
        # Verify it's not an Event (which doesn't support with)
        from threading import Event
        assert not isinstance(fw._lock, Event)

    def test_batch_processor(self):
        """BUG-07: Batch processor should execute correctly."""
        from unittest.mock import patch, MagicMock
        changes = []
        def on_change(chgs):
            changes.extend(chgs)

        with patch("services.file_watcher.Observer") as mock_observer_cls:
            mock_observer = MagicMock()
            mock_observer.is_alive.return_value = False
            mock_observer_cls.return_value = mock_observer

            fw = FileWatcher(Path("/tmp"), on_change, batch_interval=0.1)
            fw.start()

            # Simulate file change events via _on_file_change
            handler = FileChangeHandler(lambda c: fw._on_file_change(c), set())
            handler.on_created(_make_event("created", "/tmp/test.py"))
            handler.on_modified(_make_event("modified", "/tmp/test2.py"))

            # Wait for batch processing
            time.sleep(0.4)

            fw.stop()
            assert len(changes) == 2
