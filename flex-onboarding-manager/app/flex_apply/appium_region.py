"""Automatización Appium de Amazon Flex (Android) hasta región/lista.

Alcance:
  - Abrir app Amazon Flex
  - Login con email/password de la siembra
  - Introducir ZIP
  - Detectar: región OK | join list | OTP | pantalla de docs (STOP)

NO sube licencia, SSN, seguro ni banco.
Requiere: Appium Server + emulador/dispositivo Android + app Flex instalada.
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from pathlib import Path

from app.config import get_settings
from app.flex_apply.service import (
    EVIDENCE_DIR,
    FlexApplyOutcome,
    FlexApplyStatus,
    _ensure_evidence_dir,
    _safe_slug,
)

logger = logging.getLogger(__name__)

# Marcadores de pantalla (texto visible en la app)
PERSONAL_MARKERS = (
    "driver's license",
    "drivers license",
    "driver license",
    "social security",
    "ssn",
    "bank account",
    "routing number",
    "auto insurance",
    "background check",
    "upload your license",
    "take a photo",
    "scan your license",
)

WAITLIST_MARKERS = (
    "join list",
    "join the list",
    "interest list",
    "not currently recruiting",
    "not actively recruiting",
    "we'll notify you",
    "we will notify you",
    "no opportunities",
    "spots become available",
    "waitlist",
)

REGION_READY_MARKERS = (
    "select a service area",
    "choose your region",
    "continue onboarding",
    "complete your profile",
    "start onboarding",
    "get started",
    "you're almost ready",
    "delivery partner",
    "welcome to amazon flex",
    "next steps",
)

OTP_MARKERS = (
    "verification code",
    "enter the code",
    "one-time password",
    "otp",
    "verify your email",
    "verify your phone",
    "código de verificación",
    "codigo de verificacion",
    "ingresa el código",
    "introduce el código",
    "verificar correo",
)


def _page_source_lower(driver) -> str:
    try:
        return (driver.page_source or "").lower()
    except Exception:
        return ""


def _visible_text(driver) -> str:
    """Mejor esfuerzo: page_source + textos de TextView."""
    chunks = [_page_source_lower(driver)]
    try:
        for el in driver.find_elements("xpath", "//android.widget.TextView"):
            t = (el.text or "").strip()
            if t:
                chunks.append(t.lower())
    except Exception:
        pass
    return "\n".join(chunks)


def _save_app_screenshot(driver, *, email: str, label: str) -> str | None:
    try:
        folder = _ensure_evidence_dir()
        path = folder / f"{_safe_slug(email)}_{_safe_slug(label)}_app.png"
        driver.get_screenshot_as_file(str(path))
        src = folder / f"{_safe_slug(email)}_{_safe_slug(label)}_app.xml"
        try:
            src.write_text(driver.page_source or "", encoding="utf-8", errors="ignore")
        except Exception:
            pass
        return str(path)
    except Exception as exc:
        logger.info("Appium evidence skip: %s", exc)
        return None


def _tap_by_texts(driver, texts: tuple[str, ...], *, timeout_s: float = 2.0) -> bool:
    """Toca el primer elemento cuyo text/content-desc coincida (case-insensitive)."""
    # Sin implicit wait largo: si no, cada xpath fallido suma segundos y el login tarda minutos.
    try:
        driver.implicitly_wait(0)
    except Exception:
        pass
    deadline = time.time() + timeout_s
    try:
        while time.time() < deadline:
            for raw in texts:
                t = raw.replace('"', '\\"')
                low = t.lower()
                xpaths = (
                    f'//*[@text="{raw}"]',
                    f'//*[contains(@text, "{raw}")]',
                    f'//*[@content-desc="{raw}"]',
                    f'//*[contains(@content-desc, "{raw}")]',
                    f'//*[contains(translate(@text,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"), "{low}")]',
                    f'//*[contains(translate(@content-desc,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"), "{low}")]',
                )
                for xp in xpaths:
                    try:
                        els = driver.find_elements("xpath", xp)
                        for el in els:
                            if el.is_displayed():
                                el.click()
                                time.sleep(0.8)
                                return True
                    except Exception:
                        continue
            time.sleep(0.25)
        return False
    finally:
        try:
            driver.implicitly_wait(0.5)
        except Exception:
            pass


def _fill_first_edit(driver, value: str, *, hints: tuple[str, ...] = ()) -> bool:
    """Rellena el primer EditText visible; opcionalmente filtrado por hint."""
    try:
        driver.implicitly_wait(0)
    except Exception:
        pass
    try:
        edits = driver.find_elements("class name", "android.widget.EditText")
    except Exception:
        edits = []
    for el in edits:
        try:
            if not el.is_displayed():
                continue
            hint = (el.get_attribute("hint") or "").lower()
            desc = (el.get_attribute("content-desc") or "").lower()
            resource = (el.get_attribute("resource-id") or "").lower()
            blob = f"{hint} {desc} {resource}"
            if hints and not any(h in blob for h in hints):
                continue
            el.clear()
            el.send_keys(value)
            time.sleep(0.4)
            return True
        except Exception:
            continue
    # Si había hints y falló, reintentar sin filtro
    if hints:
        return _fill_first_edit(driver, value, hints=())
    return False


def _dismiss_permissions(driver) -> None:
    _tap_by_texts(
        driver,
        (
            "While using the app",
            "Allow",
            "ALLOW",
            "Only this time",
            "Continue",
            "Continuar",
            "OK",
            "Ok",
            "Got it",
            "Entendido",
            "Accept",
            "Aceptar",
            "I agree",
            "Agree",
            "Permitir",
            "Durante el uso de la app",
            "Solo esta vez",
        ),
        timeout_s=1.2,
    )


def _detect_app_outcome(driver, *, zip_code: str | None) -> FlexApplyOutcome:
    text = _visible_text(driver)
    zip_used = zip_code
    low = text.lower()

    if any(
        m in low
        for m in (
            "correo electrónico o la contraseña son incorrectos",
            "email or password are incorrect",
            "password is incorrect",
            "there was a problem",
            "no podemos encontrar una cuenta",
            "cannot find an account",
            "auth-error",
        )
    ):
        return FlexApplyOutcome(
            ok=False,
            status=FlexApplyStatus.FAILED,
            message=(
                "Amazon rechazó el login en la app (email/contraseña incorrectos). "
                "Abre la siembra, corrige la contraseña, Guardar y vuelve a Sembrar."
            ),
            zip_used=zip_used,
        )

    if any(m in text for m in OTP_MARKERS):
        return FlexApplyOutcome(
            ok=True,
            status=FlexApplyStatus.NEEDS_VERIFICATION,
            message="La app Flex pide verificación email/SMS. Completa el código y vuelve a Sembrar.",
            zip_used=zip_used,
            needs_verification=True,
        )

    if any(m in text for m in PERSONAL_MARKERS):
        return FlexApplyOutcome(
            ok=True,
            status=FlexApplyStatus.REGION_READY,
            message=(
                "Flex aceptó la región / onboarding en la app. "
                "Parado ANTES de datos personales (licencia/SSN/banco)."
            ),
            zip_used=zip_used,
        )

    if any(m in text for m in WAITLIST_MARKERS):
        return FlexApplyOutcome(
            ok=True,
            status=FlexApplyStatus.WAITLISTED,
            message=(
                f"Amazon puso la cuenta en lista de interés"
                f"{f' para ZIP {zip_code}' if zip_code else ''} (app)."
            ),
            zip_used=zip_used,
        )

    if any(m in text for m in REGION_READY_MARKERS) and not any(
        m in text for m in ("download the app", "google play")
    ):
        return FlexApplyOutcome(
            ok=True,
            status=FlexApplyStatus.REGION_READY,
            message=(
                f"Región/service area lista en app"
                f"{f' (ZIP {zip_code})' if zip_code else ''}. "
                "Listo para que otra persona suba licencia y documentos."
            ),
            zip_used=zip_used,
        )

    if _still_on_flex_login_gate(driver):
        return FlexApplyOutcome(
            ok=False,
            status=FlexApplyStatus.FAILED,
            message=(
                "La app Flex sigue en la pantalla de login "
                "(cuenta Amazon no autenticada en el dispositivo)."
            ),
            zip_used=zip_used,
        )

    return FlexApplyOutcome(
        ok=True,
        status=FlexApplyStatus.IDENTITY_OK,
        message=(
            "Login en app Flex OK, pero no se confirmó región/lista. "
            "Revisa evidencia en var/flex_apply/."
        ),
        zip_used=zip_used,
    )


def _still_on_flex_login_gate(driver) -> bool:
    """True si la app sigue en la puerta de login (sin sesión Flex)."""
    src = _page_source_lower(driver)
    text = _visible_text(driver)
    if "sign_in_button" in src or "id/sign_in_button" in src:
        # Si ya hay formulario de email/pass, no es la puerta inicial
        if "account_edit_text" in src or "sign_in_form" in src:
            return False
        return True
    if "inicie sesión con amazon" in text or "inicie sesion con amazon" in text:
        return True
    if "crear una cuenta" in text and (
        "iniciar sesión" in text or "inicie sesión" in text
    ):
        return True
    return False


def _tap_by_ids(driver, resource_ids: tuple[str, ...], *, timeout_s: float = 3.0) -> bool:
    """Toca por resource-id (completo o sufijo)."""
    try:
        driver.implicitly_wait(0)
    except Exception:
        pass
    deadline = time.time() + timeout_s
    try:
        while time.time() < deadline:
            for rid in resource_ids:
                candidates = [rid]
                if ":id/" not in rid:
                    candidates.append(f"com.amazon.flex.rabbit:id/{rid}")
                for cand in candidates:
                    try:
                        els = driver.find_elements("id", cand)
                        for el in els:
                            if el.is_displayed():
                                el.click()
                                time.sleep(0.8)
                                return True
                    except Exception:
                        continue
                    # fallback contains
                    try:
                        xp = f'//*[contains(@resource-id, "{rid}")]'
                        els = driver.find_elements("xpath", xp)
                        for el in els:
                            if el.is_displayed():
                                el.click()
                                time.sleep(0.8)
                                return True
                    except Exception:
                        continue
            time.sleep(0.25)
        return False
    finally:
        try:
            driver.implicitly_wait(0.5)
        except Exception:
            pass


def _fill_by_id(driver, resource_ids: tuple[str, ...], value: str) -> bool:
    """Rellena un campo por resource-id (completo o sufijo)."""
    try:
        driver.implicitly_wait(0)
    except Exception:
        pass
    for rid in resource_ids:
        candidates = [rid]
        if ":id/" not in rid:
            candidates.append(f"com.amazon.flex.rabbit:id/{rid}")
        for cand in candidates:
            try:
                els = driver.find_elements("id", cand)
                for el in els:
                    if not el.is_displayed():
                        continue
                    try:
                        el.click()
                        el.clear()
                    except Exception:
                        pass
                    el.send_keys(value)
                    time.sleep(0.3)
                    return True
            except Exception:
                continue
            try:
                xp = f'//*[contains(@resource-id, "{rid}")]'
                for el in driver.find_elements("xpath", xp):
                    if not el.is_displayed():
                        continue
                    try:
                        el.click()
                        el.clear()
                    except Exception:
                        pass
                    el.send_keys(value)
                    time.sleep(0.3)
                    return True
            except Exception:
                continue
    return False


def _ensure_device_awake() -> None:
    """Despierta / intenta quitar lock antes de Appium (evita pantalla negra)."""
    try:
        _adb(["shell", "input", "keyevent", "KEYCODE_WAKEUP"], timeout_s=8)
        _adb(["shell", "wm", "dismiss-keyguard"], timeout_s=8)
        # Deslizar hacia arriba por si hay lock suave
        _adb(
            ["shell", "input", "swipe", "300", "1400", "300", "400", "300"],
            timeout_s=8,
        )
    except Exception as exc:
        logger.info("wake device skip: %s", exc)


def _ensure_flex_foreground(driver) -> bool:
    """Si el launcher u otra app está al frente, reactiva Amazon Flex."""
    settings = get_settings()
    pkg = settings.flex_app_package
    activity = settings.flex_app_activity
    try:
        from app.flex_apply.pipeline_log import step
    except Exception:
        def step(msg: str, **_k):  # type: ignore
            logger.info(msg)

    try:
        cur = (driver.current_package or "").strip()
        step(f"L1b package en primer plano={cur or '?'}")
        if cur == pkg:
            return True
        # launcher / home / otra app
        if cur in ("", "com.android.launcher", "com.miui.home", "com.google.android.apps.nexuslauncher") or (
            cur and cur != pkg
        ):
            step(f"L1b Flex no está al frente ({cur}) → activate_app / am start")
            try:
                driver.activate_app(pkg)
            except Exception as exc:
                step(f"L1b activate_app falló: {exc}; adb am start")
                component = f"{pkg}/{activity}" if activity else pkg
                _adb(
                    ["shell", "am", "start", "-n", component]
                    if activity
                    else [
                        "shell",
                        "monkey",
                        "-p",
                        pkg,
                        "-c",
                        "android.intent.category.LAUNCHER",
                        "1",
                    ],
                    timeout_s=20,
                )
            time.sleep(2.5)
            _dismiss_permissions(driver)
            cur2 = (driver.current_package or "").strip()
            step(f"L1b tras relaunch package={cur2 or '?'}")
            return cur2 == pkg
        return False
    except Exception as exc:
        step(f"L1b foreground check error: {exc}")
        return False


def _login_amazon_in_app(driver, *, email: str, password: str) -> bool:
    """Login nativo Flex: puerta → formulario email+pass en la MISMA pantalla → Iniciar sesión."""
    try:
        from app.flex_apply.pipeline_log import step
    except Exception:
        def step(msg: str, **_k):  # type: ignore
            logger.info(msg)

    _ensure_flex_foreground(driver)
    _dismiss_permissions(driver)

    # Si ya está el formulario, no hace falta tocar la puerta.
    form_ready = False
    try:
        driver.implicitly_wait(0)
        form_ready = bool(
            driver.find_elements("id", "com.amazon.flex.rabbit:id/account_edit_text")
            or driver.find_elements("id", "com.amazon.flex.rabbit:id/password_edit_text")
        )
    except Exception:
        form_ready = False
    step(f"L1b login form_ready={form_ready}")

    if not form_ready:
        tapped = _tap_by_ids(
            driver,
            ("sign_in_button", "com.amazon.flex.rabbit:id/sign_in_button"),
            timeout_s=5,
        )
        if not tapped:
            _tap_by_texts(
                driver,
                (
                    "Inicie sesión con Amazon",
                    "Inicie sesión",
                    "Iniciar sesión",
                    "Sign in",
                    "Sign In",
                    "Log in",
                ),
                timeout_s=4,
            )
        # Esperar formulario
        deadline = time.time() + 12
        while time.time() < deadline:
            try:
                if driver.find_elements(
                    "id", "com.amazon.flex.rabbit:id/account_edit_text"
                ):
                    form_ready = True
                    break
            except Exception:
                pass
            time.sleep(0.4)
        _dismiss_permissions(driver)

    # Pantalla Flex: email + password juntos (NO hay "Continue" intermedio como en web).
    filled_email = _fill_by_id(
        driver,
        (
            "com.amazon.flex.rabbit:id/account_edit_text",
            "account_edit_text",
            "meridian_input_edit_text",
        ),
        email,
    )
    if not filled_email:
        filled_email = _fill_first_edit(
            driver,
            email,
            hints=("email", "account", "correo", "phone", "usuario"),
        )
    if not filled_email:
        filled_email = _fill_first_edit(driver, email)

    filled_pass = _fill_by_id(
        driver,
        (
            "com.amazon.flex.rabbit:id/password_edit_text",
            "password_edit_text",
        ),
        password,
    )
    if not filled_pass:
        filled_pass = _fill_first_edit(
            driver,
            password,
            hints=("password", "contraseña", "contrasena", "pass"),
        )
    if not filled_pass:
        # Segundo EditText visible
        try:
            edits = [
                e
                for e in driver.find_elements("class name", "android.widget.EditText")
                if e.is_displayed()
            ]
            if len(edits) >= 2:
                edits[1].click()
                edits[1].clear()
                edits[1].send_keys(password)
                filled_pass = True
        except Exception:
            pass

    submitted = _tap_by_ids(
        driver,
        (
            "com.amazon.flex.rabbit:id/go_to_sign_in_button",
            "go_to_sign_in_button",
            "sign_in_button",
        ),
        timeout_s=3,
    )
    if not submitted:
        submitted = _tap_by_texts(
            driver,
            (
                "Iniciar sesión",
                "Inicie sesión",
                "Inicia sesión",
                "Sign in",
                "Sign In",
                "Sign-In",
                "Log in",
                "Continue",
                "Continuar",
            ),
            timeout_s=4,
        )
    # A veces el click útil es el TextView dentro del botón Meridian
    if not submitted:
        try:
            for el in driver.find_elements(
                "id", "com.amazon.flex.rabbit:id/meridian_button_text_view"
            ):
                t = (el.text or "").lower()
                if "iniciar" in t or "sign" in t or "sesión" in t or "sesion" in t:
                    el.click()
                    submitted = True
                    break
        except Exception:
            pass

    time.sleep(3.0)
    _ensure_flex_foreground(driver)
    _dismiss_permissions(driver)
    ok = bool(filled_email and filled_pass and submitted)
    step(
        f"L1b login fill email={filled_email} pass={filled_pass} "
        f"submit={submitted} ok={ok}"
    )
    logger.info(
        "App login fill email=%s pass=%s submit=%s",
        filled_email,
        filled_pass,
        submitted,
    )
    return ok


def _apply_zip_in_app(driver, zip_code: str, vehicle_type: str) -> None:
    """Introduce ZIP y, si aparece, tipo de vehículo. Para en docs personales."""
    for _ in range(4):
        _dismiss_permissions(driver)
        text = _visible_text(driver)
        if any(m in text for m in PERSONAL_MARKERS):
            return
        if any(m in text for m in WAITLIST_MARKERS):
            _tap_by_texts(
                driver,
                ("Join list", "Join List", "Join the list", "Join"),
                timeout_s=2,
            )
            time.sleep(1.5)
            return

        filled = _fill_first_edit(
            driver,
            zip_code,
            hints=("zip", "postal", "code"),
        )
        if filled:
            _tap_by_texts(
                driver,
                ("Continue", "Next", "Submit", "Check", "Search", "Done"),
                timeout_s=2,
            )
            time.sleep(1.5)

        # Vehicle type (si aparece)
        if vehicle_type:
            _tap_by_texts(
                driver,
                (vehicle_type, vehicle_type.title(), "Sedan", "Car", "SUV", "Truck"),
                timeout_s=1.5,
            )
            _tap_by_texts(driver, ("Continue", "Next", "Done"), timeout_s=1.5)

        _tap_by_texts(
            driver,
            (
                "Join list",
                "Join List",
                "Get started",
                "Continue",
                "Next",
                "I agree",
                "Agree",
            ),
            timeout_s=1.5,
        )
        time.sleep(1.0)


def _adb_bin() -> str:
    import os
    from shutil import which

    home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or ""
    if home:
        candidate = Path(home) / "platform-tools" / "adb.exe"
        if candidate.is_file():
            return str(candidate)
        candidate = Path(home) / "platform-tools" / "adb"
        if candidate.is_file():
            return str(candidate)
    return which("adb") or "adb"


def _adb(args: list[str], *, timeout_s: float = 20) -> subprocess.CompletedProcess[str]:
    settings = get_settings()
    udid = (settings.flex_appium_udid or "").strip()
    cmd = [_adb_bin()]
    if udid:
        cmd += ["-s", udid]
    cmd += args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )


def _preflight_flex_app_launch() -> str | None:
    """Si Flex no se mantiene abierta, devuelve motivo legible (None = OK)."""
    settings = get_settings()
    pkg = settings.flex_app_package
    activity = settings.flex_app_activity
    try:
        path = _adb(["shell", "pm", "path", pkg], timeout_s=15)
        if path.returncode != 0 or "package:" not in (path.stdout or ""):
            return (
                f"Amazon Flex ({pkg}) no está instalada en el dispositivo/emulador. "
                "Instálala desde Play Store o con un APK."
            )

        _adb(["logcat", "-c"], timeout_s=10)
        _adb(["shell", "am", "force-stop", pkg], timeout_s=15)
        time.sleep(0.5)
        component = f"{pkg}/{activity}" if activity else pkg
        start = _adb(
            ["shell", "am", "start", "-n", component]
            if activity
            else ["shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"],
            timeout_s=20,
        )
        time.sleep(4.0)
        pid = _adb(["shell", "pidof", pkg], timeout_s=10)
        if (pid.stdout or "").strip():
            return None

        # App murió: leer pista del logcat
        log = _adb(["logcat", "-d"], timeout_s=25)
        blob = (log.stdout or "") + "\n" + (log.stderr or "")
        if "kHasAES" in blob or "ndk_translation" in blob:
            return (
                "Amazon Flex se instala pero CRASH al abrir en este emulador x86_64: "
                "la app es ARM64 y la traducción NDK exige AES del host "
                "(abort: kHasAES). Solución: usa un teléfono Android real por USB "
                "(adb devices) o un emulador/imagen ARM con AES, no este sdk_gphone64_x86_64."
            )
        if "Fatal signal" in blob or "FATAL EXCEPTION" in blob:
            return (
                f"Amazon Flex CRASH al abrir (am start ok pero proceso muere). "
                f"Salida am: {(start.stdout or start.stderr or '')[:120].strip()} "
                "Revisa logcat; en emuladores x86 suele fallar por libs ARM."
            )
        return (
            f"Amazon Flex no se mantiene abierta tras am start "
            f"(pidof vacío). Activity={activity or 'launcher'}."
        )
    except FileNotFoundError:
        return "adb no está en PATH / ANDROID_HOME. No se pudo preflight de Flex."
    except subprocess.TimeoutExpired:
        return "Timeout en adb al comprobar si Flex abre (emulador lento o colgado)."
    except Exception as exc:
        logger.exception("preflight Flex falló")
        return f"No se pudo preflight Flex: {exc}"


def _humanize_appium_error(msg: str) -> str:
    low = msg.lower()
    if "never started" in low or "cannot start" in low:
        pre = _preflight_flex_app_launch()
        if pre:
            return pre
        return (
            "Appium no pudo arrancar Amazon Flex (la activity no llegó a primer plano). "
            "Si el emulador es x86_64, Flex ARM suele crashear: usa un teléfono real."
        )
    if "connection" in low or "max retries" in low or "refused" in low:
        settings = get_settings()
        return (
            f"No hay Appium en {settings.flex_appium_server_url}. "
            "Ejecuta scripts/start_appium.ps1"
        )
    if "adbexec" in low.replace(" ", "") or "adb exec" in low:
        return (
            f"adb lento/timeout: {msg[:300]}. "
            "Despierta el emulador o sube FLEX_APPIUM_ADB_EXEC_TIMEOUT_MS."
        )
    return msg


def _build_driver():
    """Crea sesión Appium UiAutomator2."""
    settings = get_settings()
    try:
        from appium import webdriver
        from appium.options.android import UiAutomator2Options
    except ImportError as exc:
        raise RuntimeError(
            "Appium client no instalado. Ejecuta: pip install Appium-Python-Client"
        ) from exc

    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.device_name = settings.flex_appium_device_name
    options.automation_name = "UiAutomator2"
    options.app_package = settings.flex_app_package
    if settings.flex_app_activity:
        options.app_activity = settings.flex_app_activity
    options.set_capability("appWaitActivity", "*")
    options.set_capability("appWaitDuration", 60_000)
    options.no_reset = settings.flex_appium_no_reset
    options.new_command_timeout = max(60, settings.flex_appium_timeout_s)
    if settings.flex_appium_udid.strip():
        options.set_capability("udid", settings.flex_appium_udid.strip())
    if settings.flex_app_apk_path:
        apk = Path(settings.flex_app_apk_path)
        if apk.is_file():
            options.app = str(apk.resolve())

    caps_extra = {
        "autoGrantPermissions": True,
        "disableWindowAnimation": True,
        "dontStopAppOnReset": False,
        # Default Appium adbExecTimeout=20s; emuladores suelen necesitar más.
        "adbExecTimeout": max(60_000, settings.flex_appium_adb_exec_timeout_ms),
        "uiautomator2ServerLaunchTimeout": 120_000,
        "uiautomator2ServerInstallTimeout": 120_000,
        "androidDeviceReadyTimeout": 60,
    }
    for k, v in caps_extra.items():
        options.set_capability(k, v)

    url = settings.flex_appium_server_url.rstrip("/")
    driver = webdriver.Remote(f"{url}", options=options)
    driver.implicitly_wait(0.5)
    return driver


def _try_resolve_otp_in_app(driver, *, email: str, password: str) -> tuple[bool, str]:
    """Si la app pide OTP, lo lee de Namecheap IMAP y lo pega."""
    text = _visible_text(driver)
    if not any(m in text for m in OTP_MARKERS):
        return True, "No se pidió OTP en app."

    from datetime import datetime, timezone

    from app.mailbox_imap import fetch_amazon_otp

    since = datetime.now(timezone.utc)
    result = fetch_amazon_otp(
        email_addr=email,
        mailbox_password=password,
        since=since,
    )
    if not result.ok or not result.code:
        return False, result.message or "No se leyó OTP del buzón."

    filled = _fill_first_edit(
        driver,
        result.code,
        hints=("code", "otp", "verification", "passcode"),
    )
    if not filled:
        filled = _fill_first_edit(driver, result.code)
    _tap_by_texts(
        driver,
        ("Continue", "Verify", "Submit", "Create your Amazon account", "Next"),
        timeout_s=3,
    )
    time.sleep(2.0)
    text2 = _visible_text(driver)
    if any(m in text2 for m in OTP_MARKERS):
        return False, f"OTP {result.code} pegado pero la app sigue pidiendo código."
    return True, f"OTP de app aplicado desde buzón Namecheap."


def attempt_flex_region_via_app(
    *,
    email: str,
    password: str,
    zip_code: str | None,
) -> FlexApplyOutcome:
    """Login en app Flex + ZIP. STOP antes de datos personales."""
    settings = get_settings()
    if not settings.flex_appium_enabled:
        return FlexApplyOutcome(
            ok=True,
            status=FlexApplyStatus.NEEDS_APP,
            message=(
                "Appium desactivado. Activa FLEX_APPIUM_ENABLED=true y arranca "
                "Appium + emulador con Amazon Flex instalada."
            ),
            zip_used=zip_code,
        )

    zip_clean = (zip_code or "").strip() or None
    if not zip_clean:
        return FlexApplyOutcome(
            ok=False,
            status=FlexApplyStatus.FAILED,
            message="Falta ZIP en la siembra para aplicar región en la app Flex.",
            zip_used=None,
        )

    try:
        from app.flex_apply.pipeline_log import pipeline_tail, step
    except Exception:
        def step(msg: str, **_k):  # type: ignore
            logger.info(msg)

        def pipeline_tail(_n: int = 12) -> str:  # type: ignore
            return ""

    driver = None
    try:
        step(f"L1b Appium start email={email} zip={zip_clean}")
        _ensure_device_awake()
        pre = _preflight_flex_app_launch()
        if pre:
            step(f"L1b preflight FAIL: {pre}")
            return FlexApplyOutcome(
                ok=False,
                status=FlexApplyStatus.FAILED,
                message=f"{pre} Log: {pipeline_tail(6)}",
                zip_used=zip_clean,
            )
        step("L1b preflight OK")

        _ensure_device_awake()
        driver = _build_driver()
        time.sleep(2.0)
        _ensure_device_awake()
        if not _ensure_flex_foreground(driver):
            step("L1b WARN: Flex no quedó en primer plano tras session")
        _dismiss_permissions(driver)

        logged = _login_amazon_in_app(driver, email=email, password=password)
        if not _ensure_flex_foreground(driver):
            step("L1b WARN: tras login el launcher/home está al frente — relaunch intentado")
        evidence = _save_app_screenshot(driver, email=email, label="after_login")
        step(f"L1b after_login evidence={evidence} logged={logged}")

        # Auth fallido (mensaje en UI) aunque se hayan rellenado los campos.
        auth = _detect_app_outcome(driver, zip_code=zip_clean)
        step(f"L1b detect post-login status={auth.status.value} ok={auth.ok} msg={auth.message[:140]}")
        if not auth.ok and auth.status == FlexApplyStatus.FAILED:
            auth.evidence_path = evidence
            auth.message = f"{auth.message} Log: {pipeline_tail(8)}"
            return auth
        if _still_on_flex_login_gate(driver):
            step("L1b FAIL: sigue en puerta Inicie sesión con Amazon")
            return FlexApplyOutcome(
                ok=False,
                status=FlexApplyStatus.FAILED,
                message=(
                    "Paso 1 falló en la app: sigue el botón "
                    "'Inicie sesión con Amazon' (cuenta no autenticada). "
                    f"Log: {pipeline_tail(8)}"
                ),
                zip_used=zip_clean,
                evidence_path=evidence,
            )

        otp_ok, otp_msg = _try_resolve_otp_in_app(driver, email=email, password=password)
        step(f"L1b OTP app ok={otp_ok} msg={otp_msg[:160]}")
        if not otp_ok:
            return FlexApplyOutcome(
                ok=False,
                status=FlexApplyStatus.NEEDS_VERIFICATION,
                message=(
                    f"App pide verificación. IMAP: {otp_msg} "
                    "Comprueba forward *@dominio → Gmail madre. "
                    f"Log: {pipeline_tail(8)}"
                ),
                zip_used=zip_clean,
                evidence_path=evidence,
                needs_verification=True,
            )

        if not logged:
            early = _detect_app_outcome(driver, zip_code=zip_clean)
            if early.status in (
                FlexApplyStatus.REGION_READY,
                FlexApplyStatus.WAITLISTED,
            ):
                early.evidence_path = evidence
                return early
            if early.status == FlexApplyStatus.NEEDS_VERIFICATION:
                early.message = f"{early.message} | {otp_msg}"
                early.evidence_path = evidence
                return early
            # Último intento: si estamos en home, relaunch + re-login una vez
            if not _ensure_flex_foreground(driver):
                step("L1b reintento login tras relaunch (no logged)")
                logged = _login_amazon_in_app(driver, email=email, password=password)
                evidence = _save_app_screenshot(driver, email=email, label="after_login_retry")
                if logged:
                    early = _detect_app_outcome(driver, zip_code=zip_clean)
                    if early.status in (
                        FlexApplyStatus.REGION_READY,
                        FlexApplyStatus.WAITLISTED,
                    ):
                        early.evidence_path = evidence
                        return early
            return FlexApplyOutcome(
                ok=False,
                status=FlexApplyStatus.FAILED,
                message=(
                    "No se pudo completar login en la app Flex "
                    "(email/pass/botón Iniciar sesión). "
                    "Deja el móvil DESBLOQUEADO y con pantalla encendida; "
                    "revisa selectores / sesión Amazon / OTP. "
                    f"Log: {pipeline_tail(10)}"
                ),
                zip_used=zip_clean,
                evidence_path=evidence,
            )

        early = _detect_app_outcome(driver, zip_code=zip_clean)
        if early.status in (
            FlexApplyStatus.REGION_READY,
            FlexApplyStatus.WAITLISTED,
        ):
            early.evidence_path = evidence
            return early
        if early.status == FlexApplyStatus.NEEDS_VERIFICATION:
            early.message = f"{early.message} | {otp_msg}"
            early.evidence_path = evidence
            return early

        step(f"L1b apply ZIP={zip_clean}")
        _apply_zip_in_app(
            driver,
            zip_clean,
            settings.flex_default_vehicle_type,
        )
        outcome = _detect_app_outcome(driver, zip_code=zip_clean)
        outcome.evidence_path = _save_app_screenshot(
            driver, email=email, label=outcome.status.value
        )
        step(f"L1b final status={outcome.status.value} ok={outcome.ok} msg={outcome.message[:160]}")
        if not outcome.ok:
            outcome.message = f"{outcome.message} Log: {pipeline_tail(8)}"
        return outcome
    except Exception as exc:
        logger.exception("Appium Flex apply failed for %s", email)
        msg = _humanize_appium_error(str(exc))
        step(f"L1b EXCEPTION {msg}")
        return FlexApplyOutcome(
            ok=False,
            status=FlexApplyStatus.FAILED,
            message=f"Error Appium: {msg} Log: {pipeline_tail(8)}",
            zip_used=zip_clean,
        )
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def appium_healthcheck() -> dict:
    """Comprueba si Appium responde (sin abrir Flex)."""
    settings = get_settings()
    import requests

    url = settings.flex_appium_server_url.rstrip("/") + "/status"
    try:
        r = requests.get(url, timeout=5)
        return {
            "ok": r.ok,
            "enabled": settings.flex_appium_enabled,
            "server": settings.flex_appium_server_url,
            "package": settings.flex_app_package,
            "status_code": r.status_code,
            "body": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:300],
        }
    except Exception as exc:
        return {
            "ok": False,
            "enabled": settings.flex_appium_enabled,
            "server": settings.flex_appium_server_url,
            "package": settings.flex_app_package,
            "error": str(exc),
        }
