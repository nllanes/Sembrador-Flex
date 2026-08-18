"""Automatiza hasta que Flex acepte la región o ponga en lista.

Alcance (STOP antes de datos personales):
  1. Crear / iniciar sesión en amazon.com (cuenta usflex)
  2. Entrar a flex.amazon.com
  3. Intentar ZIP / región de la siembra
  4. Detectar: región OK | join list | necesita app | OTP | fallo

NO sube licencia, SSN, seguro ni banco.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.config import get_settings
from app.flex_creation import service as identity

logger = logging.getLogger(__name__)

EVIDENCE_DIR = Path(__file__).resolve().parent.parent.parent / "var" / "flex_apply"


class FlexApplyStatus(str, Enum):
    """Resultado del sembrado hasta región (capa L0+L1)."""

    REGION_READY = "region_ready"  # Flex acepta seguir (antes de docs)
    WAITLISTED = "waitlisted"  # Join list / sin cupo en ZIP
    NEEDS_APP = "needs_app"  # Web solo pide app; región va en app móvil
    NEEDS_VERIFICATION = "needs_verification"  # OTP / email
    IDENTITY_OK = "identity_ok"  # Cuenta Amazon OK, región no confirmada en web
    FAILED = "failed"


@dataclass
class FlexApplyOutcome:
    ok: bool
    status: FlexApplyStatus
    message: str
    zip_used: str | None = None
    evidence_path: str | None = None
    page_url: str | None = None
    needs_verification: bool = False


def _ensure_evidence_dir() -> Path:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    return EVIDENCE_DIR


def _safe_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", value)[:80]


def _save_evidence(page, *, email: str, label: str) -> str | None:
    try:
        folder = _ensure_evidence_dir()
        stem = f"{_safe_slug(email)}_{_safe_slug(label)}"
        png = folder / f"{stem}.png"
        txt = folder / f"{stem}.txt"
        page.screenshot(path=str(png), full_page=True)
        body = identity._page_text(page)
        txt.write_text(
            f"url={page.url}\n\n{body[:6000]}",
            encoding="utf-8",
            errors="ignore",
        )
        return str(png)
    except Exception as exc:
        logger.info("Evidence skip: %s", exc)
        return None


def _detect_flex_region_outcome(page, *, zip_code: str | None) -> FlexApplyOutcome:
    """Inspecciona la página Flex y decide región / lista / app / docs."""
    text = identity._page_text(page).lower()
    url = page.url.lower()
    zip_used = zip_code

    # Páginas de marketing / download: NO son onboarding real
    marketing_urls = (
        "flex.amazon.com/download-app",
        "flex.amazon.com/get-started",
        "flex.amazon.com/recruiting-cities",
        "flex.amazon.com/faq",
        "flex.amazon.com/why-flex",
        "flex.amazon.com/lets-drive",
        "flex.amazon.com/safety",
    )
    on_marketing = any(u in url for u in marketing_urls) or url.rstrip("/") in (
        "https://flex.amazon.com",
        "https://www.flex.amazon.com",
    )
    if on_marketing or "download the app" in text or "scan the qr" in text:
        # Aunque el FAQ mencione "driver's license", no significa que haya cuenta/onboarding
        if any(
            m in text
            for m in (
                "join list",
                "join the list",
                "interest list",
                "not currently recruiting",
                "not actively recruiting",
            )
        ):
            return FlexApplyOutcome(
                ok=True,
                status=FlexApplyStatus.WAITLISTED,
                message=(
                    f"Amazon muestra lista de interés"
                    f"{f' para ZIP {zip_code}' if zip_code else ''}."
                ),
                zip_used=zip_used,
                page_url=page.url,
            )
        return FlexApplyOutcome(
            ok=True,
            status=FlexApplyStatus.NEEDS_APP,
            message=(
                "Solo se abrió la web de Flex (download/marketing). "
                "Eso NO confirma cuenta ni región. Hay que completar login+ZIP en la app."
            ),
            zip_used=zip_used,
            page_url=page.url,
        )

    # Datos personales en flujo real de app/onboarding (no FAQ)
    personal_markers = (
        "upload your license",
        "take a photo of your",
        "scan your license",
        "enter your social security",
        "social security number",
        "routing number",
        "account number",
        "background check consent",
    )
    if any(m in text for m in personal_markers):
        return FlexApplyOutcome(
            ok=True,
            status=FlexApplyStatus.REGION_READY,
            message=(
                "Flex aceptó la región / onboarding. "
                "Parado antes de datos personales (licencia/SSN/banco)."
            ),
            zip_used=zip_used,
            page_url=page.url,
        )

    waitlist_markers = (
        "join list",
        "join the list",
        "interest list",
        "join our interest list",
        "not currently recruiting",
        "not actively recruiting",
        "we'll notify you",
        "we will notify you",
        "spots become available",
        "no opportunities available",
        "waitlist",
    )
    if any(m in text for m in waitlist_markers):
        return FlexApplyOutcome(
            ok=True,
            status=FlexApplyStatus.WAITLISTED,
            message=(
                f"Amazon puso la cuenta en lista de interés"
                f"{f' para ZIP {zip_code}' if zip_code else ''} "
                "(sin cupo ahora; avisan por email)."
            ),
            zip_used=zip_used,
            page_url=page.url,
        )

    region_ok_markers = (
        "select a service area",
        "choose your region",
        "continue onboarding",
        "complete your profile",
        "get started delivering",
        "you're almost ready",
        "start onboarding",
        "delivery partner application",
    )
    if any(m in text for m in region_ok_markers):
        return FlexApplyOutcome(
            ok=True,
            status=FlexApplyStatus.REGION_READY,
            message=(
                f"Región/service area lista"
                f"{f' (ZIP {zip_code})' if zip_code else ''}. "
                "Listo para que otra persona suba licencia y documentos."
            ),
            zip_used=zip_used,
            page_url=page.url,
        )

    app_markers = (
        "download the app",
        "download the amazon flex app",
        "app store",
        "google play",
        "get the app",
        "sign up in the app",
        "onboarding takes place in the amazon flex app",
    )
    if any(m in text for m in app_markers) or "download-app" in url:
        return FlexApplyOutcome(
            ok=True,
            status=FlexApplyStatus.NEEDS_APP,
            message=(
                "Cuenta Amazon OK. El ZIP/región se completa en la app Amazon Flex "
                "(la web solo pide descargar la app). Sembrado de identidad listo; "
                "falta apply de región en app."
            ),
            zip_used=zip_used,
            page_url=page.url,
        )

    return FlexApplyOutcome(
        ok=True,
        status=FlexApplyStatus.IDENTITY_OK,
        message=(
            "Cuenta Amazon creada/sesión OK. "
            "No se pudo confirmar región en web; revisa flex.amazon.com o la app con el ZIP."
        ),
        zip_used=zip_used,
        page_url=page.url,
    )


def _try_fill_zip(page, zip_code: str) -> bool:
    """Intenta rellenar un campo ZIP en la página actual."""
    selectors = (
        'input[name*="zip" i]',
        'input[id*="zip" i]',
        'input[placeholder*="zip" i]',
        'input[aria-label*="zip" i]',
        'input[name*="postal" i]',
        'input[placeholder*="postal" i]',
        'input[type="tel"]',
        'input[inputmode="numeric"]',
    )
    for sel in selectors:
        loc = page.locator(sel)
        if loc.count():
            try:
                loc.first.fill(zip_code)
                identity._click_first(
                    page,
                    (
                        'button:has-text("Continue")',
                        'button:has-text("Submit")',
                        'button:has-text("Check")',
                        'button:has-text("Search")',
                        'button:has-text("Join")',
                        'input[type="submit"]',
                        "#continue",
                    ),
                )
                page.wait_for_timeout(1500)
                return True
            except Exception:
                continue
    return False


def _try_join_list(page) -> bool:
    return identity._click_first(
        page,
        (
            'button:has-text("Join list")',
            'button:has-text("Join List")',
            'a:has-text("Join list")',
            'a:has-text("Join List")',
            'button:has-text("Join the list")',
            'a:has-text("Join the interest list")',
        ),
    )


def _explore_flex_web(page, *, zip_code: str | None) -> FlexApplyOutcome:
    """Navega flex.amazon.com e intenta apply de región por ZIP."""
    urls = (
        "https://flex.amazon.com/",
        "https://flex.amazon.com/get-started",
        "https://flex.amazon.com/download-app",
        "https://flex.amazon.com/recruiting-cities",
    )
    last = FlexApplyOutcome(
        ok=True,
        status=FlexApplyStatus.IDENTITY_OK,
        message="Sin páginas Flex exploradas.",
        zip_used=zip_code,
    )

    for url in urls:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(1200)
        except Exception as exc:
            logger.info("Flex URL skip %s: %s", url, exc)
            continue

        # Clicks típicos de CTA
        identity._click_first(
            page,
            (
                'a:has-text("Deliver Now")',
                'button:has-text("Deliver Now")',
                'a:has-text("Get started")',
                'button:has-text("Get started")',
                'a:has-text("Let\'s Drive")',
                'a:has-text("Sign up")',
            ),
        )
        page.wait_for_timeout(1000)

        if zip_code:
            filled = _try_fill_zip(page, zip_code)
            if filled:
                page.wait_for_timeout(1500)
            _try_join_list(page)
            page.wait_for_timeout(800)

        last = _detect_flex_region_outcome(page, zip_code=zip_code)
        evidence = _save_evidence(page, email=zip_code or "flex", label=last.status.value)
        last.evidence_path = evidence

        # Si ya tenemos un resultado accionable, paramos
        if last.status in (
            FlexApplyStatus.REGION_READY,
            FlexApplyStatus.WAITLISTED,
            FlexApplyStatus.NEEDS_APP,
        ):
            return last

    return last


def attempt_flex_region_apply(
    *,
    email: str,
    password: str,
    full_name: str,
    zip_code: str | None = None,
) -> FlexApplyOutcome:
    """Cuenta Amazon + intento de región/ZIP. Para antes de datos personales."""
    settings = get_settings()
    if not settings.flex_creation_enabled:
        return FlexApplyOutcome(
            ok=True,
            status=FlexApplyStatus.IDENTITY_OK,
            message="Creación automática desactivada (solo actualización CRM).",
            zip_used=zip_code,
        )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return FlexApplyOutcome(
            ok=False,
            status=FlexApplyStatus.FAILED,
            message=(
                "Playwright no instalado. Ejecuta: "
                "python -m pip install playwright && python -m playwright install chromium"
            ),
            zip_used=zip_code,
        )

    zip_clean = (zip_code or "").strip() or None
    name = identity._display_name(full_name)
    timeout = settings.flex_creation_timeout_ms

    from app.flex_apply.pipeline_log import begin_pipeline_log, pipeline_tail, step

    begin_pipeline_log(email)
    step(f"start zip={zip_clean} name={name}")

    weak = identity.validate_amazon_password(password)
    if weak:
        step(f"BLOCK pass: {weak}")
        return FlexApplyOutcome(
            ok=False,
            status=FlexApplyStatus.FAILED,
            message=f"Paso 1 (cuenta Amazon): {weak}",
            zip_used=zip_clean,
        )

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

            # --- L0: identidad Amazon (crear/login + prueba de sesión) ---
            step("L0 begin establish_amazon_identity")
            id_outcome = identity.establish_amazon_identity(
                page, name=name, email=email, password=password
            )

            if id_outcome.needs_verification:
                from app.flex_apply.otp_flow import try_resolve_otp_with_mailbox

                step("L0 OTP required → IMAP")
                otp_ok, otp_msg = try_resolve_otp_with_mailbox(
                    page, email=email, mailbox_password=password
                )
                step(f"L0 OTP result ok={otp_ok} msg={otp_msg[:200]}")
                if not otp_ok:
                    evidence = _save_evidence(page, email=email, label="needs_otp")
                    browser.close()
                    return FlexApplyOutcome(
                        ok=False,
                        status=FlexApplyStatus.NEEDS_VERIFICATION,
                        message=(
                            "Paso 1: Amazon pide OTP pero no se pudo aplicar. "
                            f"{otp_msg} "
                            "Comprueba forward *@cosecha.it.com → Gmail madre. "
                            f"Log: {pipeline_tail(8)}"
                        ),
                        zip_used=zip_clean,
                        evidence_path=evidence,
                        page_url=page.url,
                        needs_verification=True,
                    )
                id_outcome = identity._prove_signed_in(
                    page, used_signin=id_outcome.used_signin
                )
                step(f"L0 after OTP prove ok={id_outcome.ok} otp={id_outcome.needs_verification}")
                if id_outcome.needs_verification:
                    evidence = _save_evidence(page, email=email, label="otp_still")
                    browser.close()
                    return FlexApplyOutcome(
                        ok=False,
                        status=FlexApplyStatus.NEEDS_VERIFICATION,
                        message=(
                            f"Paso 1: OTP aplicado ({otp_msg}) pero Amazon sigue pidiendo código. "
                            f"Log: {pipeline_tail(6)}"
                        ),
                        zip_used=zip_clean,
                        evidence_path=evidence,
                        page_url=page.url,
                        needs_verification=True,
                    )

            if not id_outcome.ok:
                evidence = _save_evidence(page, email=email, label="identity_fail")
                browser.close()
                step(f"L0 FAIL {id_outcome.message}")
                return FlexApplyOutcome(
                    ok=False,
                    status=FlexApplyStatus.FAILED,
                    message=(
                        f"Paso 1 (cuenta Amazon) falló: {id_outcome.message} "
                        f"Log: {pipeline_tail(8)}"
                    ),
                    zip_used=zip_clean,
                    evidence_path=evidence,
                    page_url=page.url,
                )

            step(f"L0 OK — {id_outcome.message}")

            # --- L1: región / ZIP en Flex web ---
            step(f"L1 web Flex zip={zip_clean}")
            flex_outcome = _explore_flex_web(page, zip_code=zip_clean)
            if not flex_outcome.evidence_path:
                flex_outcome.evidence_path = _save_evidence(
                    page, email=email, label=flex_outcome.status.value
                )
            if not zip_clean and flex_outcome.status == FlexApplyStatus.NEEDS_APP:
                flex_outcome.message += (
                    " Tip: guarda un ZIP en la siembra para mapear la región."
                )
            step(
                f"L1 result status={flex_outcome.status.value} "
                f"msg={flex_outcome.message[:160]}"
            )

            browser.close()

            # Si web ya resolvió región/lista, listo
            if flex_outcome.status in (
                FlexApplyStatus.REGION_READY,
                FlexApplyStatus.WAITLISTED,
            ):
                step("DONE via web region/list")
                return flex_outcome

            # --- L1b: región en app Android (Appium) — solo con L0 OK ---
            if settings.flex_appium_enabled and zip_clean:
                from app.flex_apply.appium_region import attempt_flex_region_via_app

                step("L1b Appium begin (cuenta Amazon ya autenticada en web)")
                app_outcome = attempt_flex_region_via_app(
                    email=email,
                    password=password,
                    zip_code=zip_clean,
                )
                step(
                    f"L1b Appium status={app_outcome.status.value} "
                    f"ok={app_outcome.ok} msg={app_outcome.message[:200]}"
                )
                if app_outcome.status in (
                    FlexApplyStatus.REGION_READY,
                    FlexApplyStatus.WAITLISTED,
                    FlexApplyStatus.NEEDS_VERIFICATION,
                ):
                    return app_outcome
                if not app_outcome.ok and app_outcome.status == FlexApplyStatus.FAILED:
                    app_outcome.message = (
                        f"{flex_outcome.message} | Appium: {app_outcome.message} "
                        f"Log: {pipeline_tail(10)}"
                    )
                    return app_outcome
                if app_outcome.status != FlexApplyStatus.NEEDS_APP:
                    return app_outcome
                flex_outcome.message = (
                    f"{flex_outcome.message} | App: {app_outcome.message}"
                )
                return flex_outcome

            if settings.flex_appium_enabled and not zip_clean:
                flex_outcome.message += (
                    " Appium listo, pero falta ZIP en la siembra."
                )

            flex_outcome.message = f"{flex_outcome.message} Log: {pipeline_tail(6)}"
            return flex_outcome
    except Exception as exc:
        logger.exception("Flex apply failed for %s", email)
        step(f"EXCEPTION {exc}")
        return FlexApplyOutcome(
            ok=False,
            status=FlexApplyStatus.FAILED,
            message=f"Error de automatización: {exc} Log: {pipeline_tail(8)}",
            zip_used=zip_clean,
        )
