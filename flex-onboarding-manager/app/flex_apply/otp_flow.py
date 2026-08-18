"""Helpers para detectar y rellenar OTP en páginas Amazon (Playwright)."""

from __future__ import annotations

import logging
import re

from app.flex_creation import service as identity
from app.mailbox_imap import fetch_amazon_otp

logger = logging.getLogger(__name__)


def page_needs_otp(page) -> bool:
    from app.flex_creation.service import _looks_like_otp

    return _looks_like_otp(page)


def submit_otp_on_page(page, code: str) -> bool:
    """Rellena el código OTP y continúa."""
    filled = identity._set_input(
        page,
        (
            'input[name="code"]',
            'input[name="otpCode"]',
            "#cvf-input-code",
            'input[name="cvf_captcha_input"]',
            'input[type="tel"]',
            'input[autocomplete="one-time-code"]',
            'input[name="email.otp.code"]',
            'input[name="otpCode"]',
        ),
        code,
    )
    if not filled:
        # último recurso: primer input visible numérico
        for sel in ("input[type='text']", "input"):
            loc = page.locator(sel)
            if loc.count():
                try:
                    loc.first.fill(code)
                    filled = True
                    break
                except Exception:
                    continue
    clicked = identity._click_first(
        page,
        (
            'input[type="submit"]',
            'button[type="submit"]',
            "#cvf-submit-otp-button",
            'input#cvf-submit-otp-button',
            'button:has-text("Create your Amazon account")',
            'button:has-text("Continue")',
            'button:has-text("Continuar")',
            'button:has-text("Verify")',
            'button:has-text("Verificar")',
            'input[aria-labelledby*="cvf"]',
        ),
    )
    page.wait_for_timeout(2000)
    return filled and clicked


def try_resolve_otp_with_mailbox(
    page,
    *,
    email: str,
    mailbox_password: str,
) -> tuple[bool, str]:
    """Si la página pide OTP, lee IMAP (Gmail madre / buzón) y lo envía."""
    try:
        from app.flex_apply.pipeline_log import step
    except Exception:
        def step(msg: str, **_k):  # type: ignore
            logger.info(msg)

    if not page_needs_otp(page):
        step(f"OTP skip: página no pide código url={page.url[:100]}")
        return True, "No se pidió OTP."

    step(f"OTP page detectada url={page.url[:120]} → IMAP")
    from datetime import datetime, timezone

    since = datetime.now(timezone.utc)
    result = fetch_amazon_otp(
        email_addr=email,
        mailbox_password=mailbox_password,
        since=since,
    )
    if not result.ok or not result.code:
        tip = (
            " Revisa: 1) forward Namecheap *@dominio → Gmail madre, "
            "2) App Password IMAP, 3) carpeta Inbox (no Spam)."
        )
        msg = (result.message or "No se pudo leer OTP del buzón.") + tip
        step(f"OTP IMAP FAIL: {msg[:200]}")
        return False, msg

    step(f"OTP IMAP OK code={result.code} subject={result.subject or '?'}")
    if not submit_otp_on_page(page, result.code):
        step("OTP submit FAIL: no se pudo pegar en página")
        return False, f"OTP {result.code} leído pero no se pudo pegar en Amazon."

    # ¿sigue pidiendo OTP?
    page.wait_for_timeout(1500)
    if page_needs_otp(page):
        step("OTP still required after submit")
        return False, "OTP enviado pero Amazon sigue pidiendo verificación."

    step("OTP aplicado OK")
    return True, f"OTP {result.code} aplicado ({result.subject or 'Amazon'})."
