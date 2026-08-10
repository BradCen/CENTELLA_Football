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
    if (Test-Path $candidate) { $Python = $candidate; break }
}
if (-not $Python) {
    $Python = (Get-Command python).Source
}

Set-Location $ProjectRoot
Write-Host "CENTELLA Football shell: $Python" -ForegroundColor Cyan

& $Python -c "import pygame" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Instalando pygame para el shell..." -ForegroundColor Yellow
    & $Python -m pip install "pygame==2.6.1"
    if ($LASTEXITCODE -ne 0) { throw "No se pudo instalar pygame." }
}

& $Python -m centella
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nEl shell terminó con error $LASTEXITCODE." -ForegroundColor Red
    exit $LASTEXITCODE
}
