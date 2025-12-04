# Build script simplificado
$ErrorActionPreference = 'Stop'

Write-Host "Empaquetando cotizador_app..."

# Limpiar builds anteriores
if (Test-Path "dist") {
    Remove-Item -Recurse -Force "dist"
}
if (Test-Path "build") {
    Remove-Item -Recurse -Force "build"
}

# Ejecutar PyInstaller
python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --noconsole `
    --name cotizador_app `
    --add-data "VERSION;." `
    cotizador.py

Write-Host "Build completado. Ejecutable en: dist\cotizador_app\cotizador_app.exe"
