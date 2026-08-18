"""Configuración de la aplicación cargada desde variables de entorno."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Ajustes globales de la app.

    Los valores se leen del entorno (o de un archivo `.env` en la raíz).
    """

    database_url: str = "postgresql+psycopg2://flex:flex@localhost:5432/flex_onboarding"
    app_env: str = "development"
    app_title: str = "Flex Onboarding Manager"
    api_prefix: str = "/api"

    # Clave Fernet (base64 urlsafe de 32 bytes) para cifrar credenciales en reposo.
    cred_key: str = ""

    # Sembrado: intentar registro real en Amazon.com con Playwright (email + pass del CRM).
    flex_creation_enabled: bool = True
    flex_creation_headless: bool = True
    flex_creation_timeout_ms: int = 120_000

    # Worker async: True = procesa jobs en background dentro de uvicorn (local).
    # En cloud pon False y corre: python -m scripts.flex_worker
    flex_worker_embedded: bool = True
    flex_worker_poll_seconds: float = 2.0

    # Región Flex vía app Android (Appium). Tras identidad web, aplica ZIP en la app.
    flex_appium_enabled: bool = True
    flex_appium_server_url: str = "http://127.0.0.1:4723"
    flex_appium_device_name: str = "Android Emulator"
    flex_appium_udid: str = "emulator-5554"  # vacío = autodetect
    flex_appium_no_reset: bool = False
    flex_appium_timeout_s: int = 180
    # Emuladores lentos: dumpsys/adb a menudo superan el default 20s de Appium.
    flex_appium_adb_exec_timeout_ms: int = 120_000
    flex_app_package: str = "com.amazon.flex.rabbit"
    flex_app_activity: str = "com.amazon.rabbit.android.presentation.core.LaunchActivity"
    flex_app_apk_path: str = ""  # opcional: ruta a APK si no está instalada
    flex_default_vehicle_type: str = "Sedan"

    # OTP por IMAP.
    # Modo A — buzón propio (Namecheap Private Email): deja IMAP_MOTHER_EMAIL vacío.
    # Modo B — dominio forward a Gmail madre: rellena IMAP_MOTHER_* y host imap.gmail.com
    imap_otp_enabled: bool = True
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_otp_timeout_s: int = 300
    imap_otp_poll_s: float = 5.0
    imap_mother_email: str = ""
    imap_mother_password: str = ""  # Gmail: App Password, no la pass normal

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Devuelve una instancia cacheada de Settings."""
    return Settings()
