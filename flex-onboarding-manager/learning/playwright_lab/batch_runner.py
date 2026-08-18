"""Ejercicio: correr el flujo de automatización para una LISTA de ZIP codes.

Lee ZIPs desde un archivo (uno por línea), ejecuta el flujo del sandbox para
cada uno y al final imprime un resumen: "de cuántos tuve respuesta/éxito".
Reutiliza las funciones de `automation_demo.py` (login, carrito, checkout).

Uso:
    python batch_runner.py                 # usa zips.txt
    python batch_runner.py --file otros.txt --headed
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout, sync_playwright

from automation_demo import (
    add_first_items_to_cart,
    checkout,
    init_db,
    login,
    save_run,
)


def read_zips(path: Path) -> list[str]:
    """Lee ZIPs de un archivo, ignorando líneas vacías y comentarios (#)."""
    zips: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            zips.append(line)
    return zips


def run_batch(file: Path, headed: bool) -> None:
    zips = read_zips(file)
    if not zips:
        print(f"[batch] No hay ZIPs en {file}.")
        return

    print(f"[batch] Procesando {len(zips)} ZIP code(s): {', '.join(zips)}")
    conn = init_db()
    results: dict[str, bool] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        for zip_code in zips:
            # Un contexto nuevo por ZIP = sesión limpia (como usuario distinto).
            context = browser.new_context()
            page = context.new_page()
            confirmation = error = None
            success = False
            try:
                login(page)
                add_first_items_to_cart(page, how_many=1)
                confirmation = checkout(page, "Juan", "Perez", zip_code)
                success = confirmation.lower().startswith("thank you")
                print(f"[batch] ZIP {zip_code}: {'OK' if success else 'sin confirmación'}")
            except PWTimeout as exc:
                error = f"timeout: {exc}"
                print(f"[batch] ZIP {zip_code}: ERROR {error}")
            except Exception as exc:  # noqa: BLE001 (didáctico)
                error = repr(exc)
                print(f"[batch] ZIP {zip_code}: ERROR {error}")
            finally:
                save_run(conn, zip_code=zip_code, success=success, confirmation=confirmation, error=error)
                results[zip_code] = success
                context.close()
        browser.close()

    ok = sum(1 for v in results.values() if v)
    print("\n[batch] ===== RESUMEN =====")
    for zip_code, success in results.items():
        print(f"  {zip_code}: {'[OK] respuesta/exito' if success else '[--] sin exito'}")
    print(f"[batch] {ok}/{len(results)} ZIPs con respuesta exitosa.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Runner por lote de ZIPs (Playwright)")
    parser.add_argument("--file", default="zips.txt", help="Archivo con ZIPs (uno por línea)")
    parser.add_argument("--headed", action="store_true", help="Mostrar el navegador")
    args = parser.parse_args()

    run_batch(Path(args.file), headed=args.headed)


if __name__ == "__main__":
    main()
