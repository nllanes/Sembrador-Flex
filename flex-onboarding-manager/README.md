# flex-onboarding-manager

CRM ligero para gestionar **expedientes de onboarding de conductores Amazon Flex**:
emails asignados, estados del proceso (desde `not_started` hasta
`waitlisted` / `approved_active`), checklist de seguimiento, línea de tiempo
(timeline) y **handoff** cuando el expediente está listo para vincularse en otro
sistema.

> ⚠️ **Alcance:**
> - ✅ **Tracking** de estados, checklist, timeline y handoff.
> - ✅ **Sembrar** (opcional): cuenta Amazon + región/ZIP en Flex; **para antes** de docs personales.
> - ❌ **No hace:** background checks de Amazon ni el Monitor SaaS.
> - Detalle del flujo Sembrar: [`docs/sembrar_idea_y_flujo.md`](docs/sembrar_idea_y_flujo.md).

## Stack

- **FastAPI** (API REST + panel web servido como estático)
- **PostgreSQL** + **SQLAlchemy 2.0**
- **Alembic** (migraciones)
- **Docker** + **docker-compose**
- Panel web **vanilla JS** (sin build, sin dependencias front)

## Estructura

```
flex-onboarding-manager/
├── app/
│   ├── main.py            # App FastAPI + montaje del panel web
│   ├── config.py          # Settings desde entorno / .env
│   ├── database.py        # Engine, sesión, Base declarativa
│   ├── enums.py           # Estados de onboarding, checklist, eventos
│   ├── models.py          # Modelos ORM (Candidate, ChecklistItem, TimelineEvent)
│   ├── schemas.py         # Schemas Pydantic
│   ├── crud.py            # Lógica de negocio + timeline
│   ├── routers/           # Endpoints: candidates, checklist, meta
│   └── static/            # Panel web (index.html, styles.css, app.js)
├── alembic/               # Migraciones
├── learning/              # Laboratorios de aprendizaje (ver más abajo)
│   ├── playwright_lab/    # Automatización web contra un sandbox legítimo
│   └── credentials_lab/   # Manejo seguro de credenciales + dominio de correo
├── docs/
│   ├── sembrar_idea_y_flujo.md  # Idea + flujo completo Sembrar (Amazon + Flex)
│   ├── flow.md                  # Estados CRM / handoff
│   ├── flex_apply.md            # Setup Appium / outcomes
│   └── …
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh          # Espera a la BD y corre migraciones
├── requirements.txt
└── .env.example
```

## Puesta en marcha con Docker (recomendado)

```bash
cp .env.example .env        # ajusta credenciales si quieres
docker compose up --build
```

Esto levanta PostgreSQL, aplica las migraciones automáticamente y arranca la API.

- Panel web: <http://localhost:8000/>
- Docs interactivas (Swagger): <http://localhost:8000/docs>
- Healthcheck: <http://localhost:8000/health>

## Puesta en marcha local (sin Docker)

Requiere una instancia de PostgreSQL en marcha.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edita DATABASE_URL, p.ej.:
# DATABASE_URL=postgresql+psycopg2://flex:flex@localhost:5432/flex_onboarding

alembic upgrade head
uvicorn app.main:app --reload
```

## Estados del onboarding

| Estado                 | Significado                                        |
|------------------------|----------------------------------------------------|
| `not_started`          | Email asignado, sin iniciar                        |
| `invited`              | Invitación enviada al candidato                    |
| `registration_started` | El candidato empezó el registro en Amazon          |
| `documents_pending`    | Faltan documentos                                  |
| `documents_submitted`  | Documentos completos                               |
| `background_check`     | En verificación de antecedentes (por Amazon)       |
| `waitlisted`           | En lista de espera de Amazon                       |
| `approved_active`      | Aprobado y activo → se marca `handoff_ready`       |
| `rejected`             | Rechazado (terminal)                               |
| `inactive`             | Dado de baja / pausado (terminal)                  |

Al llegar a `approved_active`, el expediente se marca automáticamente como
`handoff_ready`. El **handoff** se confirma manualmente vía endpoint/panel,
guardando opcionalmente una `external_ref` (id en el sistema de monitoreo).

## API (resumen)

Prefijo por defecto: `/api`

| Método | Ruta                                | Descripción                                  |
|--------|-------------------------------------|----------------------------------------------|
| GET    | `/candidates`                       | Listar (filtros: `status`, `search`, paginación) |
| POST   | `/candidates`                       | Crear expediente (genera checklist estándar) |
| POST   | `/candidates/import`                | Importar lote desde CSV                      |
| GET    | `/candidates/{id}`                  | Detalle (con checklist + timeline)           |
| PATCH  | `/candidates/{id}`                  | Editar datos                                 |
| DELETE | `/candidates/{id}`                  | Eliminar expediente                          |
| POST   | `/candidates/{id}/status`           | Cambiar estado (registra en timeline)        |
| POST   | `/candidates/{id}/notes`            | Añadir nota al timeline                      |
| POST   | `/candidates/{id}/handoff`          | Marcar handoff completado                    |
| PUT    | `/candidates/{id}/mailbox-credential` | Guardar contraseña de buzón (cifrada)      |
| GET    | `/candidates/{id}/mailbox-credential` | Revelar contraseña (descifra + audita)     |
| DELETE | `/candidates/{id}/mailbox-credential` | Eliminar la credencial                     |
| GET    | `/candidates/{id}/timeline`         | Ver timeline                                 |
| POST   | `/candidates/{id}/checklist`        | Añadir ítem de checklist                     |
| PATCH  | `/checklist-items/{id}`             | Actualizar ítem                              |
| DELETE | `/checklist-items/{id}`             | Eliminar ítem                                |
| GET    | `/meta/statuses`                    | Catálogo de estados                          |
| GET    | `/meta/summary`                     | Conteo por estado (dashboard)                |
| GET    | `/meta/zip-stats`                   | Conversión por ZIP code (total/aplicados/respuesta/activos) |
| GET    | `/meta/location-stats`              | Totales por ciudad y ZIP (desglose ciudad → ZIP)           |

### Ejemplo rápido

```bash
# Crear expediente
curl -X POST http://localhost:8000/api/candidates \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Juan Pérez","assigned_email":"juan.flex@example.com"}'

# Cambiar estado
curl -X POST http://localhost:8000/api/candidates/1/status \
  -H "Content-Type: application/json" \
  -d '{"status":"invited","actor":"reclutador1"}'
```

### Importar CSV

```bash
curl -X POST "http://localhost:8000/api/candidates/import?seed_checklist=true" \
  -F "file=@docs/candidates_import_example.csv"
```

Columnas soportadas: `full_name`, `assigned_email` (o `email`), `zip_code` (o `zip`),
`phone`, `region`, `notes`, `mailbox_password` (opcional, se guarda cifrada).
Filas con email duplicado se omiten; errores de validación se reportan por línea.

Desde el panel web: botón **Importar CSV** en la barra superior.

## Migraciones (Alembic)

```bash
# Aplicar
alembic upgrade head

# Generar una nueva migración tras cambiar modelos
alembic revision --autogenerate -m "descripcion"
```

## Laboratorios de aprendizaje (`learning/`)

Módulos didácticos para aprender las técnicas de automatización de forma
**legítima** (sin automatizar servicios de terceros sin permiso):

- [`learning/playwright_lab/`](learning/playwright_lab/README.md): automatización
  web con Playwright (login, formulario multi-paso con ZIP code, guardado de
  resultados) practicando contra `saucedemo.com`, un sandbox público hecho para eso.
- [`learning/credentials_lab/`](learning/credentials_lab/README.md): manejo seguro
  de credenciales (hashing vs. cifrado) y cómo funciona un dominio de correo propio
  (MX/SPF/DKIM/DMARC, buzones, alias, catch-all).

> Nota de alcance: estos labs enseñan las **técnicas**. Automatizar el registro o
> la creación masiva de cuentas en servicios de terceros (p. ej. Amazon Flex) viola
> sus Términos y no forma parte de este proyecto.

## Credenciales de buzón (cifradas en reposo)

Cada expediente puede guardar la **contraseña del buzón de correo que tu
organización administra** para esa persona real. Se cifra con Fernet (ver
`app/security.py`) usando la clave `CRED_KEY` del entorno:

- El detalle/listado nunca expone el secreto: solo un booleano `has_mailbox_credential`.
- Revelar la contraseña (`GET .../mailbox-credential`) la descifra bajo demanda y
  **deja registro en el timeline** (evento `credential_revealed`).
- Genera tu clave con:
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
  y ponla en `CRED_KEY` (en producción, en un gestor de secretos; nunca en el repo).

> Uso legítimo: administrar buzones de personas reales de tu organización. No es
> para fabricar cuentas de terceros.

## Análisis por ciudad y ZIP code

Cada expediente puede tener **ciudad** (`region` en la API/CSV) y **ZIP code**. El panel
muestra dos secciones en el panel izquierdo:

- **Por ciudad**: total por ciudad y, debajo, cuántos hay en cada ZIP de esa ciudad.
- **Por ZIP code**: total global de cada ZIP (todas las ciudades).

Haz clic en una ciudad o ZIP para filtrar la lista. También puedes escribir en los
campos de filtro o quitar filtros con las chips activas.

API: `GET /api/meta/location-stats` y filtros `?city=Miami&zip=33101` en el listado.

## Diagramas de flujo

Ver [`docs/flow.md`](docs/flow.md): máquina de estados, flujo operativo y modelo
de datos (Mermaid).

## Handoff hacia el sistema de monitoreo

Cuando un expediente llega a `approved_active` queda **listo para handoff**. El
traspaso es **manual**: se llama a `POST /candidates/{id}/handoff` (o el botón en
el panel) para marcarlo como entregado y guardar la referencia externa. Este
proyecto **no** integra ni modifica el sistema de monitoreo; solo deja el rastro
del punto de vinculación.
