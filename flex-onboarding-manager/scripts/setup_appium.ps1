# Setup Appium + Android para Sembrar hasta región Flex (Windows)
# Uso:  .\scripts\setup_appium.ps1
#
# Requisitos previos (instálalos si faltan):
#   1. Node.js LTS  https://nodejs.org/
#   2. Android Studio (SDK + emulador)  https://developer.android.com/studio
#   3. Python del proyecto con: pip install -r requirements.txt

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "== Flex Appium setup ==" -ForegroundColor Cyan

# 1) Appium server global
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: npm/Node.js no está en PATH. Instala Node.js LTS y reabre la terminal." -ForegroundColor Red
    exit 1
}

Write-Host "Instalando Appium 3 + driver UiAutomator2 (versión estable)..."
npm install -g appium@3
appium driver uninstall uiautomator2 2>$null
appium driver install uiautomator2@4.2.9
appium -v
appium driver list --installed

# 2) Cliente Python
Write-Host "Instalando Appium-Python-Client..."
python -m pip install "Appium-Python-Client==4.3.0" "selenium==4.27.1" -q

# 3) ADB check
$adb = Get-Command adb -ErrorAction SilentlyContinue
if (-not $adb) {
    Write-Host "AVISO: adb no está en PATH. Añade Android SDK platform-tools al PATH." -ForegroundColor Yellow
    Write-Host "  Ejemplo: C:\Users\$env:USERNAME\AppData\Local\Android\Sdk\platform-tools" -ForegroundColor Yellow
} else {
    Write-Host "Dispositivos ADB:"
    adb devices
}

Write-Host ""
Write-Host "Siguiente:" -ForegroundColor Green
Write-Host "  1. Abre Android Studio → Device Manager → crea/arranca un emulador (API 33+)."
Write-Host "  2. Instala Amazon Flex en el emulador (Play Store) O:"
Write-Host "       adb install ruta\AmazonFlex.apk"
Write-Host "  3. En otra terminal:  appium"
Write-Host "  4. En .env:  FLEX_APPIUM_ENABLED=true"
Write-Host "  5. Healthcheck:  curl http://127.0.0.1:8080/api/meta/appium-status"
Write-Host "  6. Sembrar una siembra CON ZIP."
Write-Host ""
Write-Host "Package por defecto: com.amazon.flex.rabbit"
Write-Host "Si la activity falla, ajusta FLEX_APP_ACTIVITY en .env tras: adb shell dumpsys package com.amazon.flex.rabbit"
