# CodeLens Build Script
# Builds the Windows distribution package
# Usage: .\build.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$DistDir = Join-Path $Root "dist"
$BuildDir = Join-Path $Root "build"
$OutputDir = Join-Path $DistDir "CodeLens"
$LlamaSrc = Join-Path $Root "llama.cpp"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  CodeLens Build Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check prerequisites
Write-Host "[1/8] Checking prerequisites..." -ForegroundColor Yellow

if (-not (Test-Path $VenvPython)) {
    Write-Host "ERROR: Python venv not found at $VenvPython" -ForegroundColor Red
    Write-Host "Run: python -m venv .venv" -ForegroundColor Gray
    exit 1
}

# Step 2: Install PyInstaller
Write-Host "[2/8] Installing PyInstaller..." -ForegroundColor Yellow
& $VenvPython -m pip install pyinstaller --quiet 2>&1 | Out-Null
Write-Host "  PyInstaller installed" -ForegroundColor Gray

# Step 3: Clean previous build
Write-Host "[3/8] Cleaning previous build..." -ForegroundColor Yellow
if (Test-Path $BuildDir) { Remove-Item $BuildDir -Recurse -Force }
if (Test-Path $DistDir) { Remove-Item $DistDir -Recurse -Force }
New-Item -ItemType Directory -Path $DistDir -Force | Out-Null

# Step 4: Build launcher.exe
Write-Host "[4/8] Building launcher.exe..." -ForegroundColor Yellow
& $VenvPython -m PyInstaller `
    --onefile `
    --name "launcher" `
    --distpath $DistDir `
    --workpath $BuildDir `
    --specpath $Root `
    --clean `
    --noconfirm `
    (Join-Path $Root "launcher.py")

if (-not (Test-Path (Join-Path $DistDir "launcher.exe"))) {
    Write-Host "ERROR: Failed to build launcher.exe" -ForegroundColor Red
    exit 1
}
Write-Host "  launcher.exe built" -ForegroundColor Gray

# Step 5: Build web app
Write-Host "[5/8] Building web app (app.exe)..." -ForegroundColor Yellow
& $VenvPython -m PyInstaller `
    (Join-Path $Root "app.spec") `
    --distpath $OutputDir `
    --workpath $BuildDir `
    --clean `
    --noconfirm

if (-not (Test-Path (Join-Path $OutputDir "app\app.exe"))) {
    Write-Host "ERROR: Failed to build app.exe" -ForegroundColor Red
    exit 1
}
Write-Host "  app.exe built" -ForegroundColor Gray

# Step 6: Copy llama-server binaries
Write-Host "[6/8] Copying llama-server binaries..." -ForegroundColor Yellow
$LlamaDst = Join-Path $OutputDir "llama-server"
if (-not (Test-Path $LlamaDst)) {
    New-Item -ItemType Directory -Path $LlamaDst -Force | Out-Null
}

# Copy essential files
$EssentialFiles = @(
    "llama-server.exe",
    "llama.dll",
    "ggml.dll",
    "ggml-base.dll",
    "ggml-cuda.dll",
    "ggml-rpc.dll",
    "mtmd.dll",
    "libomp140.x86_64.dll"
)

foreach ($file in $EssentialFiles) {
    $src = Join-Path $LlamaSrc $file
    if (Test-Path $src) {
        Copy-Item $src -Destination $LlamaDst -Force
        Write-Host "  Copied: $file" -ForegroundColor Gray
    } else {
        Write-Host "  WARNING: $file not found" -ForegroundColor DarkYellow
    }
}

# Copy CPU variant DLLs
Get-ChildItem -Path $LlamaSrc -Filter "ggml-cpu-*.dll" | ForEach-Object {
    Copy-Item $_.FullName -Destination $LlamaDst -Force
}

# Step 7: Create config.ini and models directory
Write-Host "[7/8] Creating config and models directory..." -ForegroundColor Yellow
Copy-Item (Join-Path $Root "config.ini") -Destination $OutputDir -Force
New-Item -ItemType Directory -Path (Join-Path $OutputDir "models") -Force | Out-Null
Write-Host "  config.ini copied" -ForegroundColor Gray
Write-Host "  models/ directory created" -ForegroundColor Gray

# Step 8: Create zip archive
Write-Host "[8/8] Creating zip archive..." -ForegroundColor Yellow
$ZipPath = Join-Path $DistDir "CodeLens-win64.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path $OutputDir -DestinationPath $ZipPath -Force
$ZipSize = [math]::Round((Get-Item $ZipPath).Length / 1MB, 1)
Write-Host "  Created: $ZipPath ($ZipSize MB)" -ForegroundColor Gray

# Summary
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Build Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Distribution folder: $OutputDir" -ForegroundColor Cyan
Write-Host "Zip archive: $ZipPath" -ForegroundColor Cyan
Write-Host ""
Write-Host "To use:" -ForegroundColor Yellow
Write-Host "  1. Copy the CodeLens folder to your target machine" -ForegroundColor Gray
Write-Host "  2. Place your .gguf model in the models/ folder" -ForegroundColor Gray
Write-Host "  3. Edit config.ini if needed" -ForegroundColor Gray
Write-Host "  4. Run launcher.exe" -ForegroundColor Gray
Write-Host ""
