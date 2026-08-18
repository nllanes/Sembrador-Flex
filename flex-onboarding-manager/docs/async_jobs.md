# Jobs async de Sembrar (cloud-ready)

## Idea

`Sembrar` **ya no bloquea** el HTTP 2–3 minutos. Encola un job en la BD y el **worker** lo procesa.

```
UI  →  POST /api/candidates/batch/dispatch-flex  →  202 { job_id }
UI  →  GET  /api/jobs/{job_id}  (poll)           →  queued|running|completed|failed
Worker → claim job → Playwright/Appium → guarda result
```

## Local (por defecto)

`FLEX_WORKER_EMBEDDED=true` → el API arranca un hilo worker.

Solo necesitas:

```powershell
.\run_local.ps1
```

## Cloud

1. Despliega el **API/CRM** (sin Playwright/Appium en ese contenedor, o con).
2. En `.env` del API:

```env
FLEX_WORKER_EMBEDDED=false
```

3. En otra máquina/servicio (con Chromium + opcional Appium/emulador):

```powershell
python -m scripts.flex_worker
```

Ese worker usa la misma `DATABASE_URL` y `CRED_KEY`.

## Endpoints

| Método | Ruta | Qué hace |
|--------|------|----------|
| POST | `/api/candidates/batch/dispatch-flex` | Encola (202) |
| POST | `/api/jobs/flex-dispatch` | Igual, ruta explícita |
| GET | `/api/jobs/{id}` | Estado + resultado |

## Tabla

`flex_jobs`: id, status, candidate_ids, result JSON, error, timestamps.
