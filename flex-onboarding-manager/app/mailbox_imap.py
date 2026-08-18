"""Lectura de OTP desde IMAP.

Dos modos:

1) Buzón propio (Namecheap Private Email, etc.)
   - Login IMAP con el email de la siembra + su password
   - Host típico: mail.privateemail.com:993

2) Dominio → forward catch-all a un Gmail "madre"
   - Solo compraste el dominio; todo *@tudominio.com cae en madre@gmail.com
   - Login IMAP con el Gmail madre (App Password)
   - Filtra correos cuyo To/Delivered-To sea el email de la siembra
   - Host: imap.gmail.com:993
"""

from __future__ import annotations

import email
import imaplib
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime

from app.config import get_settings

logger = logging.getLogger(__name__)

OTP_RE = re.compile(
    r"(?:(?:security|verification|one[-\s]?time|otp|auth(?:entication)?)\s*(?:code|password)?\s*[:=]?\s*)?"
    r"(?<!\d)(\d{6})(?!\d)",
    re.I,
)
OTP_RE_LOOSE = re.compile(r"(?<!\d)(\d{6})(?!\d)")

AMAZON_FROM = re.compile(r"amazon|account-update@|auto-confirm@", re.I)


@dataclass
class OtpFetchResult:
    ok: bool
    code: str | None = None
    message: str = ""
    subject: str | None = None


def _decode_mime(value: str | None) -> str:
    if not value:
        return ""
    parts = []
    for chunk, enc in decode_header(value):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(enc or "utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts)


def _message_body(msg: email.message.Message) -> str:
    chunks: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if ctype in ("text/plain", "text/html"):
                try:
                    payload = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    chunks.append(payload.decode(charset, errors="replace"))
                except Exception:
                    continue
    else:
        try:
            payload = msg.get_payload(decode=True) or b""
            charset = msg.get_content_charset() or "utf-8"
            chunks.append(payload.decode(charset, errors="replace"))
        except Exception:
            pass
    text = "\n".join(chunks)
    text = re.sub(r"<[^>]+>", " ", text)
    return text


def _extract_otp(subject: str, body: str) -> str | None:
    blob = f"{subject}\n{body}"
    for rx in (OTP_RE, OTP_RE_LOOSE):
        for m in rx.finditer(blob):
            code = m.group(1)
            if code.startswith(("19", "20")) and int(code[:4]) > 1900:
                continue
            return code
    return None


def _message_targets(msg: email.message.Message) -> str:
    """Headers donde suele aparecer el destinatario original tras un forward."""
    keys = (
        "To",
        "Delivered-To",
        "X-Original-To",
        "X-Forwarded-To",
        "Envelope-To",
        "Cc",
        "Apparently-To",
    )
    parts = [_decode_mime(msg.get(k)) for k in keys]
    # A veces el forward pone el alias en el cuerpo
    return " ".join(p for p in parts if p).lower()


def _addressed_to(msg: email.message.Message, target_email: str) -> bool:
    target = target_email.strip().lower()
    blob = _message_targets(msg)
    if target in blob:
        return True
    # Gmail a veces solo deja el local-part en filtros; exigir email completo
    body = _message_body(msg).lower()
    return target in body


def fetch_amazon_otp(
    *,
    email_addr: str,
    mailbox_password: str,
    since: datetime | None = None,
    timeout_s: int | None = None,
    poll_s: float | None = None,
) -> OtpFetchResult:
    """Espera y lee un OTP de Amazon desde IMAP (buzón propio o Gmail madre)."""
    settings = get_settings()
    # Recargar .env si cambió (lru_cache del proceso uvicorn)
    try:
        get_settings.cache_clear()
        settings = get_settings()
    except Exception:
        pass
    if not settings.imap_otp_enabled:
        return OtpFetchResult(
            ok=False,
            message="Lectura OTP por IMAP desactivada (IMAP_OTP_ENABLED=false).",
        )

    mother = (settings.imap_mother_email or "").strip()
    mother_pass = (settings.imap_mother_password or "").strip()
    use_mother = bool(mother and mother_pass)

    if use_mother:
        login_user = mother
        login_pass = mother_pass
        host = settings.imap_host or "imap.gmail.com"
        mode = "gmail_madre"
    else:
        login_user = email_addr
        login_pass = mailbox_password
        host = settings.imap_host or "mail.privateemail.com"
        mode = "buzon_propio"

    port = settings.imap_port
    timeout = timeout_s if timeout_s is not None else settings.imap_otp_timeout_s
    poll = poll_s if poll_s is not None else settings.imap_otp_poll_s
    since = since or datetime.now(timezone.utc)
    deadline = time.time() + max(15, timeout)
    last_err = ""

    try:
        from app.flex_apply.pipeline_log import step
    except Exception:
        def step(msg: str, **_k):  # type: ignore
            logger.info(msg)

    boxes = ("INBOX",) if not use_mother else ("INBOX", "[Gmail]/Spam")
    step(
        f"OTP IMAP wait hasta {timeout}s (poll {poll}s) mode={mode} "
        f"boxes={','.join(boxes)} since={since.isoformat()}"
    )
    poll_n = 0

    while time.time() < deadline:
        poll_n += 1
        left = max(0, int(deadline - time.time()))
        try:
            client = imaplib.IMAP4_SSL(host, port)
            try:
                client.login(login_user, login_pass)
                day = since.astimezone().strftime("%d-%b-%Y")
                scanned = 0
                amazonish = 0
                for box in boxes:
                    try:
                        if client.select(box)[0] != "OK":
                            continue
                    except Exception:
                        continue
                    # En modo madre, buscar Amazon; filtrar destinatario en Python
                    if use_mother:
                        status, data = client.search(
                            None, f'(SINCE "{day}" FROM "amazon")'
                        )
                        if status != "OK" or not (data and data[0]):
                            status, data = client.search(None, f'(SINCE "{day}")')
                    else:
                        status, data = client.search(None, f'(SINCE "{day}")')

                    if status != "OK":
                        last_err = f"IMAP search falló ({box}): {status}"
                        continue

                    ids = data[0].split() if data and data[0] else []
                    for mid in reversed(ids[-50:]):
                        st, msg_data = client.fetch(mid, "(RFC822)")
                        if st != "OK" or not msg_data or not msg_data[0]:
                            continue
                        raw = msg_data[0][1]
                        if not isinstance(raw, (bytes, bytearray)):
                            continue
                        scanned += 1
                        msg = email.message_from_bytes(raw)
                        frm = _decode_mime(msg.get("From"))
                        subj = _decode_mime(msg.get("Subject"))
                        if not AMAZON_FROM.search(frm) and not AMAZON_FROM.search(subj):
                            continue
                        amazonish += 1
                        if use_mother and not _addressed_to(msg, email_addr):
                            continue
                        try:
                            msg_dt = parsedate_to_datetime(msg.get("Date"))
                            if msg_dt.tzinfo is None:
                                msg_dt = msg_dt.replace(tzinfo=timezone.utc)
                            if msg_dt < since - timedelta(minutes=2):
                                continue
                        except Exception:
                            pass
                        body = _message_body(msg)
                        code = _extract_otp(subj, body)
                        if code:
                            step(
                                f"OTP IMAP HIT box={box} subj={subj[:80]} "
                                f"code={code[:2]}****"
                            )
                            logger.info(
                                "OTP (%s) para %s via %s",
                                code[:2] + "****",
                                email_addr,
                                mode,
                            )
                            return OtpFetchResult(
                                ok=True,
                                code=code,
                                message=(
                                    f"OTP leído desde "
                                    f"{'Gmail madre' if use_mother else 'buzón IMAP'} "
                                    f"({box})."
                                ),
                                subject=subj,
                            )
                last_err = (
                    f"Aún no hay OTP de Amazon para {email_addr} "
                    f"en {'Gmail madre' if use_mother else 'el buzón'}."
                )
                if poll_n == 1 or poll_n % 3 == 0 or left <= poll:
                    step(
                        f"OTP IMAP poll#{poll_n} left={left}s "
                        f"scanned={scanned} amazonish={amazonish}"
                    )
            finally:
                try:
                    client.logout()
                except Exception:
                    pass
        except imaplib.IMAP4.error as exc:
            last_err = f"IMAP auth/error ({mode}): {exc}"
            logger.warning("IMAP error: %s", exc)
            step(f"OTP IMAP error: {exc}")
            if "AUTHENTICATIONFAILED" in str(exc).upper() or "LOGIN" in str(exc).upper():
                hint = ""
                if use_mother:
                    hint = (
                        " Usa una App Password de Gmail "
                        "(cuenta Google → Seguridad → Contraseñas de aplicaciones)."
                    )
                return OtpFetchResult(ok=False, message=last_err + hint)
        except Exception as exc:
            last_err = f"IMAP: {exc}"
            logger.warning("IMAP exception: %s", exc)
            step(f"OTP IMAP exception: {exc}")

        time.sleep(max(2.0, poll))

    step(f"OTP IMAP TIMEOUT {timeout}s — {last_err}")
    return OtpFetchResult(
        ok=False,
        message=last_err or f"Timeout {timeout}s esperando OTP para {email_addr}.",
    )
