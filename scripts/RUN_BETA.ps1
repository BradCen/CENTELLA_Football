$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$WorkspaceRoot = Split-Path -Parent $ProjectRoot
$Python = Join-Path $WorkspaceRoot "TOOLCHAIN\Python310\python.exe"
if (-not (Test-Path $Python)) {
    $Python = (Get-Command python).Source
}
Set-Location $ProjectRoot
& $Python -c "import pygame" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $Python -m pip install pygame
}
& $Python -m centella
