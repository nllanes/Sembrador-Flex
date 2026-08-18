#!/usr/bin/env bash
set -e

# Espera a que PostgreSQL esté disponible y aplica migraciones antes de arrancar.

echo "[entrypoint] Esperando a PostgreSQL..."
python - <<'PY'
import os, time, sys
import psycopg2

url = os.environ.get("DATABASE_URL", "")
# Normaliza la URL SQLAlchemy -> libpq
dsn = url.replace("postgresql+psycopg2://", "postgresql://")

for attempt in range(30):
    try:
        conn = psycopg2.connect(dsn)
        conn.close()
        print("[entrypoint] PostgreSQL disponible.")
        sys.exit(0)
    except Exception as exc:
        print(f"[entrypoint] intento {attempt+1}/30: {exc}")
        time.sleep(2)
print("[entrypoint] No se pudo conectar a PostgreSQL.", file=sys.stderr)
sys.exit(1)
PY

echo "[entrypoint] Aplicando migraciones (alembic upgrade head)..."
alembic upgrade head

echo "[entrypoint] Iniciando aplicación..."
exec "$@"
