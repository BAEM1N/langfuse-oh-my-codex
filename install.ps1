# ─────────────────────────────────────────────
# langfuse-oh-my-codex installer (Windows)
# ─────────────────────────────────────────────
#Requires -Version 5.1

$ErrorActionPreference = "Stop"

$HookName     = "langfuse_hook.py"
$OmxDir       = Join-Path $env:USERPROFILE ".omx"
$HooksDir     = Join-Path $OmxDir "hooks"
$EnvFile      = Join-Path $OmxDir ".env"
$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path

function Write-Step  ($msg) { Write-Host "[STEP] $msg" -ForegroundColor Cyan }
function Write-Info  ($msg) { Write-Host "[INFO] $msg" -ForegroundColor Green }
function Write-Warn  ($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err   ($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "============================================"
Write-Host "   langfuse-oh-my-codex installer"
Write-Host "============================================"
Write-Host ""

# ── 1. Check Python ──────────────────────────
Write-Step "Checking Python installation..."
$Python = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $Python = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $Python = "python3"
} else {
    Write-Err "Python not found. Please install Python 3.8+ first."
    exit 1
}

$PyVersion = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$PyMajor   = & $Python -c "import sys; print(sys.version_info.major)"
$PyMinor   = & $Python -c "import sys; print(sys.version_info.minor)"

if ([int]$PyMajor -lt 3 -or ([int]$PyMajor -eq 3 -and [int]$PyMinor -lt 8)) {
    Write-Err "Python 3.8+ required, found $PyVersion"
    exit 1
}

Write-Info "Found $Python ($PyVersion)"

# ── 2. Install langfuse SDK ──────────────────
Write-Step "Installing langfuse Python SDK..."
& $Python -m pip install --quiet --upgrade langfuse
Write-Info "langfuse SDK installed."

# ── 3. Copy hook script ─────────────────────
Write-Step "Copying hook script..."
if (-not (Test-Path $HooksDir)) { New-Item -ItemType Directory -Path $HooksDir -Force | Out-Null }
Copy-Item (Join-Path $ScriptDir $HookName) -Destination (Join-Path $HooksDir $HookName) -Force
Write-Info "Hook script installed: $HooksDir\$HookName"

# ── 4. Clean previous state (optional) ──────
$StateFile = Join-Path $HooksDir "langfuse_state.json"
if (Test-Path $StateFile) {
    Write-Host ""
    $ResetState = Read-Host "  Previous state file found. Reset trace offsets? [y/N]"
    if ($ResetState -eq "y" -or $ResetState -eq "Y") {
        Remove-Item $StateFile -Force
        Write-Info "State file reset."
    }
}

# ── 5. Collect Langfuse credentials ─────────
Write-Host ""
Write-Step "Configuring Langfuse credentials..."
Write-Host "  Get your keys from https://cloud.langfuse.com (or your self-hosted instance)."
Write-Host ""

$LfPublicKey = Read-Host "  Langfuse Public Key "
$LfSecretKeySecure = Read-Host "  Langfuse Secret Key " -AsSecureString
$LfSecretKey = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($LfSecretKeySecure)
)

$LfBaseUrl = Read-Host "  Langfuse Base URL   [https://cloud.langfuse.com]"
if ([string]::IsNullOrWhiteSpace($LfBaseUrl)) { $LfBaseUrl = "https://cloud.langfuse.com" }

$LfUserId = Read-Host "  User ID (trace attribution) [omx-user]"
if ([string]::IsNullOrWhiteSpace($LfUserId)) { $LfUserId = "omx-user" }

if ([string]::IsNullOrWhiteSpace($LfPublicKey) -or [string]::IsNullOrWhiteSpace($LfSecretKey)) {
    Write-Err "Public Key and Secret Key are required."
    exit 1
}

# ── 6. Write credentials to .env ─────────────
Write-Step "Writing credentials to $EnvFile..."
if (-not (Test-Path $OmxDir)) { New-Item -ItemType Directory -Path $OmxDir -Force | Out-Null }

$EnvContent = @"
# Langfuse credentials for langfuse-oh-my-codex
# Environment variables take priority over .env values.

TRACE_TO_LANGFUSE=true
LANGFUSE_PUBLIC_KEY=$LfPublicKey
LANGFUSE_SECRET_KEY=$LfSecretKey
LANGFUSE_BASE_URL=$LfBaseUrl
LANGFUSE_USER_ID=$LfUserId
"@

Set-Content -Path $EnvFile -Value $EnvContent -Encoding UTF8
Write-Info "Credentials written to $EnvFile"

# ── 7. Verify ────────────────────────────────
Write-Step "Verifying installation..."
$ImportCheck = & $Python -c "import langfuse; print('ok')" 2>&1
if ($ImportCheck -eq "ok") {
    Write-Info "langfuse SDK: OK"
} else {
    Write-Warn "langfuse SDK import failed. Check your Python environment."
}

if (Test-Path (Join-Path $HooksDir $HookName)) {
    Write-Info "Hook script: OK"
} else {
    Write-Warn "Hook script not found."
}

# ── Done ─────────────────────────────────────
Write-Host ""
Write-Host "============================================"
Write-Host "   Installation complete!"
Write-Host "============================================"
Write-Host ""
Write-Info "OMX will now send traces to Langfuse on turn-complete events."
Write-Info "Configure your OMX hook plugin to call: $Python ~/.omx/hooks/$HookName"
Write-Host ""
Write-Host "  Dashboard : $LfBaseUrl"
Write-Host "  Logs      : ~/.omx/hooks/langfuse_hook.log"
Write-Host "  Disable   : set TRACE_TO_LANGFUSE=false in ~/.omx/.env"
Write-Host ""
