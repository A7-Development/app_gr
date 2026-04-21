#Requires -Version 5.1
<#
.SYNOPSIS
    Inicia o servidor de desenvolvimento do GR Backend (FastAPI + Uvicorn).

.DESCRIPTION
    Ativa o venv local (.venv), aplica migrations do Alembic (pode ser pulado)
    e sobe o Uvicorn com hot-reload na porta escolhida.

.PARAMETER BindHost
    Interface para bind. Default: 127.0.0.1.

.PARAMETER Port
    Porta TCP. Default: 8000.

.PARAMETER SkipMigrations
    Nao roda "alembic upgrade head" antes de subir a API.

.PARAMETER NoReload
    Sobe sem --reload (util para profiling / medir tempo de boot real).

.EXAMPLE
    .\start.ps1
    .\start.ps1 -Port 8080 -SkipMigrations
    .\start.ps1 -BindHost 0.0.0.0
#>

[CmdletBinding()]
param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$SkipMigrations,
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$venvActivate = Join-Path $PSScriptRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $venvActivate)) {
    Write-Error "Venv nao encontrado em .venv. Rode: uv venv --python 3.13 && uv sync --extra dev"
    exit 1
}

if (-not (Test-Path (Join-Path $PSScriptRoot ".env"))) {
    Write-Warning ".env nao encontrado. Copie .env.example para .env e ajuste os valores."
}

Write-Host "[start] Ativando venv..." -ForegroundColor Cyan
. $venvActivate

if (-not $SkipMigrations) {
    Write-Host "[start] Aplicando migrations (alembic upgrade head)..." -ForegroundColor Cyan
    alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Falha ao aplicar migrations. Use -SkipMigrations para subir assim mesmo."
        exit $LASTEXITCODE
    }
}

$uvicornArgs = @(
    "app.main:app",
    "--host", $BindHost,
    "--port", $Port
)
if (-not $NoReload) { $uvicornArgs += "--reload" }

Write-Host "[start] Subindo Uvicorn em http://${BindHost}:${Port} (docs em /docs)" -ForegroundColor Green
uvicorn @uvicornArgs
