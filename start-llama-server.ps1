$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Server = Join-Path $Root "llama.cpp\llama-server.exe"
$Model = Join-Path $Root "Qwen3.5-9B.Q4_K_M.gguf"

if (-not (Test-Path $Server)) {
    throw "llama-server.exe not found: $Server"
}

if (-not (Test-Path $Model)) {
    throw "Model not found: $Model"
}

& $Server `
    -m $Model `
    -ngl 999 `
    -c 32768 `
    --host 127.0.0.1 `
    --port 8080 `
    --jinja `
    --reasoning-format none `
    --cache-type-k q4_0 `
    --cache-reuse 3000
