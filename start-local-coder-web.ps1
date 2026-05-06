$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "Python not found: $Python"
}

& $Python -m uvicorn app:app --app-dir (Join-Path $Root "local-coder-web") --host 127.0.0.1 --port 8765 --reload
