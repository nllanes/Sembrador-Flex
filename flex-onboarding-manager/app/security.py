"""Cifrado simétrico de secretos en reposo (credenciales de buzones).

Uso legítimo: guardar de forma segura la contraseña del buzón de correo que TU
organización administra para cada conductor real. NO es para crear cuentas de
terceros ni para eludir verificaciones.

- Se cifra con Fernet (AES-128-CBC + HMAC). El texto plano nunca se guarda.
- La clave (`CRED_KEY`) vive SEPARADA del dato cifrado (variable de entorno /
  gestor de secretos). En desarrollo, si no se define, se reutiliza una clave
  estable guardada en `.cred_key_dev` (no commitear).
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

logger = logging.getLogger(__name__)

_DEV_KEY_FILE = Path(__file__).resolve().parent.parent / ".cred_key_dev"


def _load_or_create_dev_key() -> str:
    if _DEV_KEY_FILE.is_file():
        key = _DEV_KEY_FILE.read_text(encoding="utf-8").strip()
        if key:
            return key
    key = Fernet.generate_key().decode()
    _DEV_KEY_FILE.write_text(key + "\n", encoding="utf-8")
    logger.info(
        "CRED_KEY no definida: clave de desarrollo persistida en %s",
        _DEV_KEY_FILE,
    )
    return key


@lru_cache
def _get_fernet() -> Fernet:
    settings = get_settings()
    key = settings.cred_key.strip()
    if not key:
        if settings.app_env == "development":
            key = _load_or_create_dev_key()
        else:
            key = Fernet.generate_key().decode()
            logger.warning(
                "CRED_KEY no está configurada: se generó una clave EFÍMERA. "
                "Las credenciales cifradas no serán legibles tras reiniciar. "
                "Define CRED_KEY en el entorno para producción."
            )
    return Fernet(key.encode())


def encrypt_secret(plaintext: str) -> str:
    """Cifra un secreto y devuelve el token (texto) para guardar en la BD."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str | None:
    """Descifra un token. Devuelve None si la clave no corresponde (token inválido)."""
    if not token:
        return None
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        logger.error("No se pudo descifrar la credencial (clave incorrecta o dato corrupto).")
        return None
