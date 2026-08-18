"""Laboratorio: manejo SEGURO de credenciales.

Aprende la diferencia clave entre dos necesidades distintas:

  1) HASHING (unidireccional): para verificar contraseñas de LOGIN de tus
     usuarios. Nunca se puede "des-hashear". Usas scrypt/bcrypt/argon2 + salt.

  2) CIFRADO (reversible): para guardar secretos que SÍ necesitas recuperar
     luego, como la contraseña de un buzón de correo de tu propio dominio.
     Usas cifrado simétrico (Fernet/AES) con una clave guardada aparte.

REGLA DE ORO
------------
- Contraseñas de usuarios de TU app  -> HASH (nunca las guardas en claro).
- Secretos operativos que debes reutilizar (SMTP/IMAP, API keys, passwords de
  buzones que tú administras) -> CIFRADO, con la clave en un secreto/variable
  de entorno separada del dato cifrado.

Dependencias:
    pip install -r requirements.txt   # cryptography
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from cryptography.fernet import Fernet


# --------------------------------------------------------------------------- #
# 1) HASHING de contraseñas (unidireccional) — con scrypt de la stdlib
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    """Devuelve 'salt$hash' en hex. Cada password lleva su propio salt aleatorio."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verifica en tiempo constante (evita timing attacks)."""
    try:
        salt_hex, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    candidate = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return hmac.compare_digest(candidate, expected)


# --------------------------------------------------------------------------- #
# 2) CIFRADO reversible (para secretos recuperables) — Fernet (AES-128 + HMAC)
# --------------------------------------------------------------------------- #
def get_or_create_key() -> bytes:
    """Obtiene la clave de cifrado desde la variable de entorno CRED_KEY.

    En producción NUNCA la generes al vuelo: guárdala en un gestor de secretos
    (Docker secret, AWS Secrets Manager, .env fuera del repo). Aquí la generamos
    solo para la demo si no existe.
    """
    env_key = os.environ.get("CRED_KEY")
    if env_key:
        return env_key.encode()
    # Solo para la demo local:
    return Fernet.generate_key()


def encrypt_secret(plaintext: str, key: bytes) -> str:
    return Fernet(key).encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str, key: bytes) -> str:
    return Fernet(key).decrypt(token.encode()).decode()


# --------------------------------------------------------------------------- #
# Demo
# --------------------------------------------------------------------------- #
def _demo() -> None:
    print("=== 1) HASHING (login de usuarios) ===")
    stored = hash_password("MiClaveSuperSecreta!")
    print("Guardado en BD:", stored)
    print("Login correcto:", verify_password("MiClaveSuperSecreta!", stored))
    print("Login incorrecto:", verify_password("otra", stored))

    print("\n=== 2) CIFRADO (password de buzón de correo que administras) ===")
    key = get_or_create_key()
    mailbox_pass = "p4ssw0rd-del-buzon"
    token = encrypt_secret(mailbox_pass, key)
    print("Guardado cifrado en BD:", token)
    print("Recuperado para usarlo:", decrypt_secret(token, key))
    print("\nClave de cifrado (CRED_KEY) — guárdala aparte del dato:", key.decode())


if __name__ == "__main__":
    _demo()
