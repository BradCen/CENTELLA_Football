$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "CENTELLA Football - Install / Repair"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$WorkspaceRoot = Split-Path -Parent $ProjectRoot
$ToolchainRoot = Join-Path $WorkspaceRoot "TOOLCHAIN"
$Cache = Join-Path $ToolchainRoot "vcpkg_cache"

function Find-Python310 {
    $candidates = @(
        (Join-Path $ToolchainRoot "Python310\python.exe"),
        (Join-Path $ToolchainRoot "python310\python.exe"),
        (Join-Path $ToolchainRoot "Python\python.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            $version = & $candidate -c "import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $version.Trim() -eq "3.10") { return $candidate }
        }
    }
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $candidate = & py -3.10 -c "import sys;print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $candidate -and (Test-Path $candidate.Trim())) {
            return $candidate.Trim()
        }
    }
    return $null
}

function Find-Or-PrepareVcpkg {
    $candidates = @(
        (Join-Path $ToolchainRoot "vcpkg"),
        (Join-Path $WorkspaceRoot "vcpkg"),
        "F:\vcpkg",
        "C:\vcpkg"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path (Join-Path $candidate "vcpkg.exe")) { return $candidate }
    }

    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) { throw "No encontré vcpkg ni Git para descargarlo." }
    $target = Join-Path $ToolchainRoot "vcpkg"
    New-Item -ItemType Directory -Force $ToolchainRoot | Out-Null
    if (Test-Path $target) { Remove-Item $target -Recurse -Force }
    Write-Host "No había vcpkg. Descargando una copia aislada en TOOLCHAIN..." -ForegroundColor Yellow
    git clone https://github.com/microsoft/vcpkg.git $target
    if ($LASTEXITCODE -ne 0) { throw "No se pudo clonar vcpkg." }
    & (Join-Path $target "bootstrap-vcpkg.bat") -disableMetrics
    if ($LASTEXITCODE -ne 0) { throw "No se pudo preparar vcpkg." }
    return $target
}

Write-Host ""
Write-Host "CENTELLA FOOTBALL - BETA RUNTIME" -ForegroundColor Cyan
Write-Host "Project:   $ProjectRoot"
Write-Host "Workspace: $WorkspaceRoot"
Write-Host "Toolchain: $ToolchainRoot"

$Python = Find-Python310
if (-not $Python) {
    Write-Host "" -ForegroundColor Red
    Write-Host "FALTA PYTHON 3.10 x64" -ForegroundColor Red
    Write-Host "El motor nativo de esta base está fijado a Python 3.10 por su manifiesto vcpkg." -ForegroundColor Yellow
    Write-Host "Instala Python 3.10 x64 o restaura TOOLCHAIN\Python310 y vuelve a ejecutar este script."
    exit 10
}
Write-Host "Python: $Python" -ForegroundColor Green
& $Python --version

$Vcpkg = Find-Or-PrepareVcpkg
Write-Host "vcpkg: $Vcpkg" -ForegroundColor Green

$cmake = Get-Command cmake -ErrorAction SilentlyContinue
if (-not $cmake) { throw "CMake no está disponible en PATH. Abre Developer PowerShell de Visual Studio." }

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
if ($LASTEXITCODE -ne 0) { throw "No se pudieron preparar pip/setuptools/wheel." }
& $Python -m pip install "pygame==2.6.1" absl-py psutil "numpy<2" opencv-python six "gym==0.21.0"
if ($LASTEXITCODE -ne 0) { throw "Falló la instalación de dependencias Python." }

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
        Write-Host "`nLa compilación nativa todavía falló." -ForegroundColor Red
        Write-Host "Copia desde '[2/4]' hasta el final y envíalo en el chat." -ForegroundColor Yellow
        exit $secondExit
    }
}

Write-Host "`n[3/4] Verificando imports y arquitectura..." -ForegroundColor Cyan
& $Python -c "import struct,absl,pygame,numpy,cv2,psutil,gfootball_engine; assert struct.calcsize('P')*8==64; print('gfootball_engine:', gfootball_engine.__file__); print('RUNTIME OK - 64 bit')"
if ($LASTEXITCODE -ne 0) { throw "El motor compiló pero el import nativo falló." }

Write-Host "`n[4/4] Listo." -ForegroundColor Green
Write-Host "Ya puedes cerrar esta ventana y ejecutar:" -ForegroundColor White
Write-Host "  .\scripts\RUN_BETA.ps1" -ForegroundColor Cyan
Write-Host "o hacer doble clic en RUN_CENTELLA_BETA.bat" -ForegroundColor Cyan
