# Diagrama de flujo — Onboarding de conductores Amazon Flex

> **Alcance:** este sistema **solo hace tracking**. NO automatiza el registro en
> Amazon Flex ni los background checks. Registra el estado, checklist, timeline y
> el handoff (traspaso manual) al sistema de monitoreo.

## Máquina de estados del expediente

```mermaid
stateDiagram-v2
    [*] --> not_started

    not_started --> invited
    invited --> registration_started
    registration_started --> documents_pending
    documents_pending --> documents_submitted
    documents_submitted --> background_check
    background_check --> waitlisted
    background_check --> approved_active
    waitlisted --> approved_active

    approved_active --> [*]: handoff al sistema de monitoreo

    %% Estados terminales alcanzables desde casi cualquier punto
    documents_pending --> rejected
    background_check --> rejected
    waitlisted --> rejected
    invited --> inactive
    registration_started --> inactive
    approved_active --> inactive

    note right of approved_active
        Al llegar aquí se marca
        handoff_ready = true
    end note
```

## Flujo del proceso (operativo)

```mermaid
flowchart TD
    A[Asignar email Amazon Flex] --> B[Crear expediente<br/>status = not_started]
    B --> C[Enviar invitación al candidato<br/>status = invited]
    C --> D{Candidato inicia<br/>registro en Amazon}
    D -->|Sí| E[registration_started]
    E --> F[Recolectar documentos<br/>documents_pending → documents_submitted]
    F --> G[Background check<br/>lo ejecuta Amazon, aquí solo se marca]
    G --> H{Resultado}
    H -->|En espera| I[waitlisted]
    H -->|Aprobado| J[approved_active]
    I --> J
    J --> K[handoff_ready = true]
    K --> L[Handoff manual:<br/>marcar handoff_done + external_ref]
    L --> M[[Vincular en el<br/>sistema de monitoreo SaaS]]

    H -->|Rechazado| X[rejected]
```

## Modelo de datos

```mermaid
erDiagram
    CANDIDATE ||--o{ CHECKLIST_ITEM : tiene
    CANDIDATE ||--o{ TIMELINE_EVENT : registra

    CANDIDATE {
        int id PK
        string full_name
        string assigned_email UK
        string phone
        string region
        enum status
        text notes
        bool handoff_ready
        bool handoff_done
        string external_ref
        datetime created_at
        datetime updated_at
    }
    CHECKLIST_ITEM {
        int id PK
        int candidate_id FK
        string label
        int position
        enum status
        text notes
    }
    TIMELINE_EVENT {
        int id PK
        int candidate_id FK
        enum event_type
        text message
        string from_status
        string to_status
        string actor
        datetime created_at
    }
```
