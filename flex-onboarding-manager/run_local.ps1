# Arranque rápido en Windows (sin Docker)
# Usa SQLite en dev.db y puerto 8080 (el 8000 suele estar bloqueado en Windows).

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    (Get-Content ".env") -replace 'postgresql\+psycopg2://flex:flex@db:5432/flex_onboarding', 'sqlite:///./dev.db' | Set-Content ".env"
}

Write-Host "Iniciando en http://127.0.0.1:8080 ..."
python -m uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload
