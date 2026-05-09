# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-05-09

### Added
- **Agent Mode** 🤖 - New autonomous AI coding assistant mode
  - ReAct (Reasoning + Acting) execution loop
  - Tool calling system with 8 built-in tools
  - Diff-based editing (edit_file, apply_diff)
  - Execution visualization with timeline
  - Task pause/resume/stop controls
  - Undo support for edits

### Changed
- Modularized project structure:
  - `config.py` - Configuration management
  - `logger.py` - Logging utilities
  - `exceptions.py` - Custom exception classes
  - `settings.py` - Environment variable loader
  - `models/` - Data models
  - `services/` - Business logic (search, file watcher, context manager)
  - `routes/` - API route handlers
  - `core/agent.py` - Agent core framework
  - `core/tools/` - Tool implementations

### Added Tools
- `read_file` - Read file content with line numbers
- `write_file` - Create/overwrite files
- `edit_file` - Diff-style editing with old_str/new_str
- `search_files` - Regex search in files
- `list_directory` - Directory listing with tree
- `run_command` - Shell command execution
- `git_operation` - Git operations (status, diff, log, add, commit)
- `apply_diff` - Apply unified diff patches
- `undo_edit` - Undo recent edits

### Added Services
- `services/search.py` - BM25 + ONNX search
- `services/file_watcher.py` - File change monitoring
- `services/context_manager.py` - Smart context allocation

### Added Tests
- `tests/test_basic.py` - Basic functionality tests
- `tests/test_tools.py` - Tool execution tests
- `tests/test_agent.py` - Agent core tests
- `tests/test_diff.py` - Diff utility tests

### API Endpoints
- `POST /api/agent/start` - Start Agent task
- `GET /api/agent/status/{task_id}` - Get task status
- `POST /api/agent/action` - User action (confirm/reject)
- `POST /api/agent/stop/{task_id}` - Stop task
- `GET /api/agent/tools` - List available tools
- `GET /api/agent/history` - Get edit history
- `POST /api/agent/undo` - Undo edits
- `POST /api/agent/execute/{task_id}` - Execute with streaming

## [0.2.0] - Previous

### Added
- Dark theme support
- Model parameter settings (max_tokens, temperature, context_limit)
- Context usage display

### Changed
- Layout optimizations
- Terminal integration (xterm.js)

## [0.1.0] - Initial Release

### Added
- BM25 + ONNX semantic search
- Ask / Plan / Craft modes
- Streaming output
- File tree browser
- CodeMirror editor
- AI code completion