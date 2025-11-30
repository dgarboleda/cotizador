# Análisis del código

## Visión general
El proyecto implementa una aplicación de escritorio con Tkinter para generar cotizaciones en PDF, mantener un historial y enviar documentos por correo electrónico. Todo el flujo está concentrado en `cotizador.py`, que combina la interfaz, la lógica de negocio y la persistencia ligera en archivos JSON.

## Componentes principales
- **CotizadorPDF**: subclase de `FPDF` que maqueta el PDF de la cotización, incorporando el encabezado con datos de empresa, título y paginación automática. Gestiona el cuerpo (tabla de ítems) y el pie de página. 【F:cotizador.py†L20-L84】【F:cotizador.py†L259-L360】
- **CotizadorApp**: ventana raíz de Tkinter que organiza la UI en secciones (cliente, ítems, totales, términos y acciones). Carga/guarda configuración, controla la numeración de cotizaciones y administra el ciclo completo de generación de PDF, historial y envío por correo. 【F:cotizador.py†L87-L507】【F:cotizador.py†L362-L484】【F:cotizador.py†L568-L705】【F:cotizador.py†L747-L891】

## Flujo de trabajo
1. **Inicialización**: se cargan configuración, numeración y credenciales de correo desde `config_cotizador.json` si existe. 【F:cotizador.py†L99-L144】
2. **Captura de datos**: la interfaz permite ingresar cliente, dirección, condiciones y agregar ítems a un `Treeview` editable. El autocompletado de clientes frecuentes se alimenta del historial. 【F:cotizador.py†L146-L251】【F:cotizador.py†L509-L564】
3. **Cálculo de totales**: los subtotales se recalculan cada vez que se modifican ítems, con opción de incluir o excluir IGV. 【F:cotizador.py†L382-L410】
4. **Persistencia**: cada PDF generado se registra en `historial_cotizaciones.json`, que también se puede exportar a CSV. La configuración de empresa y correo se guarda en `config_cotizador.json`. 【F:cotizador.py†L412-L453】【F:cotizador.py†L607-L705】
5. **Generación y distribución**: `_crear_pdf_en_carpeta` produce el PDF, guarda el historial y devuelve la ruta; luego `generar_pdf` o `enviar_por_correo` abren el archivo y opcionalmente lo envían por SMTP. 【F:cotizador.py†L747-L891】

## Observaciones y posibles mejoras
- La lógica de negocio, UI y persistencia viven en un solo archivo, lo que dificulta pruebas unitarias y mantenibilidad. Dividir en módulos (UI, servicios de PDF, servicios de correo) ayudaría a aislar responsabilidades.
- La configuración de correo se almacena en texto plano; considerar cifrar credenciales o apoyarse en variables de entorno.
- El manejo de errores silenciosos (`except Exception: pass`) en carga y guardado de configuración e historial puede ocultar fallos; registrar los errores mejoraría la observabilidad.
- Agregar validaciones de tipos (p. ej., uso de `decimal.Decimal` para montos) evitaría errores de redondeo o formatos de entrada.
