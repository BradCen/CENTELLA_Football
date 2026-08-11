$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "CENTELLA Football - Install / Repair"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$WorkspaceRoot = Split-Path -Parent $ProjectRoot
$ToolchainRoot = Join-Path $WorkspaceRoot "TOOLCHAIN"
$Cache = Join-Path $ToolchainRoot "vcpkg_cache"
$CentellaVcpkg = Join-Path $ToolchainRoot "vcpkg-centella"
$PkgConfigRoot = Join-Path $ToolchainRoot "pkgconfiglite"
$VcpkgBaseline = "b18b17865cfb6bd24620a00f30691be6775abb96"

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

function Test-ZipFile([string]$Path) {
    if (-not (Test-Path $Path)) { return $false }
    $item = Get-Item $Path -ErrorAction SilentlyContinue
    if (-not $item -or $item.Length -lt 10000) { return $false }
    try {
        $stream = [System.IO.File]::OpenRead($Path)
        try {
            $b1 = $stream.ReadByte()
            $b2 = $stream.ReadByte()
            return ($b1 -eq 0x50 -and $b2 -eq 0x4B)
        } finally {
            $stream.Dispose()
        }
    } catch {
        return $false
    }
}

function Ensure-PkgConfig {
    $existing = Get-Command pkg-config.exe -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "pkg-config existente: $($existing.Source)" -ForegroundColor Green
        return $existing.Source
    }

    New-Item -ItemType Directory -Force $PkgConfigRoot | Out-Null
    $localExe = Get-ChildItem $PkgConfigRoot -Filter "pkg-config.exe" -Recurse -File -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($localExe) { return $localExe.FullName }

    Write-Host "Preparando pkg-config compatible para el vcpkg histórico..." -ForegroundColor Yellow

    # Prefer the same Chocolatey package used by GitHub Actions when Chocolatey
    # already exists on the machine. This avoids SourceForge redirect/download
    # pages being saved as if they were ZIP files.
    $choco = Get-Command choco.exe -ErrorAction SilentlyContinue
    if ($choco) {
        Write-Host "Intentando pkgconfiglite mediante Chocolatey..." -ForegroundColor DarkGray
        & $choco.Source install pkgconfiglite -y --no-progress
        if ($LASTEXITCODE -eq 0) {
            $chocoBin = Join-Path $env:ChocolateyInstall "bin"
            if (Test-Path $chocoBin) { $env:PATH = "$chocoBin;$env:PATH" }
            $installed = Get-Command pkg-config.exe -ErrorAction SilentlyContinue
            if ($installed) {
                Write-Host "pkg-config instalado: $($installed.Source)" -ForegroundColor Green
                return $installed.Source
            }
        }
        Write-Host "Chocolatey no dejó pkg-config disponible; usando descarga directa verificada..." -ForegroundColor Yellow
    }

    $zip = Join-Path $ToolchainRoot "pkg-config-lite-0.28-1.zip"
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
    if (Test-Path $PkgConfigRoot) { Remove-Item $PkgConfigRoot -Recurse -Force }
    New-Item -ItemType Directory -Force $PkgConfigRoot | Out-Null

    $url = "https://sourceforge.net/projects/pkgconfiglite/files/0.28-1/pkg-config-lite-0.28-1_bin-win32.zip/download"
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        & $curl.Source -L --fail --retry 3 --retry-delay 2 --connect-timeout 20 -A "Mozilla/5.0" -o $zip $url
        if ($LASTEXITCODE -ne 0) { Remove-Item $zip -Force -ErrorAction SilentlyContinue }
    }

    if (-not (Test-ZipFile $zip)) {
        Remove-Item $zip -Force -ErrorAction SilentlyContinue
        Write-Host "curl no obtuvo un ZIP válido; reintentando con PowerShell..." -ForegroundColor Yellow
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing -MaximumRedirection 10 -Headers @{ "User-Agent" = "Mozilla/5.0" }
    }

    if (-not (Test-ZipFile $zip)) {
        Remove-Item $zip -Force -ErrorAction SilentlyContinue
        throw "La descarga de pkg-config no produjo un ZIP válido. No se intentará descomprimir HTML o un archivo incompleto."
    }

    try {
        Expand-Archive -Path $zip -DestinationPath $PkgConfigRoot -Force
    } catch {
        Remove-Item $zip -Force -ErrorAction SilentlyContinue
        throw "pkg-config se descargó pero el ZIP no pudo abrirse: $($_.Exception.Message)"
    }
    Remove-Item $zip -Force -ErrorAction SilentlyContinue

    $localExe = Get-ChildItem $PkgConfigRoot -Filter "pkg-config.exe" -Recurse -File -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $localExe) { throw "pkg-config.exe no pudo prepararse." }
    Write-Host "pkg-config local: $($localExe.FullName)" -ForegroundColor Green
    return $localExe.FullName
}

function Patch-LegacyVcpkgPkgConfig([string]$VcpkgRoot, [string]$PkgConfigExe) {
    $fixup = Join-Path $VcpkgRoot "scripts\cmake\vcpkg_fixup_pkgconfig.cmake"
    if (-not (Test-Path $fixup)) { throw "No existe vcpkg_fixup_pkgconfig.cmake en el toolchain histórico." }
    $text = Get-Content $fixup -Raw
    $old = "vcpkg_find_acquire_program(PKGCONFIG)"
    $escaped = $PkgConfigExe.Replace("\", "/")
    $new = "set(PKGCONFIG `"$escaped`")"
    if ($text.Contains($old)) {
        $text = $text.Replace($old, $new)
        Set-Content -Path $fixup -Value $text -Encoding utf8
    } elseif (-not $text.Contains($new)) {
        throw "No se encontró el hook esperado de pkg-config en vcpkg histórico."
    }
    Write-Host "vcpkg histórico usará pkg-config: $PkgConfigExe" -ForegroundColor Green
}

function Prepare-CentellaVcpkg {
    $git = Get-Command git -ErrorAction SilentlyContinue
    if (-not $git) { throw "Git es necesario para preparar el toolchain reproducible de CENTELLA." }

    New-Item -ItemType Directory -Force $ToolchainRoot | Out-Null
    $needClone = -not (Test-Path (Join-Path $CentellaVcpkg ".git"))
    if ($needClone) {
        if (Test-Path $CentellaVcpkg) { Remove-Item $CentellaVcpkg -Recurse -Force }
        Write-Host "Preparando vcpkg aislado para CENTELLA..." -ForegroundColor Yellow
        git clone https://github.com/microsoft/vcpkg.git $CentellaVcpkg
        if ($LASTEXITCODE -ne 0) { throw "No se pudo clonar vcpkg." }
    }

    Write-Host "Fijando vcpkg al baseline compatible con GRF/Python 3.10..." -ForegroundColor Yellow
    git -C $CentellaVcpkg fetch --all --tags --prune
    if ($LASTEXITCODE -ne 0) { throw "No se pudo actualizar el repositorio vcpkg aislado." }
    git -C $CentellaVcpkg checkout --force $VcpkgBaseline
    if ($LASTEXITCODE -ne 0) { throw "No se pudo seleccionar el baseline vcpkg de CENTELLA." }

    $pkgConfig = Ensure-PkgConfig
    Patch-LegacyVcpkgPkgConfig $CentellaVcpkg $pkgConfig
    $pkgDir = Split-Path -Parent $pkgConfig
    $env:PATH = "$pkgDir;$env:PATH"

    & (Join-Path $CentellaVcpkg "bootstrap-vcpkg.bat") -disableMetrics
    if ($LASTEXITCODE -ne 0) { throw "No se pudo preparar vcpkg." }
    return $CentellaVcpkg
}

Write-Host ""
Write-Host "CENTELLA FOOTBALL - WINDOWS RUNTIME" -ForegroundColor Cyan
Write-Host "Project:   $ProjectRoot"
Write-Host "Workspace: $WorkspaceRoot"
Write-Host "Toolchain: $ToolchainRoot"

$Python = Find-Python310
if (-not $Python) {
    Write-Host "" -ForegroundColor Red
    Write-Host "FALTA PYTHON 3.10 x64" -ForegroundColor Red
    Write-Host "La base nativa de esta versión utiliza ABI Python 3.10." -ForegroundColor Yellow
    Write-Host "Instala Python 3.10 x64 o restaura TOOLCHAIN\Python310 y vuelve a ejecutar este script."
    exit 10
}
Write-Host "Python: $Python" -ForegroundColor Green
& $Python --version

$bits = & $Python -c "import struct; print(struct.calcsize('P')*8)"
if ($LASTEXITCODE -ne 0 -or $bits.Trim() -ne "64") {
    throw "CENTELLA Football requiere Python 3.10 x64 para este runtime."
}

$Vcpkg = Prepare-CentellaVcpkg
Write-Host "vcpkg CENTELLA: $Vcpkg" -ForegroundColor Green
git -C $Vcpkg log -1 --oneline

$cmake = Get-Command cmake -ErrorAction SilentlyContinue
if (-not $cmake) { throw "CMake no está disponible en PATH. Abre Developer PowerShell de Visual Studio." }

New-Item -ItemType Directory -Force $Cache | Out-Null
$env:VCPKG_ROOT = $Vcpkg
$env:VCPKG_DEFAULT_BINARY_CACHE = $Cache
$env:VCPKG_DISABLE_METRICS = "1"
$env:VCPKG_FEATURE_FLAGS = "versions"
$env:CMAKE_POLICY_VERSION_MINIMUM = "3.10"
$env:GENERATOR_PLATFORM = "x64"
$env:PY_VERSION = "3.10"
$env:BUILD_CONFIGURATION = "Release"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:PYGAME_HIDE_SUPPORT_PROMPT = "1"
Set-Location $ProjectRoot

Write-Host "`n[1/5] Preparando herramientas Python compatibles..." -ForegroundColor Cyan
& $Python -m pip install "pip==23.2.1" "setuptools==65.5.0" "wheel==0.38.4"
if ($LASTEXITCODE -ne 0) { throw "No se pudieron preparar pip/setuptools/wheel." }

Write-Host "`n[2/5] Instalando Gym legado sin aislamiento..." -ForegroundColor Cyan
& $Python -m pip install --no-build-isolation "gym==0.21.0"
if ($LASTEXITCODE -ne 0) {
    throw "Gym 0.21 no pudo instalarse. El script NO continuará con un entorno parcialmente roto."
}

Write-Host "`n[3/5] Instalando dependencias estables del runtime..." -ForegroundColor Cyan
& $Python -m pip install `
    "pygame==2.6.1" `
    "absl-py>=1.4,<3" `
    "psutil>=5.9,<8" `
    "numpy==1.26.4" `
    "opencv-python==4.10.0.84" `
    "six>=1.16,<2"
if ($LASTEXITCODE -ne 0) { throw "Falló la instalación de dependencias Python." }

function Invoke-GrfBuild {
    Write-Host "`n[4/5] Compilando Gameplay Football / GRF..." -ForegroundColor Cyan
    & $Python -m pip install -e . --no-build-isolation --no-deps -v
    return [int]$LASTEXITCODE
}

$firstExit = Invoke-GrfBuild
if ($firstExit -ne 0) {
    Write-Host "Primer intento falló. Comprobando compatibilidad Boost Atomic histórica..." -ForegroundColor Yellow
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
        Write-Host "No cambies paquetes al azar: envía desde '[4/5]' hasta el final para comparar con CI." -ForegroundColor Yellow
        exit $secondExit
    }
}

Write-Host "`n[5/5] Verificando imports, arquitectura y API nativa..." -ForegroundColor Cyan
& $Python -c "import struct,absl,pygame,numpy,cv2,psutil,gfootball_engine; assert struct.calcsize('P')*8==64; assert hasattr(gfootball_engine,'GameEnv'); assert hasattr(gfootball_engine,'GameState'); print('gfootball_engine:', gfootball_engine.__file__); print('RUNTIME OK - 64 bit')"
if ($LASTEXITCODE -ne 0) { throw "El build terminó pero el módulo nativo no es utilizable." }

Write-Host "`nCENTELLA Football runtime listo." -ForegroundColor Green
Write-Host "Ya puedes cerrar esta ventana y ejecutar:" -ForegroundColor White
Write-Host "  .\scripts\RUN_BETA.ps1" -ForegroundColor Cyan
Write-Host "o hacer doble clic en RUN_CENTELLA_BETA.bat" -ForegroundColor Cyan
