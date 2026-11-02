# AI Edit Stack - one-time setup (Windows PowerShell 5.1+)
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File E:\AI-Edit_stack\setup\setup.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
Write-Host "== AI Edit Stack setup in $Root ==" -ForegroundColor Cyan

function Need($cmd, $hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Host "MISSING: $cmd  ->  $hint" -ForegroundColor Yellow
        return $false
    }
    Write-Host "found: $cmd" -ForegroundColor Green
    return $true
}

$ok = $true
$ok = (Need "ffmpeg" "winget install Gyan.FFmpeg") -and $ok
$ok = (Need "node" "winget install OpenJS.NodeJS (v22+)") -and $ok
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv (Python package manager)..." -ForegroundColor Cyan
    powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
}
if (-not $ok) { Write-Host "Install the missing tools above, open a new terminal, and re-run." -ForegroundColor Red; exit 1 }

# Python 3.12 venv + dependencies (GPU extras when an NVIDIA GPU is present)
$gpu = [bool](Get-Command nvidia-smi -ErrorAction SilentlyContinue)
Write-Host "Creating Python 3.12 environment (gpu=$gpu)..." -ForegroundColor Cyan
if ($gpu) { uv sync --extra gpu } else { uv sync }
if ($LASTEXITCODE -ne 0) { Write-Host "uv sync failed" -ForegroundColor Red; exit 1 }

# HyperFrames CLI (pinned; npx caches it)
$pkg = (Get-Content "$Root\config\stack.json" -Raw | ConvertFrom-Json).hyperframes.npx_package
Write-Host "Warming HyperFrames CLI $pkg ..." -ForegroundColor Cyan
npx --yes $pkg --version

# Render frame cache off the system drive
$fc = (Get-Content "$Root\config\stack.json" -Raw | ConvertFrom-Json).paths.hf_frames_cache
if ($fc) { New-Item -ItemType Directory -Force $fc | Out-Null }

# Pre-download the Whisper model so the first analysis does not stall
Write-Host "Downloading Whisper model (one time, ~1.5 GB for 'medium')..." -ForegroundColor Cyan
uv run python -c "import json;from faster_whisper.utils import download_model;c=json.load(open('config/stack.json'))['whisper'];download_model(c['model']);download_model(c.get('model_cpu') or c['model']);print('whisper models ready')"

uv run aes doctor
Write-Host ""
Write-Host "Setup finished. Next: read ONBOARDING.md (step 3 onward)." -ForegroundColor Cyan
