# Sembrado Flex hasta región (sin datos personales)

## Qué hace **Sembrar**

1. **Paso 1 — Playwright (web):** crea / inicia sesión en `amazon.com` y **prueba la sesión** (Your Account). Si pide OTP, lo lee por IMAP (Gmail madre / forward).
2. **Web Flex:** intenta ZIP en `flex.amazon.com` (a menudo solo pide la app)
3. **Appium (Android):** abre Amazon Flex → login → ZIP → detecta región o lista
4. **STOP** antes de licencia / SSN / banco / background check

> Si el paso 1 falla (pass débil, OTP sin forward, sesión no verificada), **no** se avanza a la app.

## Outcomes

| Outcome | Significado | Estado CRM |
|---------|-------------|------------|
| `region_ready` | Región OK; listo para docs (otra persona) | `documents_pending` |
| `waitlisted` | Join list / sin cupo | `waitlisted` |
| `needs_app` | Cuenta OK; falta Appium o ZIP | `registration_started` |
| `needs_verification` | OTP email/SMS | `invited` |
| `failed` | Error / CAPTCHA / Appium caído | no cambia |

## Setup Windows (una vez)

```powershell
cd d:\Work\SembradorFlex\flex-onboarding-manager
.\scripts\setup_appium.ps1
```

Luego:

1. Arranca un **emulador Android** o conecta un **teléfono real** (`adb devices`)
2. Instala **Amazon Flex** (Play Store, o `adb install …apk`)
3. Terminal aparte: `.\scripts\start_appium.ps1` (pone `ANDROID_HOME`)
4. En `.env`:

```env
FLEX_CREATION_ENABLED=true
FLEX_CREATION_HEADLESS=false
FLEX_APPIUM_ENABLED=true
FLEX_APPIUM_SERVER_URL=http://127.0.0.1:4723
FLEX_APPIUM_UDID=emulator-5554
FLEX_APP_PACKAGE=com.amazon.flex.rabbit
FLEX_APP_ACTIVITY=com.amazon.rabbit.android.presentation.core.LaunchActivity
FLEX_DEFAULT_VEHICLE_TYPE=Sedan
```

> **Importante (Windows x86):** emuladores `sdk_gphone64_x86_64` suelen **crash** al abrir Flex
> (APK ARM64 + traducción NDK `kHasAES`). Si Flex se cierra sola al abrirla a mano,
> usa un **teléfono Android real** por USB con depuración.
5. Reinicia el CRM: `.\run_local.ps1`
6. Comprueba: http://127.0.0.1:8080/api/meta/appium-status

## Uso

1. Crea siembra con **ZIP región Flex** (modal o panel de detalle)
2. Guarda email + password
3. **Sembrar**
4. Lee el modal de resultado (`region_ready` / `waitlisted` / …)
5. Evidencias (screenshots): `var/flex_apply/`

## Si la activity no abre

```powershell
adb shell dumpsys package com.amazon.flex.rabbit | findstr Activity
```

Copia una activity de lanzamiento a `FLEX_APP_ACTIVITY` en `.env`.

## Cloud

Ver también `docs/async_jobs.md`.

1. API con `FLEX_WORKER_EMBEDDED=false`
2. Worker: `python -m scripts.flex_worker` en máquina con Chromium (+ Appium si aplica)
3. Misma `DATABASE_URL` y `CRED_KEY`

Usa solo cuentas y buzones que **tú administras**. Respeta rate limits.
La automatización de la app puede romperse con updates de Amazon Flex;
los selectores se basan en texto visible (UiAutomator2).
