"""Enumeraciones del dominio: estados del expediente y del checklist.

IMPORTANTE: este sistema SOLO hace tracking manual. No automatiza el registro
en Amazon Flex ni los background checks; únicamente registra el estado en el que
se encuentra cada expediente.
"""

from enum import Enum


class OnboardingStatus(str, Enum):
    """Estados del expediente de onboarding de un conductor.

    El flujo avanza (normalmente) en este orden, pero se permite mover a
    cualquier estado manualmente porque el proceso real vive fuera del sistema.
    """

    NOT_STARTED = "not_started"          # Email asignado, sin iniciar
    INVITED = "invited"                  # Invitación/enlace enviado al candidato
    REGISTRATION_STARTED = "registration_started"  # El candidato empezó el registro en Amazon
    DOCUMENTS_PENDING = "documents_pending"        # Faltan documentos por subir
    DOCUMENTS_SUBMITTED = "documents_submitted"    # Documentos completos
    BACKGROUND_CHECK = "background_check"           # En verificación de antecedentes
    WAITLISTED = "waitlisted"            # En lista de espera de Amazon
    APPROVED_ACTIVE = "approved_active"  # Aprobado y activo (listo para handoff)
    REJECTED = "rejected"                # Rechazado
    INACTIVE = "inactive"                # Dado de baja / pausado


# Orden lógico del flujo (para ordenar/mostrar y validar avances "hacia adelante").
STATUS_ORDER: list[OnboardingStatus] = [
    OnboardingStatus.NOT_STARTED,
    OnboardingStatus.INVITED,
    OnboardingStatus.REGISTRATION_STARTED,
    OnboardingStatus.DOCUMENTS_PENDING,
    OnboardingStatus.DOCUMENTS_SUBMITTED,
    OnboardingStatus.BACKGROUND_CHECK,
    OnboardingStatus.WAITLISTED,
    OnboardingStatus.APPROVED_ACTIVE,
]

# Estados terminales que no forman parte del avance lineal.
TERMINAL_STATUSES: set[OnboardingStatus] = {
    OnboardingStatus.REJECTED,
    OnboardingStatus.INACTIVE,
}

# Estados elegibles para "Sembrar en Amazon Flex" (aún no enviados a creación).
FLEX_DISPATCH_ELIGIBLE: set[OnboardingStatus] = {
    OnboardingStatus.NOT_STARTED,
    OnboardingStatus.INVITED,
}

# Estado al que pasan al confirmar el envío a creación.
FLEX_DISPATCH_TARGET = OnboardingStatus.REGISTRATION_STARTED

# Estados en los que tiene sentido consultar zonas para crear cuenta Flex.
# El registro real lo hace una persona; esto solo orienta dónde Amazon suele aceptar.
ACCOUNT_CREATION_STATUSES: set[OnboardingStatus] = {
    OnboardingStatus.NOT_STARTED,
    OnboardingStatus.INVITED,
    OnboardingStatus.REGISTRATION_STARTED,
    OnboardingStatus.DOCUMENTS_PENDING,
}


class ChecklistStatus(str, Enum):
    """Estado de cada ítem del checklist de un expediente."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"


class EventType(str, Enum):
    """Tipos de evento registrados en la línea de tiempo (timeline)."""

    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    CHECKLIST_UPDATED = "checklist_updated"
    NOTE_ADDED = "note_added"
    HANDOFF_READY = "handoff_ready"
    HANDOFF_DONE = "handoff_done"
    CREDENTIAL_SET = "credential_set"
    CREDENTIAL_REVEALED = "credential_revealed"
    CREDENTIAL_CLEARED = "credential_cleared"


class FlexJobStatus(str, Enum):
    """Estado de un job asíncrono de Sembrar (cola cloud-ready)."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# Plantilla por defecto de checklist para un nuevo expediente.
# Refleja pasos de onboarding SIN automatizarlos (solo seguimiento).
DEFAULT_CHECKLIST_TEMPLATE: list[str] = [
    "Email de Amazon Flex asignado",
    "Invitación enviada al candidato",
    "Cuenta de Amazon Flex creada por el candidato",
    "Documento de identidad recibido",
    "Licencia de conducir válida verificada",
    "Datos bancarios / método de pago",
    "Background check iniciado (por el candidato en Amazon)",
    "Documentos completos y revisados",
    "Listo para handoff al sistema de monitoreo",
]
