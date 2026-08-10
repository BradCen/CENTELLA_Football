$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "CENTELLA Football - Install / Repair"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$WorkspaceRoot = Split-Path -Parent $ProjectRoot
$ToolchainRoot = Join-Path $WorkspaceRoot "TOOLCHAIN"
$Python = Join-Path $ToolchainRoot "Python310\python.exe"
$Vcpkg = Join-Path $ToolchainRoot "vcpkg"
$Cache = Join-Path $ToolchainRoot "vcpkg_cache"

Write-Host ""
Write-Host "CENTELLA FOOTBALL - BETA RUNTIME" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host "Toolchain: $ToolchainRoot"

if (-not (Test-Path $Python)) {
    Write-Host "No encontré $Python" -ForegroundColor Yellow
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $candidate = & py -3.10 -c "import sys;print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and (Test-Path $candidate)) { $Python = $candidate.Trim() }
    }
}
if (-not (Test-Path $Python)) {
    throw "Necesito Python 3.10 x64. Instala Python 3.10 o restaura TOOLCHAIN\Python310."
}

Write-Host "Python: $Python" -ForegroundColor Green
& $Python --version

if (-not (Test-Path $Vcpkg)) {
    $fallback = "F:\vcpkg"
    if (Test-Path $fallback) { $Vcpkg = $fallback }
}
if (-not (Test-Path (Join-Path $Vcpkg "vcpkg.exe"))) {
    throw "No encontré vcpkg. Se esperaba TOOLCHAIN\vcpkg o F:\vcpkg."
}

New-Item -ItemType Directory -Force $Cache | Out-Null
$env:VCPKG_ROOT = $Vcpkg
$env:VCPKG_DEFAULT_BINARY_CACHE = $Cache
$env:VCPKG_DISABLE_METRICS = "1"
$env:CMAKE_POLICY_VERSION_MINIMUM = "3.10"
$env:GENERATOR_PLATFORM = "x64"
$env:PY_VERSION = "3.10"
$env:BUILD_CONFIGURATION = "Release"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
Set-Location $ProjectRoot

Write-Host "`n[1/4] Preparando dependencias Python..." -ForegroundColor Cyan
& $Python -m pip install "pip==23.2.1" "setuptools==65.5.0" "wheel==0.38.4"
& $Python -m pip install "pygame==2.6.1" absl-py psutil "numpy<2" opencv-python six "gym==0.21.0"

function Invoke-GrfBuild {
    Write-Host "`n[2/4] Compilando Gameplay Football / GRF..." -ForegroundColor Cyan
    & $Python -m pip install -e . --no-build-isolation -v
    return $LASTEXITCODE
}

$firstExit = Invoke-GrfBuild
if ($firstExit -ne 0) {
    Write-Host "Primer intento falló. Aplicando compatibilidad Boost Atomic conocida..." -ForegroundColor Yellow
    $installedRoot = Join-Path $ProjectRoot "third_party\gfootball_engine\build_win\vcpkg_installed\x64-windows"
    $aliasesCreated = 0
    $aliasPairs = @(
        @{ Dir = (Join-Path $installedRoot "debug\lib"); Target = "boost_atomic-vc140-mt-gd.lib" },
        @{ Dir = (Join-Path $installedRoot "lib");       Target = "boost_atomic-vc140-mt.lib" }
    )
    foreach ($pair in $aliasPairs) {
        $dir = $pair.Dir
        $target = Join-Path $dir $pair.Target
        if (-not (Test-Path $dir) -or (Test-Path $target)) { continue }
        $source = Get-ChildItem $dir -Filter "boost_atomic*.lib" -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -ne $pair.Target } | Sort-Object Name | Select-Object -First 1
        if ($source) {
            Copy-Item $source.FullName $target -Force
            Write-Host "Alias: $($source.Name) -> $($pair.Target)"
            $aliasesCreated++
        }
    }
    if ($aliasesCreated -gt 0) { $secondExit = Invoke-GrfBuild } else { $secondExit = $firstExit }
    if ($secondExit -ne 0) {
        Write-Host "`nLa compilación nativa todavía falló. Copia desde '[2/4]' hasta el final y envíalo en el chat." -ForegroundColor Red
        exit $secondExit
    }
}

Write-Host "`n[3/4] Verificando imports..." -ForegroundColor Cyan
& $Python -c "import absl, pygame, numpy, cv2, psutil, gfootball_engine; print('gfootball_engine:', gfootball_engine.__file__); print('RUNTIME OK')"
if ($LASTEXITCODE -ne 0) { throw "El motor compiló pero el import nativo falló." }

Write-Host "`n[4/4] Listo." -ForegroundColor Green
Write-Host "Ejecuta la beta con:" -ForegroundColor White
Write-Host "  .\scripts\RUN_BETA.ps1" -ForegroundColor Cyan
