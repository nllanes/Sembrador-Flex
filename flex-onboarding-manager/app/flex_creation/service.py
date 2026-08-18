"""Paso 1: crear / iniciar sesión REAL en Amazon.com (cuenta usflex).

Reglas:
  - Nunca marcar éxito solo porque la URL “ya no es register”.
  - OTP EN/ES → needs_verification (IMAP).
  - Tras login, PROBAR sesión en /your-account o nav.
  - Pass débil se rechaza antes de abrir Playwright.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.config import get_settings

logger = logging.getLogger(__name__)

REGISTER_URL = (
    "https://www.amazon.com/ap/register?"
    "openid.pape.max_auth_age=0&openid.return_to=https%3A%2F%2Fwww.amazon.com%2F"
    "&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select"
    "&openid.assoc_handle=usflex&openid.mode=checkid_setup"
    "&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select"
    "&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0"
)
SIGNIN_URL = (
    "https://www.amazon.com/ap/signin?"
    "openid.assoc_handle=usflex&openid.mode=checkid_setup"
    "&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0"
)

# Señales de que Amazon pide código (EN + ES)
OTP_TEXT_MARKERS = (
    "enter the code",
    "verification code",
    "one-time password",
    "one time password",
    "verify e-mail",
    "verify email",
    "verify your email",
    "verify your mobile",
    "verify your phone",
    "account recovery",
    "otp",
    "ingresa el código",
    "introduce el código",
    "código de verificación",
    "codigo de verificacion",
    "verificar correo",
    "verifica tu correo",
    "verifica tu e-mail",
    "contraseña de un solo uso",
)

AUTH_ERROR_MARKERS = (
    "there was a problem",
    "your password is incorrect",
    "password is incorrect",
    "we cannot find an account",
    "cannot find an account",
    "email address is already in use",
    "passwords must match",
    "minimum of 6 characters",
    "correo electrónico o la contraseña son incorrectos",
    "la contraseña es incorrecta",
    "no encontramos una cuenta",
    "auth-error-message-box",
)

CAPTCHA_MARKERS = (
    "solve this puzzle",
    "start puzzle",
    "type the characters",
    "enter the characters you see",
    "captcha",
    "robot check",
    "aviso de privacidad",
)


def _is_amazon_puzzle(page) -> bool:
    """Amazon CVF puzzle / CAPTCHA (NO es OTP de email)."""
    text = _page_text(page).lower()
    html = _page_html(page).lower()
    url = page.url.lower()
    if any(
        m in text
        for m in (
            "solve this puzzle",
            "start puzzle",
            "type the characters",
            "enter the characters you see",
            "robot check",
        )
    ):
        return True
    if "captcha" in text and ("puzzle" in text or "characters" in text):
        return True
    if "/ap/cvf" in url and "start puzzle" in (text + html):
        return True
    if 'id="captchacharacters"' in html or "aacb-captcha" in html:
        return True
    return False


def _wait_manual_puzzle(page, *, timeout_s: int = 180) -> bool:
    """Con browser visible: espera a que el humano resuelva el puzzle."""
    try:
        from app.flex_apply.pipeline_log import step
    except Exception:
        def step(msg: str, **_k):  # type: ignore
            logger.info(msg)

    import time as _time

    settings = get_settings()
    if settings.flex_creation_headless:
        step("L0 CAPTCHA/puzzle en headless — no se puede resolver a mano")
        return False

    step(
        f"L0 CAPTCHA puzzle — resuélvelo en la ventana del browser "
        f"(esperando hasta {timeout_s}s)"
    )
    deadline = _time.time() + max(30, timeout_s)
    poll = 0
    while _time.time() < deadline:
        poll += 1
        page.wait_for_timeout(2000)
        if not _is_amazon_puzzle(page):
            step(f"L0 puzzle resuelto (poll#{poll}) url={page.url[:100]}")
            return True
        if poll == 1 or poll % 15 == 0:
            step(f"L0 esperando puzzle manual… left={int(deadline - _time.time())}s")
    step("L0 TIMEOUT esperando puzzle manual")
    return False


@dataclass
class CreationOutcome:
    ok: bool
    message: str
    needs_verification: bool = False
    used_signin: bool = False


def validate_amazon_password(password: str) -> str | None:
    """Devuelve motivo de rechazo o None si es aceptable para Amazon."""
    pw = password or ""
    if len(pw) < 6:
        return "La contraseña Amazon debe tener al menos 6 caracteres."
    if len(pw) < 8:
        return (
            "Usa una contraseña Amazon de al menos 8 caracteres "
            "(Amazon a menudo rechaza claves cortas/débiles)."
        )
    if pw.isdigit() or pw.isalpha():
        return (
            "La contraseña Amazon debe mezclar letras y números "
            "(ej. FlexMiami01!)."
        )
    if pw.lower() in {"password", "amazon", "12345678", "qwerty12"}:
        return "Contraseña demasiado común; elige otra."
    return None


def _display_name(full_name: str) -> str:
    if " · " in full_name:
        label = full_name.split(" · ", 1)[1].strip()
        return label.split(" #")[0].strip() or "Flex Driver"
    return full_name.strip() or "Flex Driver"


def _page_text(page) -> str:
    try:
        return page.inner_text("body")[:10000]
    except Exception:
        return ""


def _page_html(page) -> str:
    try:
        return page.content()[:20000]
    except Exception:
        return ""


def _on_auth_flow(url: str) -> bool:
    u = url.lower()
    return any(
        x in u
        for x in (
            "/ap/signin",
            "/ap/register",
            "/ap/cvf",
            "/ax/claim",
            "/ap/challenge",
            "/ap/mfa",
            "ap/cnep",
        )
    )


def _is_new_account_claim(page) -> bool:
    """Pantalla 'Looks like you're new to Amazon' / Proceed to create an account."""
    text = _page_text(page).lower()
    url = page.url.lower()
    if "looks like you're new" in text or "lets create an account using your email" in text:
        return True
    if "let's create an account using your email" in text:
        return True
    if "proceed to create an account" in text:
        return True
    if "/ax/claim" in url and "claimtype=email" in url.replace(" ", ""):
        # claim/intent sin campo código = crear cuenta, no OTP
        html = _page_html(page).lower()
        if 'name="code"' not in html and "cvf-input-code" not in html:
            return True
    return False


def _looks_like_otp(page) -> bool:
    """Solo OTP real (campo código), no claim ni puzzle CAPTCHA."""
    if _is_new_account_claim(page) or _is_amazon_puzzle(page):
        return False
    text = _page_text(page).lower()
    url = page.url.lower()
    html = _page_html(page).lower()
    if 'name="code"' in html or "cvf-input-code" in html or 'name="otpCode"' in html:
        return True
    if any(m in text for m in OTP_TEXT_MARKERS):
        strong = (
            "enter the code",
            "verification code",
            "one-time password",
            "one time password",
            "código de verificación",
            "codigo de verificacion",
            "ingresa el código",
            "introduce el código",
        )
        if any(m in text for m in strong):
            return True
    # CVF con OTP en URL — no el /request genérico del puzzle
    if "/ap/cvf" in url and ("otp" in url or "transactionapproval" in url):
        return True
    return False


def _handle_new_account_claim(page, *, name: str, password: str) -> None:
    """Continúa el claim → formulario de registro (nombre/pass)."""
    logger.info("Amazon claim: new email → Proceed to create an account")
    clicked = _click_first(
        page,
        (
            'input[aria-labelledby*="create"]',
            'input[type="submit"]',
            'button:has-text("Proceed to create an account")',
            'a:has-text("Proceed to create an account")',
            "#continue",
            'input#continue',
        ),
    )
    if not clicked:
        # Playwright text click
        try:
            page.get_by_role("button", name=re.compile(r"proceed to create", re.I)).click(
                timeout=5000
            )
            clicked = True
        except Exception:
            try:
                page.locator("text=Proceed to create an account").first.click(timeout=5000)
                clicked = True
            except Exception:
                pass
    page.wait_for_timeout(1500)
    # Rellenar registro si aparecen campos
    _set_input(page, ('input[name="customerName"]', "#ap_customer_name"), name)
    _set_input(page, ('input[name="password"]', "#ap_password"), password)
    _set_input(page, ('input[name="passwordCheck"]', "#ap_password_check"), password)
    _click_first(
        page,
        (
            'input#continue',
            'input[type="submit"]',
            "#continue",
            'button[type="submit"]',
            'input#auth-create-account-button',
        ),
    )
    try:
        page.wait_for_load_state("domcontentloaded", timeout=60_000)
    except Exception:
        pass
    page.wait_for_timeout(2000)


def _extract_auth_error(page) -> str:
    for sel in (
        "#auth-error-message-box",
        "#auth-error-message-box .a-list-item",
        ".a-alert-content",
        "#auth-warning-message-box",
        "[class*='auth-error']",
    ):
        loc = page.locator(sel)
        if loc.count():
            try:
                t = loc.first.inner_text().strip()
                if t:
                    return t[:300]
            except Exception:
                continue
    text = _page_text(page).lower()
    for m in AUTH_ERROR_MARKERS:
        if m in text and m != "auth-error-message-box":
            return f"Amazon rechazó el login/registro ({m})."
    return ""


def _detect_outcome(page, *, used_signin: bool) -> CreationOutcome:
    """Clasifica la página actual. NO asume éxito por defecto."""
    text = _page_text(page).lower()
    url = page.url.lower()
    html = _page_html(page).lower()

    # Puzzle/CAPTCHA ANTES que OTP: /ap/cvf/request a menudo es puzzle, no código
    if _is_amazon_puzzle(page):
        return CreationOutcome(
            ok=False,
            used_signin=used_signin,
            message=(
                "Amazon mostró CAPTCHA/puzzle ('Solve this puzzle'). "
                "No es OTP de email."
            ),
        )

    if _looks_like_otp(page):
        return CreationOutcome(
            ok=True,
            needs_verification=True,
            used_signin=used_signin,
            message="Amazon pide verificación por email/SMS (OTP).",
        )

    err = _extract_auth_error(page)
    if err or "auth-error-message-box" in html:
        return CreationOutcome(
            ok=False,
            used_signin=used_signin,
            message=err or "Amazon rechazó el registro/login (revisa email/contraseña).",
        )

    if any(
        m in text
        for m in (
            "already have an account",
            "account already exists",
            "email address already in use",
            "ya tienes una cuenta",
            "ya existe una cuenta",
        )
    ):
        return CreationOutcome(
            ok=False,
            used_signin=used_signin,
            message="El email ya existe en Amazon; se intentará iniciar sesión.",
        )

    # Seguir en formularios de auth sin OTP → aún no hay sesión
    if _on_auth_flow(url) and not _looks_like_otp(page):
        if "password" in text or "contraseña" in text or "ap_password" in html:
            return CreationOutcome(
                ok=False,
                used_signin=used_signin,
                message=(
                    "Amazon sigue en la pantalla de login/registro "
                    "(sesión no establecida)."
                ),
            )
        return CreationOutcome(
            ok=False,
            used_signin=used_signin,
            message="Amazon sigue en el flujo de autenticación.",
        )

    # Éxito solo con señales positivas de sesión (se confirma luego con prove)
    signed_hints = (
        "your account",
        "account & lists",
        "hello,",
        "hola,",
        "sign out",
        "cerrar sesión",
        "returns & orders",
        "pedidos",
    )
    if any(h in text for h in signed_hints) and "sign in" not in url:
        return CreationOutcome(
            ok=True,
            used_signin=used_signin,
            message="Señales de sesión Amazon presentes; verificando…",
        )

    # Landing genérica sin auth → dudoso; no OK todavía
    return CreationOutcome(
        ok=False,
        used_signin=used_signin,
        message="No se pudo confirmar el registro/login en Amazon.",
    )


def _prove_signed_in(page, *, used_signin: bool) -> CreationOutcome:
    """Prueba dura: visitar Your Account y exigir no estar en /ap/signin."""
    try:
        page.goto(
            "https://www.amazon.com/gp/css/homepage.html?ref_=nav_youraccount_btn",
            wait_until="domcontentloaded",
            timeout=45_000,
        )
        page.wait_for_timeout(1500)
    except Exception as exc:
        logger.info("prove_signed_in goto failed: %s", exc)

    url = page.url.lower()
    text = _page_text(page).lower()

    if _looks_like_otp(page):
        return CreationOutcome(
            ok=True,
            needs_verification=True,
            used_signin=used_signin,
            message="Amazon pide OTP al verificar la sesión.",
        )

    if _on_auth_flow(url) or "ap/signin" in url:
        err = _extract_auth_error(page)
        return CreationOutcome(
            ok=False,
            used_signin=used_signin,
            message=err
            or (
                "No hay sesión Amazon activa (redirigió a login). "
                "La cuenta no se creó o la contraseña es incorrecta."
            ),
        )

    # Nav: si sigue pidiendo Sign in de forma prominente
    if re.search(r"\bhello,\s*sign in\b", text) or "identifícate" in text and "hola" in text:
        # A veces el texto aparece en footer; exigir también falta de account links
        if "your account" not in text and "tu cuenta" not in text:
            return CreationOutcome(
                ok=False,
                used_signin=used_signin,
                message="Amazon muestra 'Sign in': la cuenta no quedó autenticada.",
            )

    positive = any(
        x in text
        for x in (
            "your account",
            "tu cuenta",
            "orders",
            "pedidos",
            "login & security",
            "iniciar sesión y seguridad",
            "prime",
            "lists",
        )
    )
    if positive or "amazon.com" in url and not _on_auth_flow(url):
        return CreationOutcome(
            ok=True,
            used_signin=used_signin,
            message="Cuenta Amazon autenticada (sesión verificada).",
        )

    return CreationOutcome(
        ok=False,
        used_signin=used_signin,
        message="No se pudo probar la sesión Amazon tras el login.",
    )


def _set_input(page, selectors: tuple[str, ...], value: str) -> bool:
    for sel in selectors:
        loc = page.locator(sel)
        if loc.count():
            try:
                loc.first.fill(value)
                return True
            except Exception:
                continue
    return False


def _click_first(page, selectors: tuple[str, ...]) -> bool:
    for sel in selectors:
        loc = page.locator(sel)
        if loc.count():
            try:
                loc.first.click()
                return True
            except Exception:
                continue
    return False


def _fill_register(page, *, name: str, email: str, password: str) -> None:
    page.goto(REGISTER_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    _set_input(page, ('input[name="customerName"]', "#ap_customer_name"), name)
    _set_input(page, ('input[name="email"]', "#ap_email", 'input[name="email"]'), email)
    _set_input(page, ('input[name="password"]', "#ap_password"), password)
    _set_input(page, ('input[name="passwordCheck"]', "#ap_password_check"), password)
    _click_first(
        page,
        (
            'input#continue',
            'input[type="submit"]',
            "#continue",
            'button[type="submit"]',
        ),
    )
    try:
        page.wait_for_load_state("domcontentloaded", timeout=60_000)
    except Exception:
        pass
    page.wait_for_timeout(2000)


def _fill_signin(page, *, email: str, password: str) -> None:
    page.goto(SIGNIN_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    _set_input(page, ('input[name="email"]', "#ap_email", "#ap_email_login"), email)
    _click_first(
        page,
        (
            "#continue",
            'input#continue',
            "#ap_login_submit",
            'input[type="submit"]',
            'button[type="submit"]',
        ),
    )
    page.wait_for_timeout(1500)
    # A veces pide solo email otra vez / claim
    if _looks_like_otp(page):
        return
    _set_input(page, ('input[name="password"]', "#ap_password"), password)
    _click_first(
        page,
        (
            "input#signInSubmit",
            "#signInSubmit",
            'input[type="submit"]',
            'button[type="submit"]',
        ),
    )
    try:
        page.wait_for_load_state("domcontentloaded", timeout=60_000)
    except Exception:
        pass
    page.wait_for_timeout(2000)


def establish_amazon_identity(page, *, name: str, email: str, password: str) -> CreationOutcome:
    """Register / Sign-in / claim 'new to Amazon' → OTP si aplica → prove sesión.

    No resuelve OTP aquí; el caller (flex_apply) usa IMAP y vuelve a proveer.
    """
    try:
        from app.flex_apply.pipeline_log import step
    except Exception:
        def step(msg: str, **_k):  # type: ignore
            logger.info(msg)

    weak = validate_amazon_password(password)
    if weak:
        step(f"L0 BLOCK pass: {weak}")
        return CreationOutcome(ok=False, message=weak)

    step(f"L0 register → {email}")
    _fill_register(page, name=name, email=email, password=password)
    step(f"L0 after register url={page.url[:120]}")

    if _is_new_account_claim(page):
        step("L0 claim: Looks like you're new → Proceed to create an account")
        _handle_new_account_claim(page, name=name, password=password)
        step(f"L0 after claim url={page.url[:120]}")

    outcome = _detect_outcome(page, used_signin=False)
    body = _page_text(page)
    step(f"L0 detect after register: ok={outcome.ok} otp={outcome.needs_verification} msg={outcome.message[:160]}")

    need_signin = (
        not outcome.ok
        or outcome.message.startswith("El email ya existe")
        or bool(
            re.search(
                r"already.*account|account.*exists|cannot create an account|"
                r"email address already|ya existe",
                body,
                re.I,
            )
        )
    )
    if need_signin and not outcome.needs_verification:
        step(f"L0 signin → {email}")
        _fill_signin(page, email=email, password=password)
        step(f"L0 after signin url={page.url[:120]}")

        if _is_new_account_claim(page):
            step("L0 claim tras signin: email nuevo → crear cuenta")
            _handle_new_account_claim(page, name=name, password=password)
            step(f"L0 after claim2 url={page.url[:120]}")

        outcome = _detect_outcome(page, used_signin=True)
        step(
            f"L0 detect after signin: ok={outcome.ok} otp={outcome.needs_verification} "
            f"msg={outcome.message[:160]}"
        )

    # A veces el claim aparece sin pasar por need_signin
    if _is_new_account_claim(page):
        step("L0 claim final pass")
        _handle_new_account_claim(page, name=name, password=password)
        outcome = _detect_outcome(page, used_signin=outcome.used_signin)
        step(f"L0 detect after claim final: ok={outcome.ok} otp={outcome.needs_verification}")

    # CAPTCHA/puzzle: con headless=false espera resolución manual
    if _is_amazon_puzzle(page) or (
        not outcome.ok and "CAPTCHA" in outcome.message.upper()
    ):
        if _wait_manual_puzzle(page, timeout_s=180):
            outcome = _detect_outcome(page, used_signin=outcome.used_signin)
            step(
                f"L0 after puzzle: ok={outcome.ok} otp={outcome.needs_verification} "
                f"msg={outcome.message[:160]}"
            )
        else:
            return CreationOutcome(
                ok=False,
                used_signin=outcome.used_signin,
                message=(
                    "Amazon mostró CAPTCHA/puzzle ('Solve this puzzle'). "
                    "Resuélvelo en la ventana del browser y vuelve a Sembrar "
                    "(o deja headless=false y hazlo cuando aparezca)."
                ),
            )

    if outcome.needs_verification:
        step("L0 → necesita OTP real (código email/SMS)")
        return outcome

    if not outcome.ok:
        step(f"L0 FAIL before prove: {outcome.message}")
        return outcome

    step("L0 prove sesión (Your Account)")
    proved = _prove_signed_in(page, used_signin=outcome.used_signin)
    step(f"L0 prove: ok={proved.ok} otp={proved.needs_verification} msg={proved.message[:160]}")
    return proved


def attempt_amazon_account_creation(
    *,
    email: str,
    password: str,
    full_name: str,
) -> CreationOutcome:
    """Abre Amazon.com y registra o inicia sesión con email + contraseña de la siembra."""
    settings = get_settings()
    if not settings.flex_creation_enabled:
        return CreationOutcome(
            ok=True,
            message="Creación automática desactivada (solo actualización CRM).",
        )

    weak = validate_amazon_password(password)
    if weak:
        return CreationOutcome(ok=False, message=weak)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return CreationOutcome(
            ok=False,
            message=(
                "Playwright no instalado. Ejecuta: "
                "python -m pip install playwright && python -m playwright install chromium"
            ),
        )

    name = _display_name(full_name)
    timeout = settings.flex_creation_timeout_ms

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=settings.flex_creation_headless)
            context = browser.new_context(
                locale="en-US",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            page.set_default_timeout(timeout)
            outcome = establish_amazon_identity(
                page, name=name, email=email, password=password
            )
            browser.close()
            return outcome
    except Exception as exc:
        logger.exception("Amazon creation failed for %s", email)
        return CreationOutcome(ok=False, message=f"Error de automatización: {exc}")
