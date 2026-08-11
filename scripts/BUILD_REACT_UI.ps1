$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$UiRoot = Join-Path $ProjectRoot "centella\ui"
$Output = Join-Path $ProjectRoot "centella\web-react\index.html"

if (-not (Test-Path (Join-Path $UiRoot "package.json"))) {
    throw "No encontré centella\ui\package.json. Actualiza la rama antes de compilar la UI."
}

$node = Get-Command node -ErrorAction SilentlyContinue
$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $node -or -not $npm) {
    throw "La nueva UI requiere Node.js + npm para el build de desarrollo. Instala Node.js LTS y vuelve a ejecutar este script."
}

Write-Host "CENTELLA React UI" -ForegroundColor Cyan
Write-Host "Node: $(& node --version)"
Write-Host "npm:  $(& npm --version)"

Push-Location $UiRoot
try {
    if (-not (Test-Path (Join-Path $UiRoot "node_modules"))) {
        Write-Host "[1/2] Instalando dependencias de UI..." -ForegroundColor Yellow
        & npm install
        if ($LASTEXITCODE -ne 0) { throw "npm install fallo con codigo $LASTEXITCODE" }
    }
    else {
        Write-Host "[1/2] Dependencias existentes; reutilizando node_modules." -ForegroundColor DarkGray
    }

    Write-Host "[2/2] Compilando interfaz React/TypeScript..." -ForegroundColor Yellow
    & npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build fallo con codigo $LASTEXITCODE" }
}
finally {
    Pop-Location
}

if (-not (Test-Path $Output)) {
    throw "Vite termino, pero no existe centella\web-react\index.html."
}

Write-Host "CENTELLA REACT UI: READY" -ForegroundColor Green
Write-Host $Output -ForegroundColor DarkGray
