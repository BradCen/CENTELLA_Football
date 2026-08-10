param(
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$WorkspaceRoot = Split-Path -Parent $ProjectRoot
$ToolchainRoot = Join-Path $WorkspaceRoot "TOOLCHAIN"

$candidates = @(
    (Join-Path $ToolchainRoot "Python310\python.exe"),
    (Join-Path $ToolchainRoot "python310\python.exe"),
    (Join-Path $ToolchainRoot "Python\python.exe")
)

$Python = $null
foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
        $Python = $candidate
        break
    }
}

if (-not $Python) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "No encontré Python. Restaura TOOLCHAIN\Python310 antes de continuar."
    }
    $Python = $pythonCommand.Source
}

Set-Location $ProjectRoot
$env:PYGAME_HIDE_SUPPORT_PROMPT = "1"
Write-Host "CENTELLA Football: $Python" -ForegroundColor Cyan

function Test-PythonCode {
    param([Parameter(Mandatory = $true)][string]$Code)

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $Python -c $Code *> $null
        $exitCode = [int]$LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
    return ($exitCode -eq 0)
}

function Invoke-PythonCommand {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $Python @Arguments 2>&1 | ForEach-Object { Write-Host $_ }
        $exitCode = [int]$LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
    return [int]$exitCode
}

if (-not (Test-PythonCode "import pip")) {
    Write-Host "Preparando pip para CENTELLA Football..." -ForegroundColor Yellow
    $ensurePipExit = [int](Invoke-PythonCommand @("-m", "ensurepip", "--upgrade"))
    if ($ensurePipExit -ne 0) {
        throw "Python existe, pero no pude preparar pip (exit $ensurePipExit)."
    }
}

# Pygame remains installed only because the recovery frontend and parts of the
# GRF runtime still import it. It is no longer the public menu renderer.
if (-not (Test-PythonCode "import pygame; assert pygame.version.ver.startswith('2.6.')")) {
    Write-Host "Preparando dependencia de compatibilidad pygame 2.6.1..." -ForegroundColor Yellow
    $pygameInstallExit = [int](Invoke-PythonCommand @("-m", "pip", "install", "pygame==2.6.1"))
    if ($pygameInstallExit -ne 0) {
        throw "No se pudo instalar pygame (exit $pygameInstallExit)."
    }
}

# CENTELLA now renders its shipping menu with HTML/CSS/JS inside a native
# Windows WebView. pywebview uses Edge WebView2 when available.
if (-not (Test-PythonCode "import webview; assert hasattr(webview, 'create_window')")) {
    Write-Host "Preparando interfaz nativa WebView2 de CENTELLA..." -ForegroundColor Yellow
    $webviewInstallExit = [int](Invoke-PythonCommand @("-m", "pip", "install", "pywebview>=5,<7"))
    if ($webviewInstallExit -ne 0) {
        Write-Host "No se pudo preparar pywebview; se conservará el frontend de recuperación." -ForegroundColor Yellow
    }
}

if (-not (Test-PythonCode "import centella.web_frontend; import centella.release_frontend; import centella.runtime")) {
    throw "CENTELLA Football no puede importar sus frontends/runtime. Revisa el traceback con: `"$Python`" -c `"import centella.web_frontend; import centella.runtime`""
}

$pythonVersion = & $Python -c "import platform,sys; print(sys.version.split()[0] + ' ' + platform.architecture()[0])"
Write-Host "CENTELLA Python OK: $pythonVersion" -ForegroundColor Green

$EngineReady = Test-PythonCode "import sys; from centella.runtime import runtime_summary; sys.exit(0 if runtime_summary().get('ready') else 7)"
if ($EngineReady) {
    Write-Host "CENTELLA ENGINE: READY" -ForegroundColor Green
}
else {
    Write-Host "CENTELLA ENGINE: NOT READY (gfootball_engine nativo no está disponible)" -ForegroundColor Yellow
}

if ($CheckOnly) {
    Write-Host "CENTELLA LAUNCHER CHECK OK" -ForegroundColor Green
    if (-not $EngineReady) {
        Write-Host "NOTA: el menú puede abrir, pero JUGAR permanecerá bloqueado hasta que el motor nativo compile correctamente." -ForegroundColor Yellow
    }
    exit 0
}

$runExit = [int](Invoke-PythonCommand @("-m", "centella"))
if ($runExit -ne 0) {
    Write-Host "`nCENTELLA Football terminó con error $runExit." -ForegroundColor Red
    exit $runExit
}
