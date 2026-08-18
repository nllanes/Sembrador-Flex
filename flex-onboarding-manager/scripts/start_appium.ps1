# Arranca Appium con ANDROID_HOME apuntando al SDK local.
$ErrorActionPreference = "Stop"
$sdk = "C:\Program Files (x86)\Android\android-sdk"
if (-not (Test-Path "$sdk\platform-tools\adb.exe")) {
    Write-Host "ERROR: no encuentro adb en $sdk" -ForegroundColor Red
    exit 1
}
$env:ANDROID_HOME = $sdk
$env:ANDROID_SDK_ROOT = $sdk
$env:Path = "$sdk\platform-tools;$sdk\emulator;$sdk\tools;$sdk\tools\bin;" + $env:Path

Write-Host "ANDROID_HOME=$env:ANDROID_HOME"
adb devices
Write-Host "Iniciando Appium en 127.0.0.1:4723 ..."
appium --address 127.0.0.1 --port 4723
