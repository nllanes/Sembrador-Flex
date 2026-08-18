"""Automatización de creación de cuenta Amazon (sembrado con email + contraseña del CRM)."""

from app.flex_creation.service import CreationOutcome, attempt_amazon_account_creation

__all__ = ["CreationOutcome", "attempt_amazon_account_creation"]
