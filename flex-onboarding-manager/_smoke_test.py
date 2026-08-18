"""Smoke test temporal: valida el flujo de la API contra SQLite en memoria."""
import os
os.environ["DATABASE_URL"] = "sqlite:///./_smoke.db"

# Limpieza previa
if os.path.exists("_smoke.db"):
    os.remove("_smoke.db")

from fastapi.testclient import TestClient
from app.database import Base, engine
from app import models  # noqa
from app.main import app

Base.metadata.create_all(bind=engine)
client = TestClient(app)

assert client.get("/health").json()["status"] == "ok"

# Crear candidato
r = client.post("/api/candidates", json={"full_name": "Juan Perez", "assigned_email": "juan.flex@example.com"})
assert r.status_code == 201, r.text
c = r.json()
cid = c["id"]
assert c["status"] == "not_started"
assert len(c["checklist_items"]) == 9, c["checklist_items"]
assert len(c["timeline_events"]) == 1

# Email duplicado -> 409
assert client.post("/api/candidates", json={"full_name": "X", "assigned_email": "juan.flex@example.com"}).status_code == 409

# Cambiar estado
r = client.post(f"/api/candidates/{cid}/status", json={"status": "invited", "actor": "recluta"})
assert r.status_code == 200, r.text
assert r.json()["status"] == "invited"

# Nota
assert client.post(f"/api/candidates/{cid}/notes", json={"message": "Llamada realizada"}).status_code == 201

# Handoff antes de approved -> 409
assert client.post(f"/api/candidates/{cid}/handoff", json={}).status_code == 409

# Avanzar a approved_active -> handoff_ready true
r = client.post(f"/api/candidates/{cid}/status", json={"status": "approved_active"})
assert r.json()["handoff_ready"] is True, r.text

# Handoff done
r = client.post(f"/api/candidates/{cid}/handoff", json={"external_ref": "MON-123"})
assert r.status_code == 200, r.text
assert r.json()["handoff_done"] is True
assert r.json()["external_ref"] == "MON-123"

# Checklist update
item_id = c["checklist_items"][0]["id"]
r = client.patch(f"/api/checklist-items/{item_id}", json={"status": "done"})
assert r.status_code == 200 and r.json()["status"] == "done", r.text

# Meta summary
summary = client.get("/api/meta/summary").json()["by_status"]
assert summary["approved_active"] == 1, summary

# Lista con filtro y búsqueda
assert client.get("/api/candidates?status=approved_active").json()["total"] == 1
assert client.get("/api/candidates?search=juan").json()["total"] == 1

# Timeline debe tener varios eventos (created, status x2, note, handoff_ready, handoff_done, checklist)
tl = client.get(f"/api/candidates/{cid}/timeline").json()
types = {e["event_type"] for e in tl}
assert {"created", "status_changed", "note_added", "handoff_ready", "handoff_done"}.issubset(types), types

# Delete
assert client.delete(f"/api/candidates/{cid}").status_code == 204
assert client.get(f"/api/candidates/{cid}").status_code == 404

print("SMOKE TEST OK - todos los asserts pasaron")
