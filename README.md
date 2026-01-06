# Sistema de Cotizaciones

Aplicación desktop desarrollada en Python y Tkinter para generar, gestionar y hacer seguimiento de cotizaciones.

## Características Principales

### 📋 Gestión de Cotizaciones
- **Generación de cotizaciones**: Crear cotizaciones con múltiples ítems e imágenes
- **Cálculo automático de totales**: Con soporte para IGV configurable
- **Multi-moneda**: Soles, Dólares, Euros
- **Versionado**: Crear nuevas versiones de cotizaciones existentes

### 👥 Gestión de Clientes
- **Clientes frecuentes**: Guardado automático del historial
- **Validación RUC**: Consulta automática a API SUNAT para llenar datos
- **Autocomplete**: Búsqueda rápida de clientes previos

### 📑 Plantillas de Items
- **Plantillas automáticas**: Se generan del historial de cotizaciones
- **Sin duplicados**: Items únicos ordenados alfabéticamente
- **Rápida reutilización**: Usar items frecuentes sin reescribir

### 📊 Historial y Búsqueda
- **Historial completo**: Acceso a todas las cotizaciones anteriores
- **Búsqueda y filtrado**: Por cliente, fecha, rango de precios
- **Estadísticas**: Resumen de ventas y cotizaciones

### 📄 Exportación
- **PDF profesional**: Con logo de empresa y detalles completos
- **Excel/CSV**: Exportar historial de cotizaciones
- **Envío por email**: Integración con SMTP

### 🎨 Interfaz Mejorada
- **Barra de estado interactiva**: Mensajes con colores y efecto parpadeo (8 ciclos)
- **Disposición flexible**: Campos adaptables y columnas proporcionales
- **Vista previa de imágenes**: Previsualización de imágenes de ítems
- **Descripción multilínea**: Items con descripciones detalladas

## Requisitos

- Python 3.8+
- Dependencias listadas en `requirements.txt`

## Instalación

```bash
pip install -r requirements.txt
python cotizador.py
```

### Servidor Web (API ligera)
Para exponer la lógica del cotizador en una API web sin dependencias adicionales:

```bash
python web_api.py  # Inicia servidor HTTP en http://localhost:8000
```

Variables de entorno útiles:
- `COTIZADOR_CONFIG_PATH`: ruta al archivo `config_cotizador.json` a usar en la API.
- `COTIZADOR_HIST_PATH`: ruta al archivo `historial_cotizaciones.json` para persistir cotizaciones creadas vía API.

Endpoints principales:
- `GET /api/health` — estado del servicio.
- `GET /api/config` — configuración básica (moneda, IGV, serie).
- `GET /api/cotizaciones` — listado de cotizaciones recientes (parámetro `limit` opcional).
- `POST /api/cotizaciones` — crea una nueva cotización y la guarda en el historial.

## Compilación a Ejecutable

```bash
.\build.ps1
```

El ejecutable estará en `dist/cotizador_app/cotizador_app.exe`

## Estructura de Carpetas

```
Cotizador/
├── cotizador.py                    Aplicación principal
├── build.ps1                       Script para compilar a ejecutable
├── requirements.txt                Dependencias Python
├── config_cotizador.json          Configuración de empresa y email
├── historial_cotizaciones.json    Historial de todas las cotizaciones
├── plantillas_items.json          Items únicos del historial (generado automáticamente)
├── Cotizaciones/                  Archivos PDF generados
├── Referencias/                   Imágenes de referencia de ítems
└── .vscode/                       Configuración de VS Code
```

## Configuración

### config_cotizador.json
Almacena la configuración de la aplicación:
- **Datos de empresa**: Nombre, RUC, dirección, logo
- **Email**: Servidor SMTP, usuario, contraseña
- **Tasas**: IGV y moneda predeterminadas
- **Rutas**: Carpetas personalizadas para Cotizaciones y Referencias
- **Términos**: Términos y condiciones predeterminados

### historial_cotizaciones.json
Guarda el historial completo de cotizaciones:
- Información del cliente (nombre, email, dirección, RUC)
- Todos los ítems con descripciones, cantidades y precios
- Totales, IGV, moneda utilizada
- Fecha, estado y versión de cada cotización

### plantillas_items.json
Se genera automáticamente desde el historial:
- Items únicos sin duplicados
- Cantidad y precio frecuente de cada item
- Se actualiza cada vez que abres la ventana de plantillas

## Funcionalidades Avanzadas

### 🔍 Validación RUC
- Valida números RUC peruanos (11 dígitos con dígito verificador)
- Consulta API SUNAT para obtener nombre y dirección automáticamente
- Manejo de errores: 404, sin conexión, timeout

### 📱 Barra de Estado
- **Colores informativos**: Verde (éxito), Rojo (error), Naranja (advertencia), Azul (información)
- **Efecto parpadeo**: 8 ciclos para mejor visibilidad
- **Texto en negrita**: Mayor legibilidad de mensajes
- **Clickeable**: Acceso al registro de notificaciones

### 📋 Descripción de Items
- **Multilínea**: Soporta descripciones con múltiples líneas
- **Visualización en tabla**: Muestra con separadores ` | ` (una línea)
- **En PDF**: Se restauran los saltos de línea para mejor formato
- **En historial**: Se preservan los saltos de línea originales

## Licencia

Todos los derechos reservados.
