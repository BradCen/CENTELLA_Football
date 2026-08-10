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
        throw "No encontré Python. Ejecuta scripts\INSTALL_BETA.ps1 o restaura TOOLCHAIN\Python310."
    }
    $Python = $pythonCommand.Source
}

Set-Location $ProjectRoot
$env:PYGAME_HIDE_SUPPORT_PROMPT = "1"
Write-Host "CENTELLA Football shell: $Python" -ForegroundColor Cyan

# Windows PowerShell 5.1 turns redirected stderr from native programs into
# ErrorRecord objects. With ErrorActionPreference=Stop, a harmless probe such as
# `python -c 'import pygame'` used to terminate the launcher before we could read
# LASTEXITCODE and install the missing package. Keep probes isolated from that
# PowerShell behaviour and decide exclusively from the native exit code.
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
        # Route the native process output to the host instead of the PowerShell
        # success pipeline. Otherwise assigning the function result also captures
        # pip's text and turns an exit code such as 0 into an array/string.
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
    Write-Host "Preparando pip para el shell..." -ForegroundColor Yellow
    $ensurePipExit = [int](Invoke-PythonCommand @("-m", "ensurepip", "--upgrade"))
    if ($ensurePipExit -ne 0) {
        throw "Python existe, pero no pude preparar pip (exit $ensurePipExit)."
    }
}

if (-not (Test-PythonCode "import pygame; assert pygame.version.ver.startswith('2.6.')")) {
    Write-Host "pygame no está disponible en este Python. Instalando pygame 2.6.1 para el shell..." -ForegroundColor Yellow
    $pygameInstallExit = [int](Invoke-PythonCommand @("-m", "pip", "install", "pygame==2.6.1"))
    if ($pygameInstallExit -ne 0) {
        throw "No se pudo instalar pygame (exit $pygameInstallExit)."
    }
}

if (-not (Test-PythonCode "import pygame; import centella.product_frontend; import centella.runtime")) {
    throw "pygame quedó instalado, pero el shell CENTELLA no puede importarse. Revisa el traceback con: `"$Python`" -c `"import centella.product_frontend`""
}

$pythonVersion = & $Python -c "import platform,sys; print(sys.version.split()[0] + ' ' + platform.architecture()[0])"
Write-Host "Shell Python OK: $pythonVersion" -ForegroundColor Green

if ($CheckOnly) {
    Write-Host "CENTELLA LAUNCHER CHECK OK" -ForegroundColor Green
    exit 0
}

$runExit = [int](Invoke-PythonCommand @("-m", "centella"))
if ($runExit -ne 0) {
    Write-Host "`nEl shell terminó con error $runExit." -ForegroundColor Red
    exit $runExit
}
