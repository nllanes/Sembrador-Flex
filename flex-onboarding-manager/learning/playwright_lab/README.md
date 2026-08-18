# Laboratorio de automatización web (Playwright)

Aquí aprendes **las técnicas reales de automatización de navegador** — las mismas
que imaginabas para tu idea (login, formularios multi-paso, ingresar un ZIP code,
guardar cuántas corridas tuvieron respuesta) — pero practicando contra un sitio
**hecho para eso**: [`saucedemo.com`](https://www.saucedemo.com/).

> ⚖️ **Por qué este sitio y no uno real:** automatizar el registro/login de
> servicios reales de terceros (como Amazon Flex) casi siempre viola sus
> Términos de Servicio y puede ser ilegal. `saucedemo.com` es un sandbox público
> creado por Sauce Labs justamente para practicar. Las **técnicas son idénticas**;
> lo que cambia es que aquí sí tienes permiso.

## Qué enseña el script `automation_demo.py`

| Paso | Técnica que aprendes |
|------|----------------------|
| `login()` | Navegar, rellenar credenciales, click, esperar navegación |
| `add_first_items_to_cart()` | Seleccionar múltiples elementos y actuar en bucle |
| `checkout()` | **Formulario multi-paso con un campo de ZIP code** |
| `save_run()` | Guardar el resultado de cada corrida en **SQLite** |
| Resumen final | Agregar "de cuántas corridas tuve respuesta/éxito" |

## Cómo ejecutarlo

```bash
cd learning/playwright_lab
pip install -r requirements.txt
playwright install chromium      # descarga el navegador una sola vez

python automation_demo.py            # sin ventana (headless)
python automation_demo.py --headed   # para VER el navegador moviéndose
python automation_demo.py --zip 90210
```

### Runner por lote (una lista de ZIPs)

`batch_runner.py` lee `zips.txt` (un ZIP por línea) y corre el flujo para cada uno,
con una sesión nueva por ZIP, guardando el resultado y mostrando un resumen final
de "de cuántos tuve respuesta".

```bash
python batch_runner.py                 # usa zips.txt
python batch_runner.py --file otros.txt --headed
```

Cada corrida guarda una fila en `results.db` (tabla `runs`) y al final imprime
cuántas fueron exitosas.

## Conceptos clave que estás practicando

- **Auto-waiting:** Playwright espera solo a que el elemento esté listo. Evita
  `sleep(3)` frágiles.
- **Selectores robustos:** `get_by_placeholder`, `get_by_test_id`, `#id`. Mejor
  que XPaths largos que se rompen con cualquier cambio de diseño.
- **Flujo multi-paso:** cada `wait_for_url(...)` confirma que avanzaste de página.
- **Manejo de errores:** el `try/except` captura timeouts y guarda el fallo, para
  que un error no tumbe todo el proceso.
- **Persistencia de resultados:** SQLite como bitácora de corridas.

## Ejercicios para seguir aprendiendo

1. **Datos desde una lista:** en vez de un solo ZIP, lee una lista de ZIPs desde
   un archivo `zips.txt` y corre el flujo para cada uno, guardando el resultado.
2. **Capturas de pantalla:** añade `page.screenshot(path=f"shot_{zip}.png")` en el
   paso de confirmación.
3. **Login fallido:** prueba con `locked_out_user` (usuario bloqueado del sandbox)
   y aprende a detectar y registrar el mensaje de error.
4. **Extracción de datos:** lee los nombres y precios de los productos del
   inventario y guárdalos en la base de datos (scraping ético sobre el sandbox).
5. **Reintentos:** si un paso falla por timeout, reintenta hasta 3 veces.
6. **Modo asíncrono:** reescribe con `playwright.async_api` para correr varias
   sesiones en paralelo.

## Cómo se conecta con el CRM

El CRM (`flex-onboarding-manager`) es el **registro/tracking** del proceso; este
laboratorio es donde aprendes la **mecánica de automatización**. En un flujo
legítimo, una persona hace el registro real y tú usas el CRM para llevar el
control por ZIP code. Este lab te da las habilidades técnicas sin cruzar la línea
de automatizar servicios de terceros sin permiso.
