"""Laboratorio de automatización web con Playwright.

OBJETIVO DE APRENDIZAJE
-----------------------
Aprender las técnicas base de automatización de navegador:
  1. Lanzar un navegador y navegar.
  2. Localizar elementos con selectores robustos.
  3. Rellenar formularios (incluido un campo de ZIP code).
  4. Manejar un flujo multi-paso (login -> carrito -> checkout -> confirmación).
  5. Esperar de forma correcta (auto-waiting) en vez de sleeps.
  6. Guardar los resultados de cada corrida en una base de datos SQLite.

TARGET
------
https://www.saucedemo.com/  --> es un sitio PÚBLICO diseñado por Sauce Labs
específicamente para practicar automatización de pruebas. Es 100% legítimo
practicar aquí (a diferencia de automatizar sitios reales de terceros, que
suele violar sus Términos de Servicio).

Estas mismas técnicas son las que se usan en testing automatizado (QA),
scraping ético y RPA. Lo importante no es el sitio, sino las técnicas.

Uso:
    pip install -r requirements.txt
    playwright install chromium
    python automation_demo.py            # modo headless
    python automation_demo.py --headed   # ver el navegador en acción
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

BASE_URL = "https://www.saucedemo.com/"
DB_PATH = Path(__file__).parent / "results.db"

# Credenciales de prueba PÚBLICAS que el propio sitio publica en su portada.
DEMO_USER = "standard_user"
DEMO_PASS = "secret_sauce"


# --------------------------------------------------------------------------- #
# Persistencia: guardamos el resultado de cada corrida (como querías "guardar
# de cuántos tuve respuesta"). Aquí guardamos éxito/fallo y el número de orden.
# --------------------------------------------------------------------------- #
def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            zip_code TEXT,
            success INTEGER NOT NULL,
            confirmation TEXT,
            error TEXT
        )
        """
    )
    conn.commit()
    return conn


def save_run(
    conn: sqlite3.Connection,
    *,
    zip_code: str,
    success: bool,
    confirmation: str | None,
    error: str | None,
) -> None:
    conn.execute(
        "INSERT INTO runs (started_at, zip_code, success, confirmation, error) VALUES (?, ?, ?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), zip_code, int(success), confirmation, error),
    )
    conn.commit()


# --------------------------------------------------------------------------- #
# Pasos del flujo. Cada función enseña una técnica concreta.
# --------------------------------------------------------------------------- #
def login(page: Page) -> None:
    """Técnica: navegar + rellenar credenciales + click, con auto-waiting."""
    page.goto(BASE_URL)
    # get_by_placeholder / get_by_test_id son selectores robustos (mejor que XPaths frágiles).
    page.get_by_placeholder("Username").fill(DEMO_USER)
    page.get_by_placeholder("Password").fill(DEMO_PASS)
    page.locator("#login-button").click()
    # Playwright espera automáticamente a que aparezca el inventario.
    page.wait_for_url("**/inventory.html")


def add_first_items_to_cart(page: Page, how_many: int = 2) -> int:
    """Técnica: seleccionar múltiples elementos y actuar en bucle."""
    buttons = page.locator("button:has-text('Add to cart')")
    count = min(how_many, buttons.count())
    for _ in range(count):
        # Siempre tomamos el primero visible; al añadirlo, el texto del botón cambia.
        page.locator("button:has-text('Add to cart')").first.click()
    return count


def checkout(page: Page, first: str, last: str, zip_code: str) -> str:
    """Técnica: formulario multi-paso con un campo de ZIP code (como tu idea)."""
    page.locator(".shopping_cart_link").click()
    page.wait_for_url("**/cart.html")

    page.get_by_test_id("checkout").click()
    page.wait_for_url("**/checkout-step-one.html")

    # Aquí está tu "ingresar ZIP code" en un formulario real.
    page.locator("#first-name").fill(first)
    page.locator("#last-name").fill(last)
    page.locator("#postal-code").fill(zip_code)
    page.locator("#continue").click()

    page.wait_for_url("**/checkout-step-two.html")
    page.locator("#finish").click()

    page.wait_for_url("**/checkout-complete.html")
    # Capturamos el mensaje de confirmación (la "respuesta" del sistema).
    return page.locator(".complete-header").inner_text()


# --------------------------------------------------------------------------- #
# Orquestador
# --------------------------------------------------------------------------- #
def run(headed: bool, zip_code: str) -> bool:
    conn = init_db()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        page = browser.new_page()
        confirmation: str | None = None
        error: str | None = None
        success = False
        try:
            login(page)
            added = add_first_items_to_cart(page, how_many=2)
            print(f"[lab] {added} producto(s) agregado(s) al carrito.")
            confirmation = checkout(page, "Juan", "Perez", zip_code)
            success = confirmation.lower().startswith("thank you")
            print(f"[lab] Confirmación: {confirmation!r}")
        except PWTimeout as exc:
            error = f"Timeout esperando un elemento: {exc}"
            print(f"[lab] ERROR: {error}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 (didáctico)
            error = repr(exc)
            print(f"[lab] ERROR: {error}", file=sys.stderr)
        finally:
            browser.close()
            save_run(conn, zip_code=zip_code, success=success, confirmation=confirmation, error=error)

    # Resumen agregado (como tu "de cuántos tuve respuesta").
    total, ok = conn.execute("SELECT COUNT(*), COALESCE(SUM(success),0) FROM runs").fetchone()
    conn.close()
    print(f"[lab] Historial: {ok}/{total} corridas exitosas (guardado en {DB_PATH.name}).")
    return success


def main() -> None:
    parser = argparse.ArgumentParser(description="Laboratorio de automatización con Playwright")
    parser.add_argument("--headed", action="store_true", help="Mostrar el navegador")
    parser.add_argument("--zip", default="33101", help="ZIP code a ingresar en el checkout")
    args = parser.parse_args()

    ok = run(headed=args.headed, zip_code=args.zip)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
