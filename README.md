# Sistema de Cotizaciones

Aplicación desktop desarrollada en Python y Tkinter para generar, gestionar y hacer seguimiento de cotizaciones.

## Características

- **Generación de cotizaciones**: Crear cotizaciones con múltiples ítems e imágenes
- **Cálculo automático de totales**: Con soporte para IGV configurable
- **Multi-moneda**: Soles, Dólares, Euros
- **Gestión de clientes**: Clientes frecuentes con historial
- **Historial completo**: Búsqueda, filtrado y estadísticas
- **Versionado**: Crear nuevas versiones de cotizaciones existentes
- **Exportación**: A PDF y Excel
- **Envío por email**: Integración con SMTP

## Requisitos

- Python 3.8+
- Dependencias listadas en `requirements.txt`

## Instalación

```bash
pip install -r requirements.txt
python cotizador.py
```

## Compilación ejecutable

```bash
.\build.ps1
```

El ejecutable estará en `dist/cotizador_app/cotizador_app.exe`

## Estructura de carpetas

```
Cotizador/
├── cotizador.py              Aplicación principal
├── build.ps1                 Script para compilar a ejecutable
├── requirements.txt          Dependencias Python
├── Cotizaciones/            Archivos PDF generados
├── Referencias/             Imágenes de referencia de ítems
└── .vscode/                 Configuración de VS Code
```

## Configuración

La aplicación guarda configuración en `config_cotizador.json`:
- Datos de empresa (nombre, RUC, dirección)
- Configuración de email
- Tasas de IGV y moneda predeterminadas
- Rutas personalizadas para Cotizaciones y Referencias

## Historial

El historial de cotizaciones se guarda en `historial_cotizaciones.json` con toda la información de cada cotización.

## Licencia

Todos los derechos reservados.
