import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import datetime
from fpdf import FPDF
import json
from pathlib import Path
import csv
import smtplib
from email.message import EmailMessage
import os
import sys
import subprocess
import re
import difflib
import shutil
import uuid

try:
    from tkcalendar import DateEntry
except ImportError:
    DateEntry = None

# Nota: para vista previa de imágenes instalar Pillow:
# pip install pillow

CONFIG_PATH = Path("config_cotizador.json")
HIST_PATH = Path("historial_cotizaciones.json")
IGV_RATE = 0.18

# Regex compiladas para mejor performance
EMAIL_PATTERN = re.compile(r"[^@]+@[^@]+\.[^@]+")

# Constantes de símbolos de moneda (para evitar recrear dict en cada iteración)
SIMBOLOS_MONEDA = {"SOLES": "S/", "DOLARES": "$", "EUROS": "€"}

# Formatos de fecha para parsing flexible
FORMATOS_FECHA = ["%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"]


# ==== HELPERS GENERALES ===============================================
def get_base_dir() -> Path:
    """
    Devuelve el directorio base de la app (donde está el ejecutable o script).
    Compatible con script normal y ejecutable (PyInstaller/cx_Freeze).
    """
    if getattr(sys, "frozen", False):
        # Si es ejecutable, usar el directorio del ejecutable
        return Path(sys.executable).resolve().parent
    # Si es script, usar el directorio del script
    return Path(sys.argv[0]).resolve().parent


def load_json_safe(path: Path, default):
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def save_json_safe(path: Path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def get_cotizaciones_dir(config: dict) -> Path:
    """Obtiene la ruta de la carpeta Cotizaciones (configurable o predeterminada)."""
    custom_path = config.get("carpeta_cotizaciones", "")
    if custom_path and Path(custom_path).exists():
        return Path(custom_path)
    return get_base_dir() / "Cotizaciones"


def get_referencias_dir(config: dict) -> Path:
    """Obtiene la ruta de la carpeta Referencias (configurable o predeterminada)."""
    custom_path = config.get("carpeta_referencias", "")
    if custom_path and Path(custom_path).exists():
        return Path(custom_path)
    return get_base_dir() / "Referencias"


def parse_numero_version(numero: str) -> tuple:
    """
    Parsea un número de cotización con versión.
    
    Retorna: (numero_sin_version, version)
    Ejemplo: "COT-2024-00001-V3" -> ("COT-2024-00001", 3)
    """
    if "-V" not in numero:
        return numero, 1
    
    try:
        parts = numero.split("-V")
        return parts[0], int(parts[1])
    except (IndexError, ValueError):
        return numero, 1


def parse_fecha_flexible(fecha_str: str):
    """
    Parsea fecha con múltiples formatos sin recrear lista cada vez.
    Retorna: datetime.date o None
    Optimización: usa constante FORMATOS_FECHA en lugar de recrear lista
    """
    if not fecha_str:
        return None
    
    fecha_base = fecha_str.split()[0]  # Tomar solo la fecha sin hora
    
    for fmt in FORMATOS_FECHA:
        try:
            return datetime.strptime(fecha_base, fmt).date()
        except ValueError:
            continue
    
    return None


def validar_ruc_peruano(ruc: str) -> bool:
    """
    Valida un RUC peruano incluyendo el dígito verificador.
    RUC tiene 11 dígitos y el último es un dígito verificador.
    """
    if not ruc or not ruc.isdigit() or len(ruc) != 11:
        return False
    
    # Algoritmo de validación del RUC peruano
    factores = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    suma = sum(int(ruc[i]) * factores[i] for i in range(10))
    resto = suma % 11
    digito_verificador = 11 - resto if resto != 0 else 0
    
    # Si el resultado es 10 o 11, el dígito verificador es 0
    if digito_verificador >= 10:
        digito_verificador = 0
    
    return int(ruc[10]) == digito_verificador


# ==== PDF ==============================================================

class CotizadorPDF(FPDF):
    def __init__(self, empresa, logo_path=None, numero=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logo_path = logo_path
        self.empresa = empresa
        self.numero = numero

    def header(self):
        if self.logo_path:
            try:
                self.image(self.logo_path, x=10, y=8, w=30)
            except Exception:
                pass

        self.set_xy(45, 10)
        self.set_font("Helvetica", "B", 16)
        self.cell(0, 8, self.empresa.get("nombre", "EMPRESA"), ln=1)

        self.set_x(45)
        self.set_font("Helvetica", "", 10)
        ruc = self.empresa.get("ruc", "")
        if ruc:
            self.cell(0, 5, f"RUC: {ruc}", ln=1)
        direccion = self.empresa.get("direccion", "")
        if direccion:
            self.set_x(45)
            self.cell(0, 5, f"Dirección: {direccion}", ln=1)

        self.ln(5)
        self.set_font("Helvetica", "B", 15)
        title = f"Cotización N°: {self.numero}" if self.numero else "Cotización"
        self.cell(0, 10, title, ln=1, align="C")
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Página {self.page_no()}", align="C")


# ==== APP ==============================================================

class CotizadorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sistema de Cotizaciones")
        self.state('zoomed')  # Maximizar ventana al iniciar
        self.geometry("1150x900")

        # Config persistente
        self.logo_path = None
        self.empresa = {
            "nombre": "",
            "ruc": "",
            "direccion": "",
        }
        # Serie se calcula automáticamente del año actual
        from datetime import datetime
        self.serie = f"COT-{datetime.now().year}"
        self.correlativo = 1
        self.tasa_igv = 0.18  # 18% predeterminado
        self.moneda = "SOLES"  # SOLES, DOLARES, EUROS
        self._simbolo_moneda_cache = "S/"  # Cache del símbolo de moneda
        self.carpeta_cotizaciones = ""  # Ruta personalizada (vacío = usar predeterminada)
        self.carpeta_referencias = ""   # Ruta personalizada (vacío = usar predeterminada)
        # Términos y condiciones predeterminados
        self.terminos_predeterminados = {
            "texto": "",
            "condicion_pago": "50% adelanto - 50% contraentrega",
            "validez": "7 días"
        }
        self.email_config = {
            "servidor": "",
            "puerto": 587,
            "usuario": "",
            "password": "",
            "usar_tls": True,
        }

        # cache clientes
        self.clientes_hist = {}
        self.cliente_seleccionado = None  # Para proteger contra borrado
        
        # Control de versiones
        self.numero_base_version = None  # Guarda el número base al cargar desde historial

        # imágenes por ítem
        self.item_images = {}           # {iid: ruta_origen}
        self.pending_image_path = None  # imagen seleccionada para nuevo ítem
        
        # Autoguardado y debounce
        self._autosave_job = None
        self._search_debounce_job = None
        self._plantillas_items = []  # Plantillas de items frecuentes

        # preview imagen
        self.preview_photo = None

        # Historial de notificaciones
        self.notification_log = []  # Lista de (timestamp, tipo, mensaje)

        self._load_config()

        # Encabezado cliente
        self.var_cliente = tk.StringVar()
        self.var_direccion = tk.StringVar()
        self.var_cliente_email = tk.StringVar()
        self.var_cliente_ruc = tk.StringVar()
        
        # Condiciones de venta (ahora en términos y condiciones)
        self.var_condicion_pago = tk.StringVar(value=self.terminos_predeterminados["condicion_pago"])
        self.var_validez = tk.StringVar(value=self.terminos_predeterminados["validez"])
        from datetime import date
        self.var_fecha_entrega = tk.StringVar(value=date.today().strftime("%Y-%m-%d"))

        # Totales
        self.var_subtotal = tk.StringVar(value="S/ 0.00")
        self.var_igv = tk.StringVar(value="S/ 0.00")
        self.var_total = tk.StringVar(value="S/ 0.00")
        self.var_igv_enabled = tk.BooleanVar(value=True)

        # Ítems
        self.var_cant = tk.StringVar()
        self.var_precio = tk.StringVar()
        self.item_editing = None

        # Listbox sugerencias
        self.lb_suggestions = None

        # Placeholders
        self.placeholder_cliente = "Nombre del cliente"
        self.placeholder_dir_cliente = "Dirección del cliente"
        self.placeholder_email_cliente = "correo@cliente.com"
        self.placeholder_cliente_ruc = "N° RUC"
        self.placeholder_cant = "Cantidad"
        self.placeholder_precio = "Precio"
        self.placeholder_desc = "Descripción detallada del producto (multilínea)..."
        self.placeholder_terms = "Términos y condiciones adicionales..."

        self._build_ui()
        self._init_placeholders()
        
        # Agregar binding de validación RUC DESPUÉS de los placeholders para que no sea sobrescrito
        self.ent_cliente_ruc.bind("<FocusOut>", self._validar_ruc_cliente, add="+")

    # ==== CONFIG FILE ==================================================
    def _load_config(self):
        data = load_json_safe(CONFIG_PATH, {})
        if not data:
            return
        
        self.tasa_igv = data.get("tasa_igv", 0.18)
        self.moneda = data.get("moneda", "SOLES")

        if "empresa" in data:
            self.empresa.update(data["empresa"])

        logo = data.get("logo_path")
        if logo and Path(logo).exists():
            self.logo_path = logo

        self.serie = data.get("serie", self.serie)
        try:
            self.correlativo = int(data.get("correlativo", self.correlativo))
        except ValueError:
            pass
        
        self.carpeta_cotizaciones = data.get("carpeta_cotizaciones", "")
        self.carpeta_referencias = data.get("carpeta_referencias", "")
        if "terminos_predeterminados" in data:
            self.terminos_predeterminados.update(data["terminos_predeterminados"])

        if "email_config" in data:
            self.email_config.update(data["email_config"])

    def _save_config(self):
        data = {
            "empresa": self.empresa,
            "logo_path": self.logo_path,
            "correlativo": self.correlativo,
            "tasa_igv": self.tasa_igv,
            "moneda": self.moneda,
            "carpeta_cotizaciones": self.carpeta_cotizaciones,
            "carpeta_referencias": self.carpeta_referencias,
            "terminos_predeterminados": self.terminos_predeterminados,
            "email_config": self.email_config,
        }
        save_json_safe(CONFIG_PATH, data)

    # ==== SMALL HELPERS ===============================================
    def _clean_var(self, var: tk.StringVar, placeholder: str) -> str:
        """Devuelve el valor sin placeholder ni espacios."""
        val = var.get().strip()
        if val == placeholder:
            return ""
        return val

    def _actualizar_numero_cot_display(self):
        """Actualiza el display del número de cotización."""
        numero = f"{self.serie}-{str(self.correlativo).zfill(5)}"
        self.var_numero_cot.set(numero)
    
    def _get_cotizaciones_dir(self) -> Path:
        """Obtiene la carpeta de cotizaciones (personalizada o predeterminada)."""
        if self.carpeta_cotizaciones and Path(self.carpeta_cotizaciones).exists():
            return Path(self.carpeta_cotizaciones)
        return get_base_dir() / "Cotizaciones"
    
    def _get_referencias_dir(self) -> Path:
        """Obtiene la carpeta de referencias (personalizada o predeterminada)."""
        if self.carpeta_referencias and Path(self.carpeta_referencias).exists():
            return Path(self.carpeta_referencias)
        return get_base_dir() / "Referencias"

    # ==== UI ROOT ======================================================
    def _build_ui(self):
        self._build_header()
        self._build_items()
        self._build_terms_and_totals()
        self._build_actions()

    # ---- Header cliente -----------------------------------------------
    def _build_header(self):
        frm = ttk.LabelFrame(self, text="Cliente")
        frm.pack(fill="x", padx=10, pady=5)
        
        # Configurar peso de columnas para que se expandan
        frm.columnconfigure(1, weight=1)  # Columna del RUC/Dirección
        frm.columnconfigure(3, weight=2)  # Columna Cliente/Email (más ancho)

        # Fila 0: RUC, Nombre del Cliente y Número de Cotización
        ttk.Label(frm, text="RUC:").grid(row=0, column=0, sticky="w", padx=(5, 5))
        self.ent_cliente_ruc = ttk.Entry(frm, textvariable=self.var_cliente_ruc, width=13)
        self.ent_cliente_ruc.grid(row=0, column=1, sticky="w", padx=(0, 20))
        # NOTA: El binding de FocusOut se agregará después de _init_placeholders para no ser sobrescrito
        
        ttk.Label(frm, text="Cliente:").grid(row=0, column=2, sticky="w", padx=(5, 5))
        self.ent_cliente = ttk.Entry(frm, textvariable=self.var_cliente, width=50)
        self.ent_cliente.grid(row=0, column=3, sticky="ew", padx=(0, 10))
        self.ent_cliente.bind("<KeyRelease>", self._on_cliente_key)
        self.ent_cliente.bind("<Down>", self._on_cliente_down)

        # Número de cotización completamente al borde derecho
        self.var_numero_cot = tk.StringVar(value="")
        frm_numero = ttk.LabelFrame(frm, text="Cotización", relief="solid")
        frm_numero.grid(row=0, column=4, rowspan=3, sticky="ne", padx=(10, 5), pady=(0, 5))
        self.lbl_numero_cot = ttk.Label(frm_numero, textvariable=self.var_numero_cot, 
                                       font=("Arial", 12, "bold"), foreground="blue")
        self.lbl_numero_cot.pack(padx=10, pady=5)
        self._actualizar_numero_cot_display()

        # Fila 1: Dirección y Email
        ttk.Label(frm, text="Dirección:").grid(row=1, column=0, sticky="w", padx=(5, 5))
        self.ent_dir_cliente = ttk.Entry(frm, textvariable=self.var_direccion, width=50)
        self.ent_dir_cliente.grid(row=1, column=1, sticky="ew", padx=(0, 20))
        
        ttk.Label(frm, text="Email:").grid(row=1, column=2, sticky="w", padx=(5, 5))
        self.ent_email_cliente = ttk.Entry(frm, textvariable=self.var_cliente_email, width=35)
        self.ent_email_cliente.grid(row=1, column=3, sticky="ew", padx=(0, 10))

        # Fila 2: Clientes frecuentes y botones
        ttk.Label(frm, text="Clientes frecuentes:").grid(row=2, column=0, sticky="w", padx=(5, 5))
        self.cmb_clientes = ttk.Combobox(frm, state="readonly", width=40)
        self.cmb_clientes.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(0, 20))
        self.cmb_clientes.bind("<<ComboboxSelected>>", self._on_cliente_frecuente_selected)
        
        # Botones para gestionar clientes frecuentes
        frm_botones = ttk.Frame(frm)
        frm_botones.grid(row=2, column=3, sticky="w", padx=(0, 10))
        ttk.Button(frm_botones, text="✏️ Editar", width=10, command=self._editar_cliente_frecuente).pack(side="left", padx=(0, 5))
        ttk.Button(frm_botones, text="❌ Limpiar", width=10, command=self._limpiar_cliente_frecuente).pack(side="left")

        self.lb_suggestions = tk.Listbox(frm, height=5)
        self.lb_suggestions.bind("<<ListboxSelect>>", self._on_suggestion_click)
        self.lb_suggestions.bind("<Return>", self._on_suggestion_enter)
        self.lb_suggestions.bind("<Escape>", self._hide_suggestions)
        self.lb_suggestions.bind("<Double-Button-1>", self._on_suggestion_click)
        self.lb_suggestions.bind("<Up>", self._on_suggestion_up)
        self.lb_suggestions.bind("<Down>", self._on_suggestion_down)

        self._cargar_clientes_frecuentes_en_combo()

    # ---- Ítems --------------------------------------------------------
    def _build_items(self):
        frame = ttk.LabelFrame(self, text="Ítems")
        frame.pack(fill="x", padx=10, pady=5)

        style = ttk.Style(self)
        style.configure("Treeview", rowheight=40)

        # ===== Zona superior: Treeview + preview =====
        top = ttk.Frame(frame)
        top.pack(fill="x")

        left = ttk.Frame(top)
        left.pack(side="left", fill="x", expand=True)

        self.tree = ttk.Treeview(
            left,
            height=6,
            columns=("img", "desc", "cant", "precio", "subtotal"),
            show="headings"
        )
        self.tree.heading("img", text="")
        self.tree.heading("desc", text="Descripción")
        self.tree.heading("cant", text="Cant.")
        self.tree.heading("precio", text="Precio")
        self.tree.heading("subtotal", text="Subtotal")

        self.tree.column("img", width=30, anchor="center")
        self.tree.column("desc", width=470)
        self.tree.column("cant", width=80, anchor="e")
        self.tree.column("precio", width=110, anchor="e")
        self.tree.column("subtotal", width=130, anchor="e")

        scroll_tree = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_tree.set)

        self.tree.pack(side="left", fill="x", expand=True)
        scroll_tree.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        # Preview
        preview_frame = ttk.LabelFrame(top, text="Vista previa imagen")
        preview_frame.pack(side="right", padx=5, pady=5)
        self.lbl_preview = ttk.Label(preview_frame, text="Sin imagen", anchor="center", width=25)
        self.lbl_preview.pack(fill="both", expand=True, padx=5, pady=5)

        # ===== Zona inferior: formulario + botones =====
        frm = ttk.Frame(frame)
        frm.pack(fill="x", pady=5)

        frm_desc = ttk.Frame(frm)
        frm_desc.grid(row=0, column=0, padx=2, pady=2, sticky="nsew")

        self.txt_desc = tk.Text(frm_desc, height=5, width=60, wrap="word")
        self.txt_desc.pack(side="left", fill="both", expand=True)

        scroll_desc = ttk.Scrollbar(frm_desc, orient="vertical", command=self.txt_desc.yview)
        scroll_desc.pack(side="right", fill="y")
        self.txt_desc.configure(yscrollcommand=scroll_desc.set)

        self.ent_cant = ttk.Entry(frm, textvariable=self.var_cant, width=10)
        self.ent_cant.grid(row=0, column=1, padx=2)
        self.ent_precio = ttk.Entry(frm, textvariable=self.var_precio, width=12)
        self.ent_precio.grid(row=0, column=2, padx=2)

        # Enter en Cant/Precio -> agregar ítem
        self.ent_cant.bind("<Return>", self._smart_enter)
        self.ent_precio.bind("<Return>", self._smart_enter)

        ttk.Button(frm, text="Imagen...", command=self.seleccionar_imagen_item).grid(
            row=0, column=3, padx=5
        )

        self.btn_add = ttk.Button(frm, text="Agregar", command=self.agregar_item)
        self.btn_add.grid(row=0, column=4, padx=5)

        ttk.Button(frm, text="Editar", command=self.editar_item).grid(row=0, column=5, padx=5)
        ttk.Button(frm, text="Eliminar", command=self.eliminar_item).grid(row=0, column=6, padx=5)
        ttk.Button(frm, text="📋 Plantilla", command=self.gestionar_plantillas).grid(row=0, column=7, padx=5)

        self.btn_cancel = ttk.Button(frm, text="Cancelar", command=self.cancelar_edicion)
        self.btn_cancel.grid(row=0, column=8, padx=5)
        self.btn_cancel["state"] = "disabled"

    # ---- Términos y Totales lado a lado ------------------------------
    def _build_terms_and_totals(self):
        # Contenedor principal horizontal
        container = ttk.Frame(self)
        container.pack(fill="both", padx=10, pady=5)

        # Frame izquierdo: Términos y Condiciones
        frame_terms = ttk.LabelFrame(container, text="Términos y Condiciones")
        frame_terms.pack(side="left", fill="both", expand=True, padx=(0, 5))

        # Nota sobre términos (más pequeño)
        self.txt_terms = tk.Text(frame_terms, height=2, wrap="word")
        self.txt_terms.pack(fill="both", expand=True, padx=5, pady=(5, 3))

        # Condiciones de venta en grid compacto (sin etiquetas separadas)
        frm_cond = ttk.Frame(frame_terms)
        frm_cond.pack(fill="x", padx=5, pady=3)

        ttk.Label(frm_cond, text="Pago:").grid(row=0, column=0, sticky="w", padx=(0, 5))
        ttk.Entry(frm_cond, textvariable=self.var_condicion_pago, width=35).grid(row=0, column=1, sticky="w", padx=(0, 10))

        ttk.Label(frm_cond, text="Validez:").grid(row=0, column=2, sticky="w", padx=(0, 5))
        ttk.Entry(frm_cond, textvariable=self.var_validez, width=18).grid(row=0, column=3, sticky="w", padx=(0, 10))

        ttk.Label(frm_cond, text="Entrega:").grid(row=0, column=4, sticky="w", padx=(0, 5))
        
        # Entry para fecha con botón de calendario personalizado
        frm_fecha = ttk.Frame(frm_cond)
        frm_fecha.grid(row=0, column=5, sticky="w")
        
        self.ent_fecha_entrega_widget = ttk.Entry(frm_fecha, textvariable=self.var_fecha_entrega, width=14)
        self.ent_fecha_entrega_widget.pack(side="left")
        
        btn_cal = ttk.Button(frm_fecha, text="📅", width=3, command=self._abrir_calendario)
        btn_cal.pack(side="left", padx=(2, 0))

        # Frame derecho: Totales
        frame_totals = ttk.LabelFrame(container, text="Totales")
        frame_totals.pack(side="right", fill="both", padx=(5, 0))

        # Crear checkbox con texto dinámico según la tasa IGV configurada
        porcentaje_igv = int(self.tasa_igv * 100)
        self.chk_igv = ttk.Checkbutton(
            frame_totals, text=f"Aplicar IGV {porcentaje_igv}%", variable=self.var_igv_enabled,
            command=self._refresh_totals
        )
        self.chk_igv.grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        ttk.Label(frame_totals, text="Subtotal:").grid(row=1, column=0, sticky="e", padx=(5, 2))
        ttk.Label(frame_totals, textvariable=self.var_subtotal).grid(row=1, column=1, sticky="w", padx=(2, 5))

        ttk.Label(frame_totals, text="IGV:").grid(row=2, column=0, sticky="e", padx=(5, 2))
        ttk.Label(frame_totals, textvariable=self.var_igv).grid(row=2, column=1, sticky="w", padx=(2, 5))

        ttk.Label(frame_totals, text="TOTAL:").grid(row=3, column=0, sticky="e", padx=(5, 2), pady=(5, 5))
        ttk.Label(frame_totals, textvariable=self.var_total, font=("Arial", 11, "bold")).grid(
            row=3, column=1, sticky="w", padx=(2, 5), pady=(5, 5)
        )

    # ---- Acciones -----------------------------------------------------
    def _build_actions(self):
        frm = ttk.Frame(self)
        frm.pack(fill="x", padx=10, pady=10)

        ttk.Button(frm, text="Configuración", command=self.abrir_configuracion).pack(side="left")
        ttk.Button(frm, text="Historial", command=self.abrir_historial).pack(side="left", padx=5)
        ttk.Button(frm, text="Exportar Excel (CSV)", command=self.exportar_historial_excel).pack(
            side="left", padx=5
        )
        ttk.Button(frm, text="Abrir carpeta de cotizaciones",
                   command=self.abrir_carpeta_cotizaciones).pack(side="left", padx=5)

        ttk.Button(frm, text="Enviar por correo", command=self.enviar_por_correo).pack(
            side="right"
        )
        ttk.Button(frm, text="Generar PDF", command=self.generar_pdf).pack(side="right", padx=5)
        
        # Barra de estado (clickeable)
        self.status_bar = ttk.Label(self, text="Listo", relief="sunken", anchor="w", 
                                    background="#f0f0f0", foreground="#555555")
        self.status_bar.pack(side="bottom", fill="x", padx=2, pady=2)
        self.status_bar.bind("<Button-1>", lambda e: self.abrir_log_notificaciones())

    # ==== BARRA DE ESTADO ==============================================
    def show_status(self, message, tipo="info", duracion=5000):
        """
        Muestra un mensaje en la barra de estado con efecto de parpadeo.
        tipo: 'success' (verde), 'error' (rojo), 'warning' (naranja), 'info' (azul)
        duracion: tiempo en milisegundos antes de volver a 'Listo' (0 = permanente)
        """
        from datetime import datetime
        colores = {
            "success": ("#d4edda", "#155724"),    # Verde claro fondo, verde oscuro texto
            "error": ("#f8d7da", "#721c24"),      # Rojo claro fondo, rojo oscuro texto
            "warning": ("#fff3cd", "#856404"),    # Amarillo claro fondo, naranja texto
            "info": ("#cce5ff", "#0052cc")        # Azul claro fondo, azul oscuro texto (MÁS LLAMATIVO)
        }
        bg, fg = colores.get(tipo, colores["info"])
        
        # Colores atenuados para el efecto de parpadeo (off)
        colores_atenuados = {
            "success": ("#e8f5e9", "#4caf50"),    # Verde muy claro, verde más suave
            "error": ("#ffebee", "#ef5350"),      # Rojo muy claro, rojo más suave
            "warning": ("#fffde7", "#fbc02d"),    # Amarillo muy claro, amarillo más suave
            "info": ("#e3f2fd", "#90caf9")        # Azul muy claro, azul más suave
        }
        bg_atenuado, fg_atenuado = colores_atenuados.get(tipo, colores_atenuados["info"])
        
        # Guardar en el historial de notificaciones
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.notification_log.append((timestamp, tipo, message))
        # Mantener solo los últimos 100 mensajes
        if len(self.notification_log) > 100:
            self.notification_log.pop(0)
        
        # Cancelar parpadeo anterior si existe
        if hasattr(self, '_blink_job') and self._blink_job:
            self.after_cancel(self._blink_job)
        
        # Mostrar el mensaje con efecto de parpadeo
        self._blink_count = 0
        self._blink_max = 8  # 8 parpadeos (on/off) para más visibilidad
        self._blink_message = message
        self._blink_bg = bg
        self._blink_fg = fg
        self._blink_bg_atenuado = bg_atenuado
        self._blink_fg_atenuado = fg_atenuado
        self._blink_timer_duration = duracion
        
        # Iniciar el parpadeo
        self._do_blink()
    
    def _do_blink(self):
        """Realiza el efecto de parpadeo en la barra de estado."""
        # Alternar entre visible e invisible
        if self._blink_count % 2 == 0:
            # Mostrar el mensaje con colores originales
            self.status_bar.config(text=self._blink_message, 
                                  background=self._blink_bg, 
                                  foreground=self._blink_fg)
        else:
            # Mostrar un estado atenuado pero aún visible
            self.status_bar.config(text=self._blink_message, 
                                  background=self._blink_bg_atenuado, 
                                  foreground=self._blink_fg_atenuado)
        
        self._blink_count += 1
        
        # Si aún hay parpadeos pendientes
        if self._blink_count < self._blink_max:
            # Esperar 250ms entre parpadeos
            self._blink_job = self.after(250, self._do_blink)
        else:
            # Cuando termina el parpadeo, mostrar el mensaje permanentemente por duracion
            self.status_bar.config(text=self._blink_message, 
                                  background=self._blink_bg, 
                                  foreground=self._blink_fg)
            
            if self._blink_timer_duration > 0:
                self._blink_job = self.after(self._blink_timer_duration, lambda: self.status_bar.config(
                    text="Listo", background="#f0f0f0", foreground="#555555"
                ))
    
    
    def show_success(self, message, duracion=5000):
        """Mensaje de éxito en verde."""
        self.show_status(message, "success", duracion)
    
    def show_error(self, message, duracion=8000):
        """Mensaje de error en rojo."""
        self.show_status(message, "error", duracion)
    
    def show_warning(self, message, duracion=6000):
        """Mensaje de advertencia en naranja."""
        self.show_status(message, "warning", duracion)
    
    def show_info(self, message, duracion=5000):
        """Mensaje informativo en gris."""
        self.show_status(message, "info", duracion)

    def abrir_log_notificaciones(self):
        """Abre una ventana con el historial de notificaciones."""
        if not self.notification_log:
            self.show_info("No hay notificaciones registradas.")
            return

        win = tk.Toplevel(self)
        win.title("Historial de Notificaciones")
        win.geometry("600x400")
        win.grab_set()

        # Text widget para mostrar las notificaciones
        text_widget = tk.Text(win, wrap="word", height=20, width=70)
        text_widget.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        # Configurar tags para colores
        text_widget.tag_config("success", foreground="#155724", background="#d4edda")
        text_widget.tag_config("error", foreground="#721c24", background="#f8d7da")
        text_widget.tag_config("warning", foreground="#856404", background="#fff3cd")
        text_widget.tag_config("info", foreground="#555555", background="#f0f0f0")
        text_widget.tag_config("timestamp", foreground="#666666")

        # Insertar notificaciones
        for timestamp, tipo, mensaje in reversed(self.notification_log):
            text_widget.insert("end", f"[{timestamp}] ", "timestamp")
            text_widget.insert("end", f"{mensaje}\n", tipo)

        text_widget.config(state="disabled")  # Solo lectura

        # Frame inferior con botones
        bottom_frame = ttk.Frame(win)
        bottom_frame.pack(fill="x", padx=10, pady=(5, 10))

        ttk.Button(bottom_frame, text="Limpiar", command=lambda: self._limpiar_log(text_widget, win)).pack(side="left", padx=5)
        ttk.Button(bottom_frame, text="Copiar todo", command=lambda: self._copiar_log(text_widget)).pack(side="left", padx=5)
        ttk.Button(bottom_frame, text="Cerrar", command=win.destroy).pack(side="right", padx=5)

    def _limpiar_log(self, text_widget, ventana):
        """Limpia el historial de notificaciones."""
        self.notification_log.clear()
        text_widget.config(state="normal")
        text_widget.delete("1.0", "end")
        text_widget.config(state="disabled")
        self.show_success("Historial de notificaciones limpiado.")

    def _copiar_log(self, text_widget):
        """Copia todo el contenido del log al portapapeles."""
        try:
            contenido = text_widget.get("1.0", "end")
            self.clipboard_clear()
            self.clipboard_append(contenido)
            self.show_success("Historial copiado al portapapeles.")
        except Exception as e:
            self.show_error(f"Error al copiar: {e}")



    # ==== PLACEHOLDERS =================================================
    def _init_entry_placeholder(self, entry, var, placeholder):
        var.set(placeholder)
        entry.configure(foreground="grey")

        def on_focus_in(event, e=entry, v=var, ph=placeholder):
            if v.get() == ph:
                v.set("")
                e.configure(foreground="black")

        def on_focus_out(event, e=entry, v=var, ph=placeholder):
            if not v.get().strip():
                v.set(ph)
                e.configure(foreground="grey")

        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)

    def _init_text_placeholder(self, widget, placeholder):
        widget.insert("1.0", placeholder)
        widget.configure(foreground="grey")

        def on_focus_in(event, w=widget, ph=placeholder):
            if w.get("1.0", "end").strip() == ph and str(w.cget("foreground")) == "grey":
                w.delete("1.0", "end")
                w.configure(foreground="black")

        def on_focus_out(event, w=widget, ph=placeholder):
            if not w.get("1.0", "end").strip():
                w.insert("1.0", ph)
                w.configure(foreground="grey")

        widget.bind("<FocusIn>", on_focus_in)
        widget.bind("<FocusOut>", on_focus_out)

    def _reset_text_placeholder(self, widget, placeholder):
        widget.delete("1.0", "end")
        widget.insert("1.0", placeholder)
        widget.configure(foreground="grey")

    def _init_placeholders(self):
        self._init_entry_placeholder(self.ent_cliente, self.var_cliente, self.placeholder_cliente)
        self._init_entry_placeholder(self.ent_dir_cliente, self.var_direccion, self.placeholder_dir_cliente)
        self._init_entry_placeholder(self.ent_email_cliente, self.var_cliente_email, self.placeholder_email_cliente)
        self._init_entry_placeholder(self.ent_cliente_ruc, self.var_cliente_ruc, self.placeholder_cliente_ruc)
        self._init_entry_placeholder(self.ent_cant, self.var_cant, self.placeholder_cant)
        self._init_entry_placeholder(self.ent_precio, self.var_precio, self.placeholder_precio)

        self._init_text_placeholder(self.txt_desc, self.placeholder_desc)
        # Solo aplicar placeholder en términos si no hay valor predeterminado
        if self.terminos_predeterminados["texto"]:
            self.txt_terms.insert("1.0", self.terminos_predeterminados["texto"])
        else:
            self._init_text_placeholder(self.txt_terms, self.placeholder_terms)

    # ==== CONFIG WINDOW ================================================
    def abrir_configuracion(self):
        win = tk.Toplevel(self)
        win.title("Configuración")
        win.geometry("500x450")
        win.grab_set()

        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        # Empresa
        frm_emp = ttk.Frame(nb)
        nb.add(frm_emp, text="Empresa")

        var_emp_nombre = tk.StringVar(value=self.empresa.get("nombre", ""))
        var_emp_ruc = tk.StringVar(value=self.empresa.get("ruc", ""))
        var_emp_dir = tk.StringVar(value=self.empresa.get("direccion", ""))

        ttk.Label(frm_emp, text="Nombre:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(frm_emp, textvariable=var_emp_nombre, width=35).grid(row=0, column=1, sticky="w")

        ttk.Label(frm_emp, text="RUC:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(frm_emp, textvariable=var_emp_ruc, width=20).grid(row=1, column=1, sticky="w")

        ttk.Label(frm_emp, text="Dirección:").grid(row=2, column=0, sticky="nw", padx=5, pady=5)
        ttk.Entry(frm_emp, textvariable=var_emp_dir, width=40).grid(row=2, column=1, sticky="w")

        # Mostrar serie (solo lectura, se calcula automáticamente)
        ttk.Label(frm_emp, text="Serie (automática):").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        ttk.Label(frm_emp, text=self.serie, foreground="blue", font=("Arial", 10, "bold")).grid(row=3, column=1, sticky="w")

        ttk.Label(frm_emp, text="Correlativo actual:").grid(row=4, column=0, sticky="w", padx=5, pady=5)
        ttk.Label(frm_emp, text=str(self.correlativo)).grid(row=4, column=1, sticky="w")

        var_logo = tk.StringVar(value=self.logo_path or "")
        ttk.Label(frm_emp, text="Logo:").grid(row=5, column=0, sticky="w", padx=5, pady=5)
        ent_logo = ttk.Entry(frm_emp, textvariable=var_logo, width=35, state="readonly")
        ent_logo.grid(row=5, column=1, sticky="w")

        def seleccionar_logo():
            path = filedialog.askopenfilename(
                parent=win,
                filetypes=[("Imágenes", "*.png *.jpg *.jpeg"), ("Todos", "*.*")]
            )
            if path:
                var_logo.set(path)

        ttk.Button(frm_emp, text="Cargar logo", command=seleccionar_logo).grid(
            row=5, column=2, padx=5, pady=5
        )

        # Correo
        frm_mail = ttk.Frame(nb)
        nb.add(frm_mail, text="Correo")

        var_srv = tk.StringVar(value=self.email_config.get("servidor", ""))
        var_port = tk.StringVar(value=str(self.email_config.get("puerto", 587)))
        var_user = tk.StringVar(value=self.email_config.get("usuario", ""))
        var_pass = tk.StringVar(value=self.email_config.get("password", ""))
        var_tls = tk.BooleanVar(value=self.email_config.get("usar_tls", True))

        ttk.Label(frm_mail, text="Servidor SMTP:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(frm_mail, textvariable=var_srv, width=30).grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(frm_mail, text="Puerto:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(frm_mail, textvariable=var_port, width=10).grid(row=1, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(frm_mail, text="Usuario:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(frm_mail, textvariable=var_user, width=30).grid(row=2, column=1, padx=5, pady=5)

        ttk.Label(frm_mail, text="Password:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(frm_mail, textvariable=var_pass, width=30, show="*").grid(row=3, column=1, padx=5, pady=5)

        ttk.Checkbutton(frm_mail, text="Usar TLS", variable=var_tls).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=5, pady=5
        )

        # Pestaña Totales
        frm_tot = ttk.Frame(nb)
        nb.add(frm_tot, text="Totales")

        ttk.Label(frm_tot, text="Tasa IGV (%)", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", padx=10, pady=10)
        var_igv = tk.StringVar(value=str(int(self.tasa_igv * 100)))
        ttk.Label(frm_tot, text="Porcentaje de IGV:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        ttk.Entry(frm_tot, textvariable=var_igv, width=10).grid(row=1, column=1, sticky="w", padx=5)
        ttk.Label(frm_tot, text="%").grid(row=1, column=2, sticky="w")

        ttk.Label(frm_tot, text="Moneda", font=("Arial", 10, "bold")).grid(row=2, column=0, sticky="w", padx=10, pady=(20, 10))
        var_moneda = tk.StringVar(value=self.moneda)
        ttk.Label(frm_tot, text="Tipo de moneda:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        cmb_moneda = ttk.Combobox(frm_tot, textvariable=var_moneda, state="readonly", width=15, values=["SOLES", "DOLARES", "EUROS"])
        cmb_moneda.grid(row=3, column=1, sticky="w", padx=5)

        # Pestaña Rutas
        frm_rutas = ttk.Frame(nb)
        nb.add(frm_rutas, text="Rutas")

        ttk.Label(frm_rutas, text="Configuración de carpetas", font=("Arial", 10, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=10)
        ttk.Label(frm_rutas, text="Dejar vacío para usar la carpeta predeterminada (junto al ejecutable)", foreground="gray").grid(row=1, column=0, columnspan=3, sticky="w", padx=10, pady=(0, 10))

        var_carpeta_cot = tk.StringVar(value=self.carpeta_cotizaciones)
        var_carpeta_ref = tk.StringVar(value=self.carpeta_referencias)

        ttk.Label(frm_rutas, text="Carpeta Cotizaciones:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        ent_carpeta_cot = ttk.Entry(frm_rutas, textvariable=var_carpeta_cot, width=35, state="readonly")
        ent_carpeta_cot.grid(row=2, column=1, sticky="w", padx=5)

        def seleccionar_carpeta_cot():
            path = filedialog.askdirectory(parent=win, title="Seleccionar carpeta para Cotizaciones")
            if path:
                var_carpeta_cot.set(path)

        ttk.Button(frm_rutas, text="Explorar", command=seleccionar_carpeta_cot).grid(row=2, column=2, padx=5)
        ttk.Button(frm_rutas, text="Limpiar", command=lambda: var_carpeta_cot.set("")).grid(row=2, column=3, padx=5)

        ttk.Label(frm_rutas, text="Carpeta Referencias:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        ent_carpeta_ref = ttk.Entry(frm_rutas, textvariable=var_carpeta_ref, width=35, state="readonly")
        ent_carpeta_ref.grid(row=3, column=1, sticky="w", padx=5)

        def seleccionar_carpeta_ref():
            path = filedialog.askdirectory(parent=win, title="Seleccionar carpeta para Referencias")
            if path:
                var_carpeta_ref.set(path)

        ttk.Button(frm_rutas, text="Explorar", command=seleccionar_carpeta_ref).grid(row=3, column=2, padx=5)
        ttk.Button(frm_rutas, text="Limpiar", command=lambda: var_carpeta_ref.set("")).grid(row=3, column=3, padx=5)

        # Mostrar rutas actuales
        ttk.Label(frm_rutas, text="Ruta actual Cotizaciones:", font=("Arial", 9)).grid(row=4, column=0, sticky="w", padx=10, pady=(20, 5))
        lbl_ruta_cot_actual = ttk.Label(frm_rutas, text=str(self._get_cotizaciones_dir()), foreground="blue", wraplength=400)
        lbl_ruta_cot_actual.grid(row=5, column=0, columnspan=4, sticky="w", padx=20)

        ttk.Label(frm_rutas, text="Ruta actual Referencias:", font=("Arial", 9)).grid(row=6, column=0, sticky="w", padx=10, pady=(10, 5))
        lbl_ruta_ref_actual = ttk.Label(frm_rutas, text=str(self._get_referencias_dir()), foreground="blue", wraplength=400)
        lbl_ruta_ref_actual.grid(row=7, column=0, columnspan=4, sticky="w", padx=20)

        # Pestaña Términos
        frm_terms = ttk.Frame(nb)
        nb.add(frm_terms, text="Términos")

        ttk.Label(frm_terms, text="Valores predeterminados para Términos y Condiciones", font=("Arial", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=10)
        ttk.Label(frm_terms, text="Estos valores se usarán al crear una nueva cotización", foreground="gray").grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 10))

        var_cond_pago_default = tk.StringVar(value=self.terminos_predeterminados["condicion_pago"])
        var_validez_default = tk.StringVar(value=self.terminos_predeterminados["validez"])

        ttk.Label(frm_terms, text="Términos y condiciones:").grid(row=2, column=0, sticky="nw", padx=10, pady=5)
        txt_terms_config = tk.Text(frm_terms, height=4, width=50, wrap="word")
        txt_terms_config.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        txt_terms_config.insert("1.0", self.terminos_predeterminados["texto"])

        ttk.Label(frm_terms, text="Condición de pago:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        ttk.Entry(frm_terms, textvariable=var_cond_pago_default, width=40).grid(row=3, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(frm_terms, text="Validez de oferta:").grid(row=4, column=0, sticky="w", padx=10, pady=5)
        ttk.Entry(frm_terms, textvariable=var_validez_default, width=25).grid(row=4, column=1, sticky="w", padx=5, pady=5)

        # Pestaña Avanzado
        frm_adv = ttk.Frame(nb)
        nb.add(frm_adv, text="Avanzado")

        ttk.Label(frm_adv, text="Restaurar de fábrica", font=("Arial", 12, "bold")).pack(padx=10, pady=10, anchor="w")
        ttk.Label(frm_adv, text="Esta acción eliminará todos los datos (historial, configuración, etc.)").pack(padx=10, anchor="w")
        ttk.Label(frm_adv, text="Escribe RESTAURAR para confirmar:").pack(padx=10, pady=(20, 5), anchor="w")

        var_restore = tk.StringVar()
        ttk.Entry(frm_adv, textvariable=var_restore, width=30).pack(padx=10, pady=5)

        def restaurar_fabrica():
            if var_restore.get() != "RESTAURAR":
                self.show_warning("Texto de confirmación incorrecto.")
                return

            if messagebox.askyesno("Confirmar", "¿Deseas restaurar la aplicación de fábrica?"):
                try:
                    base_dir = get_base_dir()
                    # Eliminar archivos de configuración
                    for file in ["config_cotizador.json", "historial_cotizaciones.json", "catalog.json"]:
                        f = Path(file)
                        if f.exists():
                            f.unlink()
                    # Eliminar carpetas (predeterminadas y configuradas)
                    import shutil
                    carpetas_a_eliminar = [
                        base_dir / "Cotizaciones",
                        base_dir / "Referencias"
                    ]
                    if self.carpeta_cotizaciones:
                        carpetas_a_eliminar.append(Path(self.carpeta_cotizaciones))
                    if self.carpeta_referencias:
                        carpetas_a_eliminar.append(Path(self.carpeta_referencias))
                    
                    for p in carpetas_a_eliminar:
                        if p.exists():
                            shutil.rmtree(p)
                    self.show_success("Aplicación restaurada. Por favor, reinicia.")
                    win.destroy()
                except Exception as e:
                    self.show_error(f"No se pudo restaurar: {e}")

        ttk.Button(frm_adv, text="Restaurar", command=restaurar_fabrica).pack(pady=10)

        def guardar_config():
            self.empresa["nombre"] = var_emp_nombre.get().strip()
            ruc_ingresado = var_emp_ruc.get().strip()
            
            # Validar RUC si se ingresó uno
            if ruc_ingresado and not validar_ruc_peruano(ruc_ingresado):
                respuesta = messagebox.askyesno(
                    "RUC inválido",
                    f"El RUC '{ruc_ingresado}' no parece ser válido.\n\n¿Desea guardarlo de todas formas?",
                    icon='warning'
                )
                if not respuesta:
                    return
            
            self.empresa["ruc"] = ruc_ingresado
            self.empresa["direccion"] = var_emp_dir.get().strip()

            logo_val = var_logo.get().strip()
            self.logo_path = logo_val or None

            try:
                puerto = int(var_port.get())
            except ValueError:
                self.show_warning("Puerto inválido.")
                return
            
            # Validar y guardar tasa IGV
            try:
                igv_percent = float(var_igv.get().strip())
                if igv_percent < 0 or igv_percent > 100:
                    self.show_warning("La tasa IGV debe estar entre 0 y 100.")
                    return
                self.tasa_igv = igv_percent / 100.0
            except ValueError:
                self.show_warning("Tasa IGV inválida.")
                return
            
            # Guardar moneda
            self.moneda = var_moneda.get()
            
            # Guardar rutas de carpetas
            self.carpeta_cotizaciones = var_carpeta_cot.get().strip()
            self.carpeta_referencias = var_carpeta_ref.get().strip()
            
            # Guardar términos predeterminados
            self.terminos_predeterminados["texto"] = txt_terms_config.get("1.0", "end-1c")
            self.terminos_predeterminados["condicion_pago"] = var_cond_pago_default.get()
            self.terminos_predeterminados["validez"] = var_validez_default.get()

            self.email_config["servidor"] = var_srv.get().strip()
            self.email_config["puerto"] = puerto
            self.email_config["usuario"] = var_user.get().strip()
            self.email_config["password"] = var_pass.get().strip()
            self.email_config["usar_tls"] = var_tls.get()

            self._save_config()
            
            # Actualizar valores en la ventana principal
            self.var_condicion_pago.set(self.terminos_predeterminados["condicion_pago"])
            self.var_validez.set(self.terminos_predeterminados["validez"])
            self.txt_terms.delete("1.0", "end")
            if self.terminos_predeterminados["texto"]:
                self.txt_terms.insert("1.0", self.terminos_predeterminados["texto"])
                self.txt_terms.configure(foreground="black")
            else:
                self._reset_text_placeholder(self.txt_terms, self.placeholder_terms)
            
            # Actualizar texto del checkbox IGV
            porcentaje_igv = int(self.tasa_igv * 100)
            self.chk_igv.config(text=f"Aplicar IGV {porcentaje_igv}%")
            
            self._refresh_totals()  # Actualizar totales con nueva configuración
            self.show_success("Configuración guardada correctamente.")
            win.destroy()

        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill="x", pady=5)
        ttk.Button(btn_frame, text="Guardar", command=guardar_config).pack(side="right", padx=10)
        ttk.Button(btn_frame, text="Cancelar", command=win.destroy).pack(side="right")

    # ==== NUMERACIÓN ===================================================
    def _next_numero_cotizacion(self):
        # Si hay un numero_base_version, significa que se está creando una nueva versión
        if self.numero_base_version:
            # Extraer el número base sin versión
            numero_base = self.numero_base_version
            
            # Buscar todas las versiones existentes de este número en el historial
            hist_data = load_json_safe(HIST_PATH, [])
            versiones_existentes = []
            
            for r in hist_data:
                num = r.get("numero", "")
                # Verificar si el número coincide con el base
                if num.startswith(numero_base):
                    # Extraer versión si existe
                    if "-V" in num:
                        try:
                            version = int(num.split("-V")[1])
                            versiones_existentes.append(version)
                        except (IndexError, ValueError):
                            pass
                    else:
                        # Sin versión explícita = V1
                        versiones_existentes.append(1)
            
            # Determinar la siguiente versión
            if versiones_existentes:
                siguiente_version = max(versiones_existentes) + 1
            else:
                siguiente_version = 2  # Si no hay versiones, esta es la V2
            
            numero = f"{numero_base}-V{siguiente_version}"
            # Limpiar el numero_base_version después de usarlo
            self.numero_base_version = None
        else:
            # Cotización nueva normal (sin versión explícita)
            numero = f"{self.serie}-{str(self.correlativo).zfill(5)}"
            self.correlativo += 1
            self._save_config()
        
        self._actualizar_numero_cot_display()
        return numero

    # ==== ÍTEMS ========================================================
    def _smart_enter(self, event):
        widget = self.focus_get()
        if widget is self.txt_desc:
            return
        self.agregar_item()
        return "break"

    def seleccionar_imagen_item(self):
        path = filedialog.askopenfilename(
            filetypes=[
                ("Imágenes", "*.png *.jpg *.jpeg *.webp *.bmp"),
                ("Todos", "*.*"),
            ]
        )
        if not path:
            return

        base_dir = get_base_dir()
        ref_dir = base_dir / "Referencias"
        ref_dir.mkdir(exist_ok=True)

        png_name = f"TMP_{uuid.uuid4().hex}.png"
        ref_path = ref_dir / png_name

        try:
            from PIL import Image
            im = Image.open(path)
            im = im.convert("RGB")
            im.save(ref_path, format="PNG")
        except Exception as e:
            try:
                shutil.copyfile(path, ref_path)
            except Exception as e2:
                self.show_error(f"No se pudo preparar la imagen: {str(e)[:50]}")
                return

        if self.item_editing:
            old_path = self.item_images.get(self.item_editing)
            if old_path:
                try:
                    p = Path(old_path)
                    if p.exists():
                        p.unlink()
                except Exception:
                    pass

            self.item_images[self.item_editing] = str(ref_path)
            vals = list(self.tree.item(self.item_editing, "values"))
            if vals:
                vals[0] = "📷"
                self.tree.item(self.item_editing, values=vals)
        else:
            self.pending_image_path = str(ref_path)

        self.show_success("Imagen asociada al ítem.")

    def agregar_item(self):
        desc = self.txt_desc.get("1.0", "end").strip()
        if desc == self.placeholder_desc:
            desc = ""
        if not desc:
            self.show_warning("La descripción no puede estar vacía.")
            return

        try:
            cant = float(self.var_cant.get())
            precio = float(self.var_precio.get())
        except ValueError:
            self.show_warning("Cantidad o precio inválidos.")
            return

        subtotal = cant * precio

        if self.item_editing:
            icon = "📷" if self.item_images.get(self.item_editing) else ""
            self.tree.item(
                self.item_editing,
                values=(icon, desc, f"{cant:.2f}", f"{precio:.2f}", f"{subtotal:.2f}")
            )
        else:
            icon = "📷" if self.pending_image_path else ""
            iid = self.tree.insert(
                "", "end",
                values=(icon, desc, f"{cant:.2f}", f"{precio:.2f}", f"{subtotal:.2f}")
            )
            if self.pending_image_path:
                self.item_images[iid] = self.pending_image_path
                self.pending_image_path = None

        self._reset_form()
        self._refresh_totals()

    def editar_item(self):
        sel = self.tree.selection()
        if not sel:
            self.show_info("Selecciona un ítem para editar.")
            return

        item = sel[0]
        vals = self.tree.item(item)["values"]
        desc = vals[1]
        cant = vals[2]
        precio = vals[3]

        self._reset_text_placeholder(self.txt_desc, self.placeholder_desc)
        self.txt_desc.delete("1.0", "end")
        self.txt_desc.configure(foreground="black")
        self.txt_desc.insert("1.0", desc)

        self.var_cant.set(cant)
        self.var_precio.set(precio)
        self.ent_cant.configure(foreground="black")
        self.ent_precio.configure(foreground="black")

        self.item_editing = item
        self.btn_add["text"] = "Guardar"
        self.btn_cancel["state"] = "normal"
        self.tree.tag_configure("edit", background="#FFF3CD")
        self.tree.item(item, tags=("edit",))

        self.pending_image_path = None

    def cancelar_edicion(self):
        if self.item_editing:
            self.tree.item(self.item_editing, tags=())
        self._reset_form()

    def eliminar_item(self):
        sel = self.tree.selection()
        if not sel:
            self.show_info("Selecciona un ítem para eliminar.")
            return

        iid = sel[0]

        img_path = self.item_images.pop(iid, None)
        if img_path:
            try:
                p = Path(img_path)
                if p.exists():
                    p.unlink()
            except Exception:
                pass

        if getattr(self, "item_editing", None) == iid:
            self.item_editing = None

        self.tree.delete(iid)

        self._reset_form()
        self._refresh_totals()
        self._clear_preview()

    def _reset_form(self):
        self._reset_text_placeholder(self.txt_desc, self.placeholder_desc)

        self.var_cant.set(self.placeholder_cant)
        self.ent_cant.configure(foreground="grey")

        self.var_precio.set(self.placeholder_precio)
        self.ent_precio.configure(foreground="grey")

        self.btn_add["text"] = "Agregar"
        self.btn_cancel["state"] = "disabled"

        if self.item_editing and isinstance(self.item_editing, (str, int)):
            try:
                if self.tree.exists(self.item_editing):
                    self.tree.item(self.item_editing, tags=())
            except Exception:
                pass

        self.item_editing = None
        self.pending_image_path = None

    def _refresh_totals(self):
        items = self.tree.get_children()
        subtotales = [
            float(self.tree.item(i)["values"][4]) for i in items
        ] if items else []
        subtotal = sum(subtotales)

        igv = subtotal * self.tasa_igv if self.var_igv_enabled.get() else 0.0
        total = subtotal + igv

        # Obtener símbolo de moneda
        simbolo = self._get_simbolo_moneda()
        
        self.var_subtotal.set(f"{simbolo} {subtotal:,.2f}")
        self.var_igv.set(f"{simbolo} {igv:,.2f}")
        self.var_total.set(f"{simbolo} {total:,.2f}")
        
        # Activar autoguardado cada vez que cambian los totales
        self._programar_autoguardado()
    
    def _programar_autoguardado(self):
        """Programa autoguardado de borrador cada 30 segundos."""
        if self._autosave_job:
            self.after_cancel(self._autosave_job)
        self._autosave_job = self.after(30000, self._autoguardar_borrador)
    
    def _autoguardar_borrador(self):
        """Guarda un borrador temporal de la cotización actual."""
        try:
            # Solo guardar si hay items o datos del cliente
            if not self.tree.get_children() and not self.var_cliente.get().strip():
                return
            
            borrador = {
                "timestamp": datetime.now().isoformat(),
                "cliente": self.var_cliente.get(),
                "email": self.var_cliente_email.get(),
                "direccion": self.var_direccion.get(),
                "condicion_pago": self.var_condicion_pago.get(),
                "validez": self.var_validez.get(),
                "fecha_entrega": self.var_fecha_entrega.get(),
                "moneda": self.moneda,
                "tasa_igv": self.tasa_igv,
                "igv_enabled": self.var_igv_enabled.get(),
                "items": []
            }
            
            # Guardar items
            for item_id in self.tree.get_children():
                vals = self.tree.item(item_id)["values"]
                borrador["items"].append({
                    "descripcion": vals[1],
                    "cantidad": vals[2],
                    "precio": vals[3],
                    "subtotal": vals[4],
                    "imagen": self.item_images.get(item_id, "")
                })
            
            # Guardar en archivo temporal
            borrador_path = get_base_dir() / "borrador_cotizacion.json"
            save_json_safe(borrador_path, borrador)
            
        except Exception:
            pass  # Silencioso, no interrumpir al usuario
    
    def gestionar_plantillas(self):
        """Ventana para gestionar plantillas de items frecuentes."""
        win = tk.Toplevel(self)
        win.title("Plantillas de Items")
        win.geometry("600x400")
        win.transient(self)
        win.grab_set()
        
        # Cargar plantillas
        plantillas_path = get_base_dir() / "plantillas_items.json"
        plantillas = load_json_safe(plantillas_path, [])
        
        # Frame superior con lista
        frm_top = ttk.Frame(win)
        frm_top.pack(fill="both", expand=True, padx=10, pady=10)
        
        tree = ttk.Treeview(frm_top, columns=("desc", "cant", "precio"), show="headings", height=10)
        tree.heading("desc", text="Descripción")
        tree.heading("cant", text="Cantidad")
        tree.heading("precio", text="Precio Unit.")
        tree.column("desc", width=350)
        tree.column("cant", width=100)
        tree.column("precio", width=100)
        tree.pack(side="left", fill="both", expand=True)
        
        scroll = ttk.Scrollbar(frm_top, orient="vertical", command=tree.yview)
        scroll.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scroll.set)
        
        # Cargar plantillas en el tree
        for p in plantillas:
            tree.insert("", "end", values=(p.get("descripcion", ""), p.get("cantidad", ""), p.get("precio", "")))
        
        # Frame inferior con botones
        frm_bot = ttk.Frame(win)
        frm_bot.pack(fill="x", padx=10, pady=10)
        
        def usar_plantilla():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("Sin selección", "Selecciona una plantilla primero.")
                return
            
            idx = tree.index(sel[0])
            plantilla = plantillas[idx]
            
            # Agregar el item a la cotización actual
            self._reset_text_placeholder(self.txt_desc, self.placeholder_desc)
            self.txt_desc.delete("1.0", "end")
            self.txt_desc.insert("1.0", plantilla.get("descripcion", ""))
            self.txt_desc.configure(foreground="black")
            
            self.var_cant.set(plantilla.get("cantidad", "1"))
            self.ent_cant.configure(foreground="black")
            
            self.var_precio.set(plantilla.get("precio", "0.00"))
            self.ent_precio.configure(foreground="black")
            
            win.destroy()
            self.show_success("Plantilla cargada. Haz clic en 'Agregar' para confirmar.")
        
        def guardar_como_plantilla():
            # Guardar el item actual como plantilla
            desc_actual = self.txt_desc.get("1.0", "end").strip()
            if not desc_actual or desc_actual == self.placeholder_desc:
                messagebox.showwarning("Sin datos", "Primero completa la descripción del item.")
                return
            
            cant_actual = self.var_cant.get().strip()
            precio_actual = self.var_precio.get().strip()
            
            nueva_plantilla = {
                "descripcion": desc_actual,
                "cantidad": cant_actual if cant_actual != self.placeholder_cant else "1",
                "precio": precio_actual if precio_actual != self.placeholder_precio else "0.00"
            }
            
            plantillas.append(nueva_plantilla)
            save_json_safe(plantillas_path, plantillas)
            tree.insert("", "end", values=(nueva_plantilla["descripcion"], nueva_plantilla["cantidad"], nueva_plantilla["precio"]))
            self.show_success("Plantilla guardada.")
        
        def eliminar_plantilla():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("Sin selección", "Selecciona una plantilla para eliminar.")
                return
            
            idx = tree.index(sel[0])
            plantillas.pop(idx)
            save_json_safe(plantillas_path, plantillas)
            tree.delete(sel[0])
            self.show_success("Plantilla eliminada.")
        
        ttk.Button(frm_bot, text="✅ Usar plantilla", command=usar_plantilla).pack(side="left", padx=5)
        ttk.Button(frm_bot, text="💾 Guardar actual como plantilla", command=guardar_como_plantilla).pack(side="left", padx=5)
        ttk.Button(frm_bot, text="❌ Eliminar", command=eliminar_plantilla).pack(side="left", padx=5)
        ttk.Button(frm_bot, text="Cerrar", command=win.destroy).pack(side="right", padx=5)
    
    def _get_simbolo_moneda(self):
        """Retorna el símbolo de la moneda configurada (desde cache)."""
        # Recalcular cache solo si cambió la moneda
        # Usa constante global SIMBOLOS_MONEDA en lugar de recrear dict
        nuevo_simbolo = SIMBOLOS_MONEDA.get(self.moneda, "S/")
        if nuevo_simbolo != self._simbolo_moneda_cache:
            self._simbolo_moneda_cache = nuevo_simbolo
        return self._simbolo_moneda_cache

    # ==== PREVIEW IMAGEN ===============================================
    def _on_tree_select(self, event):
        sel = self.tree.selection()
        if not sel:
            self._clear_preview()
            return
        iid = sel[0]
        img_src = self.item_images.get(iid)
        if not img_src or not Path(img_src).exists():
            self._clear_preview()
            return

        try:
            from PIL import Image, ImageTk
        except ImportError:
            self.lbl_preview.configure(text="Instala Pillow para ver la imagen.", image="")
            self.preview_photo = None
            return

        try:
            im = Image.open(img_src)
            max_w, max_h = 220, 160
            im.thumbnail((max_w, max_h))
            self.preview_photo = ImageTk.PhotoImage(im)
            self.lbl_preview.configure(image=self.preview_photo, text="")
        except Exception:
            self._clear_preview()

    def _clear_preview(self):
        self.lbl_preview.configure(image="", text="Sin imagen")
        self.preview_photo = None

    # ==== HISTORIAL / CLIENTES ========================================
    def _guardar_en_historial(self, numero, ruta_pdf, subtotal, igv, total, estado):
        cliente = self._clean_var(self.var_cliente, self.placeholder_cliente)
        email = self._clean_var(self.var_cliente_email, self.placeholder_email_cliente)
        direccion = self._clean_var(self.var_direccion, self.placeholder_dir_cliente)
        ruc = self._clean_var(self.var_cliente_ruc, self.placeholder_cliente_ruc)

        # Recopilar items con sus imágenes
        items = []
        for item_id in self.tree.get_children():
            icon, desc, cant, precio, subtotal_item = self.tree.item(item_id)["values"]
            img_src = self.item_images.get(item_id, "")
            items.append({
                "descripcion": desc,
                "cantidad": cant,
                "precio": precio,
                "subtotal": subtotal_item,
                "imagen": str(img_src) if img_src else ""
            })
        
        # Extraer versión del número si existe
        numero_sin_version, version = parse_numero_version(numero)

        registro = {
            "numero": numero,
            "numero_base": numero_sin_version,
            "version": version,
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "fecha_entrega": self.var_fecha_entrega.get(),
            "cliente": cliente,
            "email": email,
            "direccion_cliente": direccion,
            "ruc_cliente": ruc,
            "condicion_pago": self.var_condicion_pago.get(),
            "validez": self.var_validez.get(),
            "items": items,
            "subtotal": float(f"{subtotal:.2f}"),
            "igv": float(f"{igv:.2f}"),
            "total": float(f"{total:.2f}"),
            "tasa_igv": self.tasa_igv,
            "moneda": self.moneda,
            "igv_enabled": self.var_igv_enabled.get(),
            "ruta_pdf": Path(ruta_pdf).name,  # Guardar solo el nombre del archivo (ruta relativa)
            "estado": estado,
        }
        data = load_json_safe(HIST_PATH, [])
        data.append(registro)
        save_json_safe(HIST_PATH, data)

        self._cargar_clientes_frecuentes_en_combo()

    def _cargar_clientes_frecuentes_en_combo(self):
        self.clientes_hist = {}
        data = load_json_safe(HIST_PATH, [])
        if not data:
            self.cmb_clientes["values"] = []
            return

        for r in data:
            nombre = r.get("cliente", "").strip()
            if not nombre:
                continue
            self.clientes_hist[nombre.lower()] = r

        nombres = sorted({r["cliente"] for r in self.clientes_hist.values()})
        self.cmb_clientes["values"] = nombres

    def _rellenar_cliente_por_nombre(self, nombre):
        if not nombre:
            return
        reg = self.clientes_hist.get(nombre.lower())
        if not reg:
            return
        self.var_cliente.set(reg.get("cliente", ""))
        self.ent_cliente.configure(foreground="black")
        self.var_cliente_email.set(reg.get("email", ""))
        self.ent_email_cliente.configure(foreground="black")
        self.var_direccion.set(reg.get("direccion_cliente", ""))
        self.ent_dir_cliente.configure(foreground="black")
        self.var_cliente_ruc.set(reg.get("ruc_cliente", ""))
        self.ent_cliente_ruc.configure(foreground="black")

    def _on_cliente_frecuente_selected(self, event):
        nombre = self.cmb_clientes.get()
        self._rellenar_cliente_por_nombre(nombre)
        # Guardar el cliente seleccionado para proteger contra borrado
        self.cliente_seleccionado = nombre.lower() if nombre else None
    
    def _validar_ruc_cliente(self, event=None):
        """Valida el RUC del cliente cuando pierde el foco y consulta API."""
        ruc = self.var_cliente_ruc.get().strip()
        
        # Si está vacío o es el placeholder, no validar
        if not ruc or ruc == self.placeholder_cliente_ruc:
            return
        
        # Validar formato y dígito verificador
        if not validar_ruc_peruano(ruc):
            self.show_warning(f"⚠️ El RUC '{ruc}' no parece ser válido.\nVerifica que tenga 11 dígitos y sea correcto.")
            return
        
        # Consultar API para obtener datos de la empresa
        self._consultar_ruc_api(ruc)
    
    def _consultar_ruc_api(self, ruc):
        """Consulta la API de SUNAT para obtener datos del RUC."""
        import urllib.request
        import urllib.error
        import json
        import ssl
        
        try:
            # Mostrar mensaje de consulta
            self.show_info("Consultando RUC en SUNAT...")
            self.update()  # Forzar actualización de UI
            
            url = f"https://dniruc.apisperu.com/api/v1/ruc/{ruc}?token=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6ImRnYXJib2xlZGFAZ21haWwuY29tIn0.rXW9BEWvNp0sStv33XImkUudScHfq63_LxL-Yw8mvG8"
            
            # Crear contexto SSL que no verifique certificados
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # Realizar petición con timeout
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0')
            
            with urllib.request.urlopen(req, timeout=5, context=ssl_context) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                # Extraer datos (intentar múltiples variantes de nombres de campos)
                razon_social = (data.get('razonSocial') or 
                               data.get('nombre') or 
                               data.get('nombreORazonSocial') or '')
                
                direccion = (data.get('direccion') or 
                            data.get('direccionCompleta') or '')
                
                # Rellenar campos siempre (sobrescribir si hay datos)
                if razon_social:
                    self.var_cliente.set(razon_social)
                    self.ent_cliente.configure(foreground="black")
                
                if direccion:
                    self.var_direccion.set(direccion)
                    self.ent_dir_cliente.configure(foreground="black")
                
                # Forzar actualización de la UI
                self.update_idletasks()
                self.update()
                
                if razon_social or direccion:
                    self.show_success(f"✅ Datos obtenidos: {razon_social}")
                else:
                    self.show_warning(f"⚠️ No se encontraron datos para el RUC {ruc}")
                    
        except urllib.error.HTTPError as e:
            if e.code == 404:
                self.show_warning(f"⚠️ RUC {ruc} no encontrado en SUNAT")
            else:
                self.show_warning(f"⚠️ Error al consultar RUC: HTTP {e.code}")
        except urllib.error.URLError:
            self.show_warning("⚠️ Sin conexión a internet. No se pudo consultar el RUC.")
        except Exception as e:
            self.show_warning(f"⚠️ Error al consultar RUC: {str(e)[:50]}")

    def _editar_cliente_frecuente(self):
        """Abre ventana para editar el cliente frecuente seleccionado."""
        nombre = self.cmb_clientes.get()
        if not nombre:
            self.show_info("Selecciona un cliente frecuente para editar.")
            return
        
        reg = self.clientes_hist.get(nombre.lower())
        if not reg:
            self.show_error("No se encontró el cliente.")
            return
        
        # Ventana de edición
        win = tk.Toplevel(self)
        win.title(f"Editar Cliente: {nombre}")
        win.geometry("500x300")
        win.grab_set()
        
        # Campos
        var_nombre = tk.StringVar(value=reg.get("cliente", ""))
        var_email = tk.StringVar(value=reg.get("email", ""))
        var_dir = tk.StringVar(value=reg.get("direccion_cliente", ""))
        
        ttk.Label(win, text="Nombre:").grid(row=0, column=0, sticky="w", padx=10, pady=10)
        ttk.Entry(win, textvariable=var_nombre, width=40).grid(row=0, column=1, sticky="w", padx=10)
        
        ttk.Label(win, text="Email:").grid(row=1, column=0, sticky="w", padx=10, pady=10)
        ttk.Entry(win, textvariable=var_email, width=40).grid(row=1, column=1, sticky="w", padx=10)
        
        ttk.Label(win, text="Dirección:").grid(row=2, column=0, sticky="nw", padx=10, pady=10)
        ttk.Entry(win, textvariable=var_dir, width=40).grid(row=2, column=1, sticky="w", padx=10)
        
        def guardar_cambios():
            # Actualizar en historial
            hist_data = load_json_safe(HIST_PATH, [])
            for r in hist_data:
                if r.get("numero") and nombre.lower() in r.get("cliente", "").lower():
                    r["cliente"] = var_nombre.get().strip()
                    r["email"] = var_email.get().strip()
                    r["direccion_cliente"] = var_dir.get().strip()
            
            save_json_safe(HIST_PATH, hist_data)
            self._cargar_clientes_frecuentes_en_combo()
            self.show_success("Cliente frecuente actualizado.")
            win.destroy()
        
        ttk.Button(win, text="Guardar", command=guardar_cambios).grid(row=3, column=0, columnspan=2, pady=10)
        ttk.Button(win, text="Cancelar", command=win.destroy).grid(row=3, column=2, padx=5)

    def _abrir_calendario(self):
        """Abre ventana modal con calendario para seleccionar fecha."""
        if not DateEntry:
            self.show_info("La librería tkcalendar no está instalada.")
            return
        
        from datetime import datetime, date
        from tkcalendar import Calendar
        
        # Ventana modal
        win = tk.Toplevel(self)
        win.title("Seleccionar Fecha de Entrega")
        win.geometry("300x280")
        win.resizable(False, False)
        win.grab_set()
        
        # Centrar ventana en pantalla
        win.update_idletasks()
        x = (win.winfo_screenwidth() // 2) - (300 // 2)
        y = (win.winfo_screenheight() // 2) - (280 // 2)
        win.geometry(f"300x280+{x}+{y}")
        
        # Obtener fecha actual del campo o usar hoy
        try:
            fecha_str = self.var_fecha_entrega.get()
            if fecha_str:
                fecha_actual = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            else:
                fecha_actual = date.today()
        except:
            fecha_actual = date.today()
        
        # Calendario
        cal = Calendar(
            win,
            selectmode='day',
            locale='es',
            year=fecha_actual.year,
            month=fecha_actual.month,
            day=fecha_actual.day,
            firstweekday='monday',
            showweeknumbers=False
        )
        cal.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Botones
        frm_btns = ttk.Frame(win)
        frm_btns.pack(fill="x", padx=10, pady=(0, 10))
        
        def seleccionar():
            fecha_sel = cal.get_date()
            try:
                fecha_obj = datetime.strptime(fecha_sel, "%d/%m/%y")
                self.var_fecha_entrega.set(fecha_obj.strftime("%Y-%m-%d"))
            except:
                self.var_fecha_entrega.set(fecha_sel)
            win.destroy()
        
        ttk.Button(frm_btns, text="Seleccionar", command=seleccionar).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ttk.Button(frm_btns, text="Cancelar", command=win.destroy).pack(side="left", expand=True, fill="x", padx=(5, 0))

    def _limpiar_cliente_frecuente(self):
        """Limpia la selección del cliente frecuente y los campos relacionados."""
        self.cmb_clientes.set("")
        self.cliente_seleccionado = None
        # Limpiar los campos de cliente
        self.var_cliente.set("")
        self.var_cliente_email.set("")
        self.var_direccion.set("")
    
    def _abrir_calendario_filtro(self, var_fecha, parent_window):
        """Abre ventana modal con calendario para seleccionar fecha en filtros del historial."""
        if not DateEntry:
            self.show_info("La librería tkcalendar no está instalada.")
            return
        
        from datetime import datetime, date
        from tkcalendar import Calendar
        
        # Ventana modal
        win = tk.Toplevel(parent_window)
        win.title("Seleccionar Fecha")
        win.geometry("300x280")
        win.resizable(False, False)
        win.grab_set()
        
        # Centrar ventana en pantalla
        win.update_idletasks()
        x = (win.winfo_screenwidth() // 2) - (300 // 2)
        y = (win.winfo_screenheight() // 2) - (280 // 2)
        win.geometry(f"300x280+{x}+{y}")
        
        # Obtener fecha actual del campo o usar hoy
        try:
            fecha_str = var_fecha.get()
            if fecha_str:
                fecha_actual = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            else:
                fecha_actual = date.today()
        except:
            fecha_actual = date.today()
        
        # Calendario
        cal = Calendar(
            win,
            selectmode='day',
            locale='es',
            year=fecha_actual.year,
            month=fecha_actual.month,
            day=fecha_actual.day,
            firstweekday='monday',
            showweeknumbers=False
        )
        cal.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Botones
        frm_btns = ttk.Frame(win)
        frm_btns.pack(fill="x", padx=10, pady=(0, 10))
        
        def seleccionar():
            fecha_sel = cal.get_date()
            try:
                fecha_obj = datetime.strptime(fecha_sel, "%d/%m/%y")
                var_fecha.set(fecha_obj.strftime("%Y-%m-%d"))
            except:
                var_fecha.set(fecha_sel)
            win.destroy()
        
        def limpiar():
            var_fecha.set("")
            win.destroy()
        
        ttk.Button(frm_btns, text="Seleccionar", command=seleccionar).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ttk.Button(frm_btns, text="Limpiar", command=limpiar).pack(side="left", expand=True, fill="x", padx=(5, 5))
        ttk.Button(frm_btns, text="Cancelar", command=win.destroy).pack(side="left", expand=True, fill="x", padx=(5, 0))

    # ==== AUTOCOMPLETE CLIENTE ========================================
    def _on_cliente_key(self, event):
        if event.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return

        texto = self._clean_var(self.var_cliente, self.placeholder_cliente)
        if not texto or len(self.clientes_hist) == 0:
            self._hide_suggestions()
            return

        nombres = [r.get("cliente", "") for r in self.clientes_hist.values()]
        matches = difflib.get_close_matches(texto, nombres, n=8, cutoff=0.2)

        if not matches:
            self._hide_suggestions()
            return

        if not self.lb_suggestions or not isinstance(self.lb_suggestions, tk.Listbox):
            return
        
        self.lb_suggestions.delete(0, "end")
        for m in matches:
            self.lb_suggestions.insert("end", m)

        parent = self.ent_cliente.master
        x = self.ent_cliente.winfo_x()
        y = self.ent_cliente.winfo_y() + self.ent_cliente.winfo_height()
        width = self.ent_cliente.winfo_width()
        self.lb_suggestions.place(in_=parent, x=x, y=y, width=width)
        self.lb_suggestions.lift()

    def _on_cliente_down(self, event):
        if not self.lb_suggestions or not isinstance(self.lb_suggestions, tk.Listbox):
            return
        
        if self.lb_suggestions.winfo_ismapped():
            if self.lb_suggestions.size() > 0:
                self.lb_suggestions.selection_clear(0, "end")
                self.lb_suggestions.selection_set(0)
                self.lb_suggestions.activate(0)
                self.lb_suggestions.focus_set()
            return "break"

    def _on_suggestion_click(self, event):
        self._apply_suggestion_from_listbox()

    def _on_suggestion_enter(self, event):
        self._apply_suggestion_from_listbox()
        return "break"

    def _on_suggestion_up(self, event):
        if not self.lb_suggestions or not isinstance(self.lb_suggestions, tk.Listbox):
            return
        
        sel = self.lb_suggestions.curselection()
        if not sel or sel[0] == 0:
            self.ent_cliente.focus_set()
            return "break"

    def _on_suggestion_down(self, event):
        if not self.lb_suggestions or not isinstance(self.lb_suggestions, tk.Listbox):
            return
        
        sel = self.lb_suggestions.curselection()
        if sel and sel[0] == self.lb_suggestions.size() - 1:
            return "break"

    def _apply_suggestion_from_listbox(self):
        if not self.lb_suggestions or not isinstance(self.lb_suggestions, tk.Listbox):
            return
        
        sel = self.lb_suggestions.curselection()
        if not sel:
            return
        nombre = self.lb_suggestions.get(sel[0])
        self._rellenar_cliente_por_nombre(nombre)
        self._hide_suggestions()

    def _hide_suggestions(self, event=None):
        if self.lb_suggestions and isinstance(self.lb_suggestions, tk.Listbox):
            self.lb_suggestions.place_forget()

    # ==== HISTORIAL / EXPORT / ESTADOS ================================
    def abrir_historial(self):
        hist_data = load_json_safe(HIST_PATH, [])
        if not hist_data:
            self.show_info("No hay cotizaciones registradas en el historial.")
            return

        win = tk.Toplevel(self)
        win.title("Historial de cotizaciones")
        win.state('zoomed')  # Maximizar la ventana
        win.grab_set()

        # Frame superior para filtros - Todo en una fila
        top = ttk.Frame(win)
        top.pack(fill="x", padx=10, pady=8)

        # Filtro por estado
        ttk.Label(top, text="Estado:").grid(row=0, column=0, sticky="w", padx=(0, 3))
        var_f_estado = tk.StringVar(value="Todos")
        cb_estado = ttk.Combobox(
            top,
            textvariable=var_f_estado,
            state="readonly",
            width=10,
            values=["Todos", "Generada", "Enviada", "Aceptada", "Rechazada"]
        )
        cb_estado.grid(row=0, column=1, sticky="w", padx=(0, 10))

        # Filtro de búsqueda por texto
        ttk.Label(top, text="Buscar:").grid(row=0, column=2, sticky="w", padx=(0, 3))
        var_f_text = tk.StringVar()
        ent_buscar = ttk.Entry(top, textvariable=var_f_text, width=20)
        ent_buscar.grid(row=0, column=3, sticky="w", padx=(0, 10))

        # Fecha desde
        ttk.Label(top, text="Desde:").grid(row=0, column=4, sticky="w", padx=(0, 3))
        var_fecha_desde = tk.StringVar(value="")
        ent_fecha_desde = ttk.Entry(top, textvariable=var_fecha_desde, width=10)
        ent_fecha_desde.grid(row=0, column=5, sticky="w")
        
        def abrir_calendario_desde():
            self._abrir_calendario_filtro(var_fecha_desde, win)
        
        ttk.Button(top, text="📅", width=3, command=abrir_calendario_desde).grid(row=0, column=6, sticky="w", padx=(2, 10))

        # Fecha hasta
        ttk.Label(top, text="Hasta:").grid(row=0, column=7, sticky="w", padx=(0, 3))
        var_fecha_hasta = tk.StringVar(value="")
        ent_fecha_hasta = ttk.Entry(top, textvariable=var_fecha_hasta, width=10)
        ent_fecha_hasta.grid(row=0, column=8, sticky="w")
        
        def abrir_calendario_hasta():
            self._abrir_calendario_filtro(var_fecha_hasta, win)
        
        ttk.Button(top, text="📅", width=3, command=abrir_calendario_hasta).grid(row=0, column=9, sticky="w", padx=(2, 10))

        # Checkbox para filtrar por fecha de entrega
        var_filtrar_por_entrega = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Filtrar por entrega", variable=var_filtrar_por_entrega, command=lambda: refrescar_tree()).grid(
            row=0, column=10, sticky="w", padx=(0, 10)
        )

        # Botón para limpiar filtros
        def limpiar_filtros():
            var_f_estado.set("Todos")
            var_f_text.set("")
            var_fecha_desde.set("")
            var_fecha_hasta.set("")
            var_filtrar_por_entrega.set(False)
            refrescar_tree()
        
        ttk.Button(top, text="Limpiar filtros", command=limpiar_filtros).grid(row=0, column=11, sticky="w", padx=(0, 5))

        # Agregar columna "entrega" al Treeview
        cols = ("numero", "fecha", "entrega", "cliente", "estado", "total", "ruta_pdf")
        tree = ttk.Treeview(win, columns=cols, show="headings")
        tree.heading("numero", text="Número")
        tree.heading("fecha", text="Fecha")
        tree.heading("entrega", text="Entrega")
        tree.heading("cliente", text="Cliente")
        tree.heading("estado", text="Estado")
        tree.heading("total", text="Total")
        tree.heading("ruta_pdf", text="Ruta PDF")
        
        tree.column("numero", width=120)
        tree.column("fecha", width=100)
        tree.column("entrega", width=100)
        tree.column("cliente", width=220)
        tree.column("estado", width=90)
        tree.column("total", width=100, anchor="e")
        tree.column("ruta_pdf", width=220)

        tree.pack(fill="both", expand=True, padx=10, pady=(0, 5))

        bottom = ttk.Frame(win)
        bottom.pack(fill="x", padx=10, pady=5)

        def actualizar_estado_seleccion(new_state: str):
            sel = tree.selection()
            if not sel:
                self.show_info("Selecciona una cotización del historial.")
                return

            item_id = sel[0]
            vals = tree.item(item_id, "values")
            if not vals:
                return
            numero = vals[0]
            estado_actual = vals[3]

            if estado_actual == new_state:
                self.show_info(f"La cotización ya está en estado {new_state}.")
                return

            if new_state in ("Aceptada", "Rechazada"):
                if not messagebox.askyesno(
                    "Confirmar",
                    f"¿Marcar la cotización {numero} como {new_state}?"
                ):
                    return

            found = False
            for r in hist_data:
                if r.get("numero") == numero:
                    r["estado"] = new_state
                    found = True
                    break

            if not found:
                self.show_error("No se encontró el registro en el historial.")
                return

            save_json_safe(HIST_PATH, hist_data)
            refrescar_tree()

        ttk.Button(bottom, text="Marcar como Enviada",
                   command=lambda: actualizar_estado_seleccion("Enviada")
                   ).pack(side="left")
        ttk.Button(bottom, text="Marcar como Aceptada",
                   command=lambda: actualizar_estado_seleccion("Aceptada")
                   ).pack(side="left", padx=5)
        ttk.Button(bottom, text="Marcar como Rechazada",
                   command=lambda: actualizar_estado_seleccion("Rechazada")
                   ).pack(side="left")
        
        # Botón para crear nueva versión - esquina inferior derecha
        def crear_nueva_version():
            sel = tree.selection()
            if not sel:
                self.show_info("Selecciona una cotización del historial.")
                return
            
            item_id = sel[0]
            vals = tree.item(item_id, "values")
            if not vals:
                return
            numero = vals[0]
            
            # Buscar el registro completo en hist_data
            registro = None
            for r in hist_data:
                if r.get("numero") == numero:
                    registro = r
                    break
            
            if not registro:
                self.show_error("No se encontró el registro en el historial.")
                return
            
            # Marcar la versión previa como Rechazada
            for r in hist_data:
                if r.get("numero") == numero:
                    r["estado"] = "Rechazada"
                    break
            save_json_safe(HIST_PATH, hist_data)
            
            # Cargar la cotización en la interfaz
            self._cargar_cotizacion_desde_historial(registro)
            win.destroy()
        
        def crear_nueva_cotizacion():
            sel = tree.selection()
            if not sel:
                self.show_info("Selecciona una cotización del historial.")
                return
            
            item_id = sel[0]
            vals = tree.item(item_id, "values")
            if not vals:
                return
            numero = vals[0]
            
            # Buscar el registro completo en hist_data
            registro = None
            for r in hist_data:
                if r.get("numero") == numero:
                    registro = r
                    break
            
            if not registro:
                self.show_error("No se encontró el registro en el historial.")
                return
            
            # Cargar solo los items en la interfaz
            self._cargar_items_desde_historial(registro)
            win.destroy()
        
        ttk.Button(bottom, text="Nueva cotización", command=crear_nueva_cotizacion).pack(side="right", padx=5)
        ttk.Button(bottom, text="Nueva versión", command=crear_nueva_version).pack(side="right", padx=5)

        def refrescar_tree(*args):
            from datetime import datetime
            tree.delete(*tree.get_children())
            filtro_estado = var_f_estado.get()
            filtro_texto = var_f_text.get().strip().lower()
            fecha_desde = var_fecha_desde.get().strip()
            fecha_hasta = var_fecha_hasta.get().strip()
            filtrar_por_entrega = var_filtrar_por_entrega.get()

            # Parsear fechas de filtro - usar función optimizada
            fecha_desde_obj = parse_fecha_flexible(fecha_desde) if fecha_desde else None
            fecha_hasta_obj = parse_fecha_flexible(fecha_hasta) if fecha_hasta else None

            for r in hist_data:
                estado = r.get("estado", "Generada")
                if filtro_estado != "Todos" and estado != filtro_estado:
                    continue

                numero = r.get("numero", "")
                cliente = r.get("cliente", "")
                if filtro_texto:
                    if filtro_texto not in numero.lower() and filtro_texto not in cliente.lower():
                        continue

                # Aplicar filtro de fecha
                if fecha_desde_obj or fecha_hasta_obj:
                    # Determinar qué fecha usar para filtrar
                    if filtrar_por_entrega:
                        fecha_str = r.get("fecha_entrega", "")
                    else:
                        fecha_str = r.get("fecha", "")
                    
                    if fecha_str:
                        # Usar función helper optimizada para parsing
                        fecha_obj = parse_fecha_flexible(fecha_str)
                        
                        if fecha_obj:
                            if fecha_desde_obj and fecha_obj < fecha_desde_obj:
                                continue
                            if fecha_hasta_obj and fecha_obj > fecha_hasta_obj:
                                continue
                        else:
                            # Si no se puede parsear, saltar este registro
                            continue
                    else:
                        # Si no tiene fecha y hay filtros activos, saltar
                        if fecha_desde_obj or fecha_hasta_obj:
                            continue

                # Obtener símbolo de moneda para mostrar el total
                moneda_registro = r.get("moneda", "SOLES")
                # Usa constante global en lugar de recrear dict en cada iteración
                simbolo = SIMBOLOS_MONEDA.get(moneda_registro, "S/")

                tree.insert(
                    "", "end",
                    values=(
                        numero,
                        r.get("fecha", ""),
                        r.get("fecha_entrega", ""),
                        cliente,
                        estado,
                        f"{simbolo} {r.get('total', 0):,.2f}",
                        r.get("ruta_pdf", ""),
                    )
                )

        def refrescar_tree_debounced(*args):
            """Refrescar tree con debounce de 300ms para evitar refrescos innecesarios."""
            if hasattr(self, '_search_debounce_job') and self._search_debounce_job:
                self.after_cancel(self._search_debounce_job)
            self._search_debounce_job = self.after(300, refrescar_tree)
        
        cb_estado.bind("<<ComboboxSelected>>", refrescar_tree)
        ent_buscar.bind("<KeyRelease>", refrescar_tree_debounced)
        ent_fecha_desde.bind("<KeyRelease>", refrescar_tree_debounced)
        ent_fecha_hasta.bind("<KeyRelease>", refrescar_tree_debounced)
        var_filtrar_por_entrega.trace_add("write", lambda *args: refrescar_tree())
        refrescar_tree()

        def on_double_click(event):
            try:
                item_id = tree.focus()
                if not item_id:
                    return
                vals = tree.item(item_id, "values")
                if not vals or len(vals) < 7:
                    self.show_warning("No se encontró ruta asociada.")
                    return
                ruta_nombre = vals[6]
                if not ruta_nombre:
                    self.show_warning("No hay ruta de archivo registrada.")
                    return

                # Construir ruta completa usando la carpeta configurada
                cot_dir = self._get_cotizaciones_dir()
                path = cot_dir / ruta_nombre
                
                if not path.exists():
                    self.show_error(f"Archivo no encontrado: {ruta_nombre}")
                    return

                self._abrir_pdf(path)
            except Exception as e:
                self.show_error(f"Error al abrir archivo: {str(e)[:60]}")

        tree.bind("<Double-1>", on_double_click)
    
    def _cargar_items_en_tree(self, items: list, limpiar_tree: bool = True):
        """
        Método helper centralizado para cargar items en el tree.
        Elimina código duplicado y facilita mantenimiento.
        
        Args:
            items: Lista de diccionarios con datos de items
            limpiar_tree: Si True, limpia el tree antes de cargar
        """
        import shutil
        
        if limpiar_tree:
            for i in self.tree.get_children():
                self.tree.delete(i)
            self.item_images.clear()
        
        ref_dir = self._get_referencias_dir()
        ref_dir.mkdir(exist_ok=True)
        
        for item_data in items:
            desc = item_data.get("descripcion", "")
            cant = item_data.get("cantidad", "")
            precio = item_data.get("precio", "")
            subtotal = item_data.get("subtotal", "")
            img_path = item_data.get("imagen", "")
            
            # Insertar item en el tree
            iid = self.tree.insert(
                "", "end",
                values=("", desc, cant, precio, subtotal)
            )
            
            # Copiar imagen de referencia si existe
            if img_path and Path(img_path).exists():
                try:
                    # Crear copia de la imagen en Referencias
                    img_src = Path(img_path)
                    img_ext = img_src.suffix
                    new_img_name = f"ref_{iid}{img_ext}"
                    new_img_path = ref_dir / new_img_name
                    shutil.copy2(img_src, new_img_path)
                    self.item_images[iid] = str(new_img_path)
                    
                    # Actualizar icono en el tree
                    self.tree.item(iid, values=("📷", desc, cant, precio, subtotal))
                except Exception as e:
                    print(f"No se pudo copiar imagen: {e}")
        
        self._refresh_totals()
    
    def _cargar_cotizacion_desde_historial(self, registro):
        """Carga una cotización desde el historial para crear una nueva versión."""
        # Limpiar cotización actual
        self._reset_cotizacion()
        
        # Establecer el número base para versionado
        numero_completo = registro.get("numero", "")
        if "-V" in numero_completo:
            # Ya tiene versión, usar el numero_base guardado
            self.numero_base_version = registro.get("numero_base", numero_completo.split("-V")[0])
        else:
            # Primera versión, usar el número completo como base
            self.numero_base_version = numero_completo
        
        # Cargar datos del cliente
        self.var_cliente.set(registro.get("cliente", ""))
        self.ent_cliente.configure(foreground="black")
        self.var_cliente_email.set(registro.get("email", ""))
        self.ent_email_cliente.configure(foreground="black")
        self.var_direccion.set(registro.get("direccion_cliente", ""))
        self.ent_dir_cliente.configure(foreground="black")
        self.var_cliente_ruc.set(registro.get("ruc_cliente", ""))
        self.ent_cliente_ruc.configure(foreground="black")
        
        # Cargar condiciones
        self.var_condicion_pago.set(registro.get("condicion_pago", "50% adelanto - 50% contraentrega"))
        self.var_validez.set(registro.get("validez", "15 días"))
        self.var_fecha_entrega.set(registro.get("fecha_entrega", ""))
        
        # Cargar configuración de IGV y moneda
        if "tasa_igv" in registro:
            self.tasa_igv = registro["tasa_igv"]
        if "moneda" in registro:
            self.moneda = registro["moneda"]
        if "igv_enabled" in registro:
            self.var_igv_enabled.set(registro["igv_enabled"])
        
        # Actualizar checkbox IGV
        porcentaje_igv = int(self.tasa_igv * 100)
        self.chk_igv.config(text=f"Aplicar IGV {porcentaje_igv}%")
        
        # Cargar items usando método helper
        items = registro.get("items", [])
        self._cargar_items_en_tree(items, limpiar_tree=True)
    
    def _cargar_items_desde_historial(self, registro):
        """Carga solo los items desde el historial para una nueva cotización."""
        items = registro.get("items", [])
        self._cargar_items_en_tree(items, limpiar_tree=True)

    def exportar_historial_excel(self):
        """Exporta el historial a CSV con formato mejorado y más información."""
        data = load_json_safe(HIST_PATH, [])
        if not data:
            self.show_info("No hay cotizaciones para exportar.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("Archivos CSV (Excel)", "*.csv"), ("Todos los archivos", "*.*")]
        )
        if not file_path:
            return

        campos = [
            "numero", "fecha", "fecha_entrega", "cliente", "email",
            "direccion_cliente", "moneda", "subtotal", "igv", "total", 
            "estado", "condicion_pago", "validez", "items_count", "ruta_pdf"
        ]
        
        try:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=campos)
                writer.writeheader()
                
                # Calcular totales para resumen al final
                total_general = 0
                count_por_estado = {}
                
                for r in data:
                    # Contar items
                    items_count = len(r.get("items", []))
                    
                    # Preparar fila
                    row = {
                        "numero": r.get("numero", ""),
                        "fecha": r.get("fecha", ""),
                        "fecha_entrega": r.get("fecha_entrega", "Por definir"),
                        "cliente": r.get("cliente", ""),
                        "email": r.get("email", ""),
                        "direccion_cliente": r.get("direccion_cliente", ""),
                        "moneda": r.get("moneda", "SOLES"),
                        "subtotal": r.get("subtotal", 0),
                        "igv": r.get("igv", 0),
                        "total": r.get("total", 0),
                        "estado": r.get("estado", "Generada"),
                        "condicion_pago": r.get("condicion_pago", ""),
                        "validez": r.get("validez", ""),
                        "items_count": items_count,
                        "ruta_pdf": r.get("ruta_pdf", "")
                    }
                    
                    writer.writerow(row)
                    
                    # Actualizar totales
                    try:
                        total_general += float(r.get("total", 0))
                        estado = row["estado"]
                        count_por_estado[estado] = count_por_estado.get(estado, 0) + 1
                    except:
                        pass
                
                # Agregar línea de resumen
                writer.writerow({})
                writer.writerow({"numero": "RESUMEN", "total": total_general})
                writer.writerow({"numero": f"Total cotizaciones: {len(data)}"})
                for estado, count in count_por_estado.items():
                    writer.writerow({"numero": f"  {estado}: {count}"})
                
            self.show_success(f"Historial exportado con éxito:\n{file_path}")
        except Exception as e:
            self.show_error(f"No se pudo exportar: {e}")

    # ==== EMAIL ========================================================
    def _enviar_correo(self, pdf_path, numero):
        dest = self._clean_var(self.var_cliente_email, self.placeholder_email_cliente)
        if not dest:
            dest = simpledialog.askstring("Correo", "Correo del cliente:")
            if not dest:
                self.show_info("No se envió correo (sin destinatario).")
                return

        if not EMAIL_PATTERN.match(dest):
            self.show_warning("Email inválido.")
            return

        servidor = self.email_config.get("servidor", "")
        usuario = self.email_config.get("usuario", "")
        password = self.email_config.get("password", "")
        puerto = self.email_config.get("puerto", 587)
        usar_tls = self.email_config.get("usar_tls", True)

        if not servidor or not usuario or not password:
            self.show_warning("Configura servidor, usuario y password en Configuración.")
            return

        msg = EmailMessage()
        msg["Subject"] = f"Cotización {numero}"
        msg["From"] = usuario
        msg["To"] = dest

        cliente = self._clean_var(self.var_cliente, self.placeholder_cliente)

        body = (
            f"Estimado(a) {cliente},\n\n"
            f"Adjuntamos la cotización {numero}.\n\n"
            "Saludos cordiales,\n"
            f"{self.empresa.get('nombre','')}"
        )
        msg.set_content(body)

        try:
            with open(pdf_path, "rb") as f:
                data = f.read()
            msg.add_attachment(
                data,
                maintype="application",
                subtype="pdf",
                filename=f"Cotizacion_{numero}.pdf"
            )
        except Exception as e:
            self.show_error(f"No se pudo adjuntar el PDF: {e}")
            return

        try:
            with smtplib.SMTP(servidor, puerto, timeout=20) as smtp:
                if usar_tls:
                    smtp.starttls()
                smtp.login(usuario, password)
                smtp.send_message(msg)
            self.show_success(f"Cotización enviada a {dest}")
        except Exception as e:
            self.show_error(f"No se pudo enviar el correo: {e}")

    # ==== UTIL: ABRIR ARCHIVOS / CARPETA ==============================
    def _abrir_pdf(self, path: Path):
        if os.name == "nt":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _abrir_carpeta(self, folder: Path):
        if os.name == "nt":
            os.startfile(str(folder))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    def abrir_carpeta_cotizaciones(self):
        cot_dir = self._get_cotizaciones_dir()

        if not cot_dir.exists():
            self.show_info("Aún no existe la carpeta 'Cotizaciones'.")
            return

        try:
            self._abrir_carpeta(cot_dir)
        except Exception as e:
            self.show_error(f"No se pudo abrir la carpeta: {e}")

    # ==== RESET COTIZACIÓN ============================================
    def _reset_cotizacion(self):
        self.var_cliente.set(self.placeholder_cliente)
        self.ent_cliente.configure(foreground="grey")
        self.var_direccion.set(self.placeholder_dir_cliente)
        self.ent_dir_cliente.configure(foreground="grey")
        self.var_cliente_email.set(self.placeholder_email_cliente)
        self.ent_email_cliente.configure(foreground="grey")
        self.var_cliente_ruc.set(self.placeholder_cliente_ruc)
        self.ent_cliente_ruc.configure(foreground="grey")
        self.var_condicion_pago.set(self.terminos_predeterminados["condicion_pago"])
        self.var_validez.set(self.terminos_predeterminados["validez"])

        # Limpiar y establecer términos predeterminados
        self.txt_terms.delete("1.0", "end")
        if self.terminos_predeterminados["texto"]:
            self.txt_terms.insert("1.0", self.terminos_predeterminados["texto"])
        else:
            self._reset_text_placeholder(self.txt_terms, self.placeholder_terms)

        for i in self.tree.get_children():
            self.tree.delete(i)

        self.item_images.clear()
        self.pending_image_path = None

        self._reset_form()
        self._refresh_totals()
        self._hide_suggestions()
        self._clear_preview()

    # ==== CORE: CREAR PDF EN /Cotizaciones ============================
    def _crear_pdf_en_carpeta(self):
        if not self.tree.get_children():
            self.show_warning("Agrega al menos un ítem para generar el PDF.")
            return None

        cliente_raw = self._clean_var(self.var_cliente, self.placeholder_cliente)
        if not cliente_raw:
            self.show_warning("El nombre del cliente es obligatorio.")
            return None

        cot_dir = self._get_cotizaciones_dir()
        ref_dir = self._get_referencias_dir()
        cot_dir.mkdir(exist_ok=True)
        ref_dir.mkdir(exist_ok=True)

        numero = self._next_numero_cotizacion()

        safe_cliente = re.sub(r"[^\w\s\-_.]", "", cliente_raw).strip()
        safe_cliente = safe_cliente.replace("  ", " ").replace(" ", "_") or "SinCliente"
        file_name = f"{safe_cliente} - {numero}.pdf"
        file_path = cot_dir / file_name

        pdf = CotizadorPDF(self.empresa, self.logo_path, numero=numero)
        pdf.set_auto_page_break(True, 15)
        pdf.add_page()

        pdf.set_draw_color(200, 200, 200)
        pdf.set_line_width(0.2)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(4)

        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(0, 6, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", ln=1)
        pdf.cell(0, 6, f"Cliente: {cliente_raw}", ln=1)

        direccion_val = self._clean_var(self.var_direccion, self.placeholder_dir_cliente)
        if direccion_val:
            pdf.cell(0, 6, f"Dirección: {direccion_val}", ln=1)

        email_val = self._clean_var(self.var_cliente_email, self.placeholder_email_cliente)
        if email_val:
            pdf.cell(0, 6, f"Email: {email_val}", ln=1)
        
        ruc_val = self._clean_var(self.var_cliente_ruc, self.placeholder_cliente_ruc)
        if ruc_val:
            pdf.cell(0, 6, f"RUC: {ruc_val}", ln=1)

        pdf.ln(8)

        widths = [80, 15, 20, 30, 30]  # Desc, Ref, Cant, Precio, Subtotal
        headers = ["Descripción", "Ref.", "Cant.", "Precio", "Subtotal"]

        pdf.set_font("Helvetica", "B", 11)
        pdf.set_fill_color(240, 240, 240)
        pdf.set_draw_color(200, 200, 200)
        pdf.set_text_color(30, 30, 30)
        for h, w in zip(headers, widths):
            pdf.cell(w, 8, h, border=1, align="C", fill=True)
        pdf.ln()

        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(50, 50, 50)

        ref_records = []

        for idx, item in enumerate(self.tree.get_children(), start=1):
            icon, d, c, p, s = self.tree.item(item)["values"]

            img_src = self.item_images.get(item)
            ref_code = f"R{idx}" if img_src else ""

            lines = pdf.multi_cell(widths[0], 6, d, split_only=True)
            row_h = 6 * max(1, len(lines))
            x = pdf.get_x()
            y = pdf.get_y()

            if y + row_h > pdf.page_break_trigger:
                pdf.add_page()
                pdf.set_font("Helvetica", "B", 11)
                pdf.set_fill_color(240, 240, 240)
                pdf.set_draw_color(200, 200, 200)
                pdf.set_text_color(30, 30, 30)
                for h, w in zip(headers, widths):
                    pdf.cell(w, 8, h, border=1, align="C", fill=True)
                pdf.ln()
                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(50, 50, 50)
                x = pdf.get_x()
                y = pdf.get_y()

            pdf.multi_cell(widths[0], 6, d, border=1)
            pdf.set_xy(x + widths[0], y)

            pdf.cell(widths[1], row_h, ref_code, border=1, align="C")
            pdf.cell(widths[2], row_h, c, border=1, align="R")
            pdf.cell(widths[3], row_h, p, border=1, align="R")
            pdf.cell(widths[4], row_h, s, border=1, align="R")
            pdf.ln(row_h)

            if img_src:
                try:
                    src_path = Path(img_src)
                    ext = src_path.suffix or ".png"
                    ref_name = f"{numero}_item{idx:02d}{ext}"
                    target_path = ref_dir / ref_name

                    if src_path != target_path:
                        try:
                            shutil.move(src_path, target_path)
                        except Exception:
                            shutil.copyfile(src_path, target_path)

                    self.item_images[item] = str(target_path)
                    ref_records.append((ref_code, d, target_path))
                except Exception:
                    pass

        items = self.tree.get_children()
        subtotales = [
            float(self.tree.item(i)["values"][4]) for i in items
        ] if items else []
        subtotal = sum(subtotales)
        igv = subtotal * IGV_RATE if self.var_igv_enabled.get() else 0.0
        total = subtotal + igv

        pdf.ln(5)
        table_width = sum(widths)
        label_w = 80
        value_w = 30
        start_x = pdf.l_margin + table_width - (label_w + value_w)

        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(40, 40, 40)

        pdf.set_xy(start_x, pdf.get_y())
        pdf.cell(label_w, 8, "SUBTOTAL:", align="R")
        pdf.cell(value_w, 8, f"S/ {subtotal:.2f}", border=1, ln=1, align="R")

        pdf.set_xy(start_x, pdf.get_y())
        pdf.cell(label_w, 8, "IGV:", align="R")
        pdf.cell(value_w, 8, f"S/ {igv:.2f}", border=1, ln=1, align="R")

        pdf.set_xy(start_x, pdf.get_y())
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_fill_color(230, 230, 250)
        pdf.cell(label_w, 8, "TOTAL:", align="R", fill=True)
        pdf.cell(value_w, 8, f"S/ {total:.2f}", border=1, ln=1, align="R", fill=True)

        # TÉRMINOS Y CONDICIONES (unificado)
        pdf.ln(10)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(0, 6, "Términos y Condiciones", ln=1)
        
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(50, 50, 50)
        
        # Construir sección unificada
        condiciones_texto = []
        
        # Condición de pago
        condicion_pago = self.var_condicion_pago.get().strip()
        if condicion_pago:
            condiciones_texto.append(f"- Condición de Pago: {condicion_pago}")
        
        # Validez
        validez = self.var_validez.get().strip()
        if validez:
            condiciones_texto.append(f"- Validez de Oferta: {validez}")
        
        # Fecha de entrega
        fecha_entrega = self.var_fecha_entrega.get().strip()
        fecha_entrega_texto = fecha_entrega if fecha_entrega else "Por definir"
        condiciones_texto.append(f"- Fecha de Entrega: {fecha_entrega_texto}")
        
        # Términos adicionales - cada línea con su guion
        terms = self.txt_terms.get("1.0", "end").strip()
        if terms and terms != self.placeholder_terms:
            # Dividir por líneas y agregar guion a cada una
            lineas_terminos = terms.split('\n')
            for linea in lineas_terminos:
                linea_limpia = linea.strip()
                if linea_limpia:
                    condiciones_texto.append(f"- {linea_limpia}")
        
        # Mostrar condiciones unificadas
        if condiciones_texto:
            for condicion in condiciones_texto:
                pdf.multi_cell(0, 5, condicion)
        else:
            pdf.cell(0, 5, "Sin términos y condiciones especificados", ln=1)

        # REFERENCIAS
        if ref_records:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 14)
            pdf.cell(0, 10, "REFERENCIAS", ln=1, align="C")
            pdf.ln(5)

            usable_width = pdf.w - pdf.l_margin - pdf.r_margin
            text_w = usable_width * 0.45
            img_max_w = usable_width * 0.45

            for ref_code, desc, img_path in ref_records:
                if pdf.get_y() > pdf.page_break_trigger - 80:
                    pdf.add_page()
                    pdf.set_font("Helvetica", "B", 14)
                    pdf.cell(0, 10, "REFERENCIAS (cont.)", ln=1, align="C")
                    pdf.ln(5)

                y_start = pdf.get_y()
                x_text = pdf.l_margin
                x_img = pdf.l_margin + text_w + 10

                pdf.set_xy(x_text, y_start)
                pdf.set_font("Helvetica", "", 10)
                pdf.multi_cell(text_w, 5, f"{ref_code} - {desc}")
                text_bottom = pdf.get_y()

                img_bottom = y_start
                try:
                    from PIL import Image
                    im = Image.open(img_path)
                    w_px, h_px = im.size

                    max_h = pdf.page_break_trigger - pdf.get_y() - 15
                    if max_h < 40:
                        pdf.add_page()
                        pdf.set_font("Helvetica", "B", 14)
                        pdf.cell(0, 10, "REFERENCIAS (cont.)", ln=1, align="C")
                        pdf.ln(5)
                        y_start = pdf.get_y()
                        x_text = pdf.l_margin
                        x_img = pdf.l_margin + text_w + 10
                        pdf.set_xy(x_text, y_start)
                        pdf.set_font("Helvetica", "", 10)
                        pdf.multi_cell(text_w, 5, f"{ref_code} - {desc}")
                        text_bottom = pdf.get_y()
                        max_h = pdf.page_break_trigger - pdf.get_y() - 15

                    scale = min(img_max_w / w_px, max_h / h_px, 1.0)
                    draw_w = w_px * scale
                    draw_h = h_px * scale

                    pdf.image(str(img_path), x=x_img, y=y_start, w=draw_w)
                    img_bottom = y_start + draw_h
                except Exception:
                    pass

                pdf.set_y(max(text_bottom, img_bottom) + 10)

        pdf.output(str(file_path))
        del pdf

        return numero, cot_dir, file_path, subtotal, igv, total

    # ==== GENERAR PDF / ENVIAR ========================================
    def generar_pdf(self):
        result = self._crear_pdf_en_carpeta()
        if result is None:
            return

        numero, cot_dir, file_path, subtotal, igv, total = result
        self._guardar_en_historial(numero, str(file_path), subtotal, igv, total, "Generada")

        try:
            self._abrir_pdf(file_path)
        except Exception as e:
            self.show_error(f"No se pudo abrir el PDF: {e}")

        self.show_success(f"Cotización generada: {numero}")
        self._reset_cotizacion()

    def enviar_por_correo(self):
        result = self._crear_pdf_en_carpeta()
        if result is None:
            return

        numero, cot_dir, file_path, subtotal, igv, total = result
        self._guardar_en_historial(numero, str(file_path), subtotal, igv, total, "Enviada")

        try:
            self._abrir_pdf(file_path)
        except Exception as e:
            self.show_error(f"No se pudo abrir el PDF: {e}")

        self._enviar_correo(str(file_path), numero)
        self._reset_cotizacion()


# ==== RUN =============================================================
if __name__ == "__main__":
    app = CotizadorApp()
    app.mainloop()
