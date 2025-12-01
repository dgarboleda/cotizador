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

# Nota: para vista previa de imágenes instalar Pillow:
# pip install pillow

CONFIG_PATH = Path("config_cotizador.json")
HIST_PATH = Path("historial_cotizaciones.json")
IGV_RATE = 0.18


# ==== HELPERS GENERALES ===============================================
def get_base_dir() -> Path:
    """
    Devuelve el directorio base de la app.
    Compatible con script normal y ejecutable (PyInstaller/cx_Freeze).
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
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
        self.geometry("1150x900")

        # Config persistente
        self.logo_path = None
        self.empresa = {
            "nombre": "TENTACIONES ELENA",
            "ruc": "20123456789",
            "direccion": "El Palmar 107 Urb. Salamanca Ate",
        }
        self.serie = "COT-2025"
        self.correlativo = 1
        self.email_config = {
            "servidor": "",
            "puerto": 587,
            "usuario": "",
            "password": "",
            "usar_tls": True,
        }

        # cache clientes
        self.clientes_hist = {}

        # imágenes por ítem
        self.item_images = {}           # {iid: ruta_origen}
        self.pending_image_path = None  # imagen seleccionada para nuevo ítem

        # preview imagen
        self.preview_photo = None

        self._load_config()

        # Encabezado cliente
        self.var_cliente = tk.StringVar()
        self.var_direccion = tk.StringVar()
        self.var_cliente_email = tk.StringVar()
        self.var_condicion_pago = tk.StringVar(value="50% adelanto - 50% contraentrega")
        self.var_validez = tk.StringVar(value="15 días")

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
        self.placeholder_cant = "Cantidad"
        self.placeholder_precio = "Precio"
        self.placeholder_desc = "Descripción detallada del producto (multilínea)..."
        self.placeholder_terms = "Términos y condiciones adicionales..."

        self._build_ui()
        self._init_placeholders()

    # ==== CONFIG FILE ==================================================
    def _load_config(self):
        data = load_json_safe(CONFIG_PATH, {})
        if not data:
            return

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

        if "email_config" in data:
            self.email_config.update(data["email_config"])

    def _save_config(self):
        data = {
            "empresa": self.empresa,
            "logo_path": self.logo_path,
            "serie": self.serie,
            "correlativo": self.correlativo,
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

    # ==== UI ROOT ======================================================
    def _build_ui(self):
        self._build_header()
        self._build_items()
        self._build_totals()
        self._build_terms()
        self._build_actions()

    # ---- Header cliente -----------------------------------------------
    def _build_header(self):
        frm = ttk.LabelFrame(self, text="Cliente / Condiciones")
        frm.pack(fill="x", padx=10, pady=5)

        ttk.Label(frm, text="Cliente:").grid(row=0, column=0, sticky="w")
        self.ent_cliente = ttk.Entry(frm, textvariable=self.var_cliente, width=30)
        self.ent_cliente.grid(row=0, column=1, sticky="w")
        self.ent_cliente.bind("<KeyRelease>", self._on_cliente_key)
        self.ent_cliente.bind("<Down>", self._on_cliente_down)

        ttk.Label(frm, text="Dirección cliente:").grid(row=0, column=2, sticky="w")
        self.ent_dir_cliente = ttk.Entry(frm, textvariable=self.var_direccion, width=40)
        self.ent_dir_cliente.grid(row=0, column=3, sticky="w")

        ttk.Label(frm, text="Email cliente:").grid(row=1, column=0, sticky="w")
        self.ent_email_cliente = ttk.Entry(frm, textvariable=self.var_cliente_email, width=30)
        self.ent_email_cliente.grid(row=1, column=1, sticky="w")

        ttk.Label(frm, text="Pago:").grid(row=1, column=2, sticky="w")
        ttk.Entry(frm, textvariable=self.var_condicion_pago, width=40).grid(row=1, column=3, sticky="w")

        ttk.Label(frm, text="Validez:").grid(row=2, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.var_validez, width=20).grid(row=2, column=1, sticky="w")

        ttk.Label(frm, text="Clientes frecuentes:").grid(row=2, column=2, sticky="w")
        self.cmb_clientes = ttk.Combobox(frm, state="readonly", width=38)
        self.cmb_clientes.grid(row=2, column=3, sticky="w")
        self.cmb_clientes.bind("<<ComboboxSelected>>", self._on_cliente_frecuente_selected)

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

        self.btn_cancel = ttk.Button(frm, text="Cancelar", command=self.cancelar_edicion)
        self.btn_cancel.grid(row=0, column=7, padx=5)
        self.btn_cancel["state"] = "disabled"

    # ---- Totales ------------------------------------------------------
    def _build_totals(self):
        frame = ttk.LabelFrame(self, text="Totales")
        frame.pack(fill="x", padx=10, pady=5)

        chk = ttk.Checkbutton(
            frame, text="Aplicar IGV 18%", variable=self.var_igv_enabled,
            command=self._refresh_totals
        )
        chk.grid(row=0, column=0, columnspan=2, sticky="w", padx=5)

        ttk.Label(frame, text="Subtotal:").grid(row=1, column=0, sticky="e")
        ttk.Label(frame, textvariable=self.var_subtotal).grid(row=1, column=1, sticky="w")

        ttk.Label(frame, text="IGV:").grid(row=1, column=2, sticky="e")
        ttk.Label(frame, textvariable=self.var_igv).grid(row=1, column=3, sticky="w")

        ttk.Label(frame, text="TOTAL:").grid(row=1, column=4, sticky="e")
        ttk.Label(frame, textvariable=self.var_total, font=("Arial", 11, "bold")).grid(
            row=1, column=5, sticky="w"
        )

    # ---- Términos -----------------------------------------------------
    def _build_terms(self):
        frame = ttk.LabelFrame(self, text="Términos y Condiciones (opcional)")
        frame.pack(fill="both", padx=10, pady=5)

        self.txt_terms = tk.Text(frame, height=4, wrap="word")
        self.txt_terms.pack(fill="both", expand=True, padx=5, pady=5)

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
        ttk.Button(frm, text="GENERAR PDF", command=self.generar_pdf).pack(side="right", padx=5)

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
        self._init_entry_placeholder(self.ent_cant, self.var_cant, self.placeholder_cant)
        self._init_entry_placeholder(self.ent_precio, self.var_precio, self.placeholder_precio)

        self._init_text_placeholder(self.txt_desc, self.placeholder_desc)
        self._init_text_placeholder(self.txt_terms, self.placeholder_terms)

    # ==== CONFIG WINDOW ================================================
    def abrir_configuracion(self):
        win = tk.Toplevel(self)
        win.title("Configuración")
        win.geometry("500x420")
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

        ttk.Label(frm_emp, text="Serie de cotización:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        var_serie = tk.StringVar(value=self.serie)
        ttk.Entry(frm_emp, textvariable=var_serie, width=20).grid(row=3, column=1, sticky="w")

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

        def guardar_config():
            self.empresa["nombre"] = var_emp_nombre.get().strip()
            self.empresa["ruc"] = var_emp_ruc.get().strip()
            self.empresa["direccion"] = var_emp_dir.get().strip()
            self.serie = var_serie.get().strip() or self.serie

            logo_val = var_logo.get().strip()
            self.logo_path = logo_val or None

            try:
                puerto = int(var_port.get())
            except ValueError:
                messagebox.showwarning("Error", "Puerto inválido.")
                return

            self.email_config["servidor"] = var_srv.get().strip()
            self.email_config["puerto"] = puerto
            self.email_config["usuario"] = var_user.get().strip()
            self.email_config["password"] = var_pass.get().strip()
            self.email_config["usar_tls"] = var_tls.get()

            self._save_config()
            messagebox.showinfo("OK", "Configuración guardada.")
            win.destroy()

        btn_frame = ttk.Frame(win)
        btn_frame.pack(fill="x", pady=5)
        ttk.Button(btn_frame, text="Guardar", command=guardar_config).pack(side="right", padx=10)
        ttk.Button(btn_frame, text="Cancelar", command=win.destroy).pack(side="right")

    # ==== NUMERACIÓN ===================================================
    def _next_numero_cotizacion(self):
        numero = f"{self.serie}-{str(self.correlativo).zfill(5)}"
        self.correlativo += 1
        self._save_config()
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
                messagebox.showerror(
                    "Imagen",
                    f"No se pudo preparar la imagen para el PDF:\n{e}\n{e2}"
                )
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

        messagebox.showinfo("Imagen", "Imagen asociada al ítem.")

    def agregar_item(self):
        desc = self.txt_desc.get("1.0", "end").strip()
        if desc == self.placeholder_desc:
            desc = ""
        if not desc:
            messagebox.showwarning("Error", "La descripción no puede estar vacía.")
            return

        try:
            cant = float(self.var_cant.get())
            precio = float(self.var_precio.get())
        except ValueError:
            messagebox.showwarning("Error", "Cantidad o precio inválidos.")
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
            messagebox.showinfo("Info", "Selecciona un ítem.")
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
            messagebox.showinfo("Info", "Selecciona un ítem.")
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

        if getattr(self, "item_editing", None):
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

        igv = subtotal * IGV_RATE if self.var_igv_enabled.get() else 0.0
        total = subtotal + igv

        self.var_subtotal.set(f"S/ {subtotal:,.2f}")
        self.var_igv.set(f"S/ {igv:,.2f}")
        self.var_total.set(f"S/ {total:,.2f}")

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

        registro = {
            "numero": numero,
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "cliente": cliente,
            "email": email,
            "direccion_cliente": direccion,
            "subtotal": float(f"{subtotal:.2f}"),
            "igv": float(f"{igv:.2f}"),
            "total": float(f"{total:.2f}"),
            "ruta_pdf": str(ruta_pdf),
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

    def _on_cliente_frecuente_selected(self, event):
        nombre = self.cmb_clientes.get()
        self._rellenar_cliente_por_nombre(nombre)

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
        sel = self.lb_suggestions.curselection()
        if not sel or sel[0] == 0:
            self.ent_cliente.focus_set()
            return "break"

    def _on_suggestion_down(self, event):
        sel = self.lb_suggestions.curselection()
        if sel and sel[0] == self.lb_suggestions.size() - 1:
            return "break"

    def _apply_suggestion_from_listbox(self):
        sel = self.lb_suggestions.curselection()
        if not sel:
            return
        nombre = self.lb_suggestions.get(sel[0])
        self._rellenar_cliente_por_nombre(nombre)
        self._hide_suggestions()

    def _hide_suggestions(self, event=None):
        self.lb_suggestions.place_forget()

    # ==== HISTORIAL / EXPORT / ESTADOS ================================
    def abrir_historial(self):
        hist_data = load_json_safe(HIST_PATH, [])
        if not hist_data:
            messagebox.showinfo("Historial", "No hay cotizaciones registradas.")
            return

        win = tk.Toplevel(self)
        win.title("Historial de cotizaciones")
        win.geometry("950x450")
        win.grab_set()

        top = ttk.Frame(win)
        top.pack(fill="x", padx=5, pady=5)

        ttk.Label(top, text="Estado:").pack(side="left")
        var_f_estado = tk.StringVar(value="Todos")
        cb_estado = ttk.Combobox(
            top,
            textvariable=var_f_estado,
            state="readonly",
            width=12,
            values=["Todos", "Generada", "Enviada", "Aceptada", "Rechazada"]
        )
        cb_estado.pack(side="left", padx=5)

        ttk.Label(top, text="Buscar (nro / cliente):").pack(side="left", padx=(15, 2))
        var_f_text = tk.StringVar()
        ent_buscar = ttk.Entry(top, textvariable=var_f_text, width=30)
        ent_buscar.pack(side="left")

        cols = ("numero", "fecha", "cliente", "email", "estado", "total", "ruta_pdf")
        tree = ttk.Treeview(win, columns=cols, show="headings")
        for c in cols:
            tree.heading(c, text=c.capitalize())
        tree.column("numero", width=120)
        tree.column("fecha", width=140)
        tree.column("cliente", width=200)
        tree.column("email", width=200)
        tree.column("estado", width=90)
        tree.column("total", width=100, anchor="e")
        tree.column("ruta_pdf", width=220)

        tree.pack(fill="both", expand=True, padx=5, pady=5)

        bottom = ttk.Frame(win)
        bottom.pack(fill="x", padx=5, pady=5)

        def actualizar_estado_seleccion(new_state: str):
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("Estado", "Selecciona una cotización.")
                return

            item_id = sel[0]
            vals = tree.item(item_id, "values")
            if not vals:
                return
            numero = vals[0]
            estado_actual = vals[4]

            if estado_actual == new_state:
                messagebox.showinfo("Estado", f"La cotización ya está en estado {new_state}.")
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
                messagebox.showerror("Estado", "No se encontró el registro en el historial.")
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

        def refrescar_tree(*args):
            tree.delete(*tree.get_children())
            filtro_estado = var_f_estado.get()
            filtro_texto = var_f_text.get().strip().lower()

            for r in hist_data:
                estado = r.get("estado", "Generada")
                if filtro_estado != "Todos" and estado != filtro_estado:
                    continue

                numero = r.get("numero", "")
                cliente = r.get("cliente", "")
                if filtro_texto:
                    if filtro_texto not in numero.lower() and filtro_texto not in cliente.lower():
                        continue

                tree.insert(
                    "", "end",
                    values=(
                        numero,
                        r.get("fecha", ""),
                        cliente,
                        r.get("email", ""),
                        estado,
                        f"S/ {r.get('total', 0):,.2f}",
                        r.get("ruta_pdf", ""),
                    )
                )

        cb_estado.bind("<<ComboboxSelected>>", refrescar_tree)
        ent_buscar.bind("<KeyRelease>", refrescar_tree)
        refrescar_tree()

        def on_double_click(event):
            try:
                item_id = tree.focus()
                if not item_id:
                    return
                vals = tree.item(item_id, "values")
                if not vals or len(vals) < 7:
                    messagebox.showwarning("Archivo", "No se encontró ruta asociada.")
                    return
                ruta = vals[6]
                if not ruta:
                    messagebox.showwarning("Archivo", "No hay ruta de archivo registrada.")
                    return

                path = Path(ruta)
                if not path.exists():
                    messagebox.showerror(
                        "Archivo",
                        f"El archivo no se encuentra en la ruta registrada:\n{ruta}"
                    )
                    return

                self._abrir_pdf(path)
            except Exception as e:
                messagebox.showerror(
                    "Error",
                    f"Ocurrió un problema al intentar abrir el archivo:\n{e}"
                )

        tree.bind("<Double-1>", on_double_click)

    def exportar_historial_excel(self):
        data = load_json_safe(HIST_PATH, [])
        if not data:
            messagebox.showinfo("Historial", "No hay cotizaciones para exportar.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("Archivos CSV (Excel)", "*.csv")]
        )
        if not file_path:
            return

        campos = [
            "numero", "fecha", "cliente", "email",
            "direccion_cliente", "subtotal", "igv", "total", "estado", "ruta_pdf"
        ]
        try:
            with open(file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=campos)
                writer.writeheader()
                for r in data:
                    row = {k: r.get(k, "") for k in campos}
                    if "estado" not in row or not row["estado"]:
                        row["estado"] = "Generada"
                    writer.writerow(row)
            messagebox.showinfo("Exportación", f"Historial exportado a:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo exportar:\n{e}")

    # ==== EMAIL ========================================================
    def _enviar_correo(self, pdf_path, numero):
        dest = self._clean_var(self.var_cliente_email, self.placeholder_email_cliente)
        if not dest:
            dest = simpledialog.askstring("Correo", "Correo del cliente:")
            if not dest:
                messagebox.showinfo("Correo", "No se envió correo (sin destinatario).")
                return

        if not re.match(r"[^@]+@[^@]+\.[^@]+", dest):
            messagebox.showwarning("Correo", "Email inválido.")
            return

        servidor = self.email_config.get("servidor", "")
        usuario = self.email_config.get("usuario", "")
        password = self.email_config.get("password", "")
        puerto = self.email_config.get("puerto", 587)
        usar_tls = self.email_config.get("usar_tls", True)

        if not servidor or not usuario or not password:
            messagebox.showwarning(
                "Correo",
                "Configura servidor, usuario y password en 'Configuración' antes de enviar."
            )
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
            messagebox.showerror("Correo", f"No se pudo adjuntar el PDF:\n{e}")
            return

        try:
            with smtplib.SMTP(servidor, puerto, timeout=20) as smtp:
                if usar_tls:
                    smtp.starttls()
                smtp.login(usuario, password)
                smtp.send_message(msg)
            messagebox.showinfo("Correo", f"Cotización enviada a {dest}")
        except Exception as e:
            messagebox.showerror("Correo", f"No se pudo enviar el correo:\n{e}")

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
        base_dir = get_base_dir()
        cot_dir = base_dir / "Cotizaciones"

        if not cot_dir.exists():
            messagebox.showinfo("Carpeta", "Aún no existe la carpeta 'Cotizaciones'.")
            return

        try:
            self._abrir_carpeta(cot_dir)
        except Exception as e:
            messagebox.showerror("Carpeta", f"No se pudo abrir la carpeta:\n{e}")

    # ==== RESET COTIZACIÓN ============================================
    def _reset_cotizacion(self):
        self.var_cliente.set(self.placeholder_cliente)
        self.ent_cliente.configure(foreground="grey")
        self.var_direccion.set(self.placeholder_dir_cliente)
        self.ent_dir_cliente.configure(foreground="grey")
        self.var_cliente_email.set(self.placeholder_email_cliente)
        self.ent_email_cliente.configure(foreground="grey")
        self.var_condicion_pago.set("50% adelanto - 50% contraentrega")
        self.var_validez.set("15 días")

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
            messagebox.showwarning("Error", "No hay ítems.")
            return None

        cliente_raw = self._clean_var(self.var_cliente, self.placeholder_cliente)
        if not cliente_raw:
            messagebox.showwarning("Error", "Cliente es obligatorio.")
            return None

        base_dir = get_base_dir()
        cot_dir = base_dir / "Cotizaciones"
        ref_dir = base_dir / "Referencias"
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

        pdf.cell(0, 6, f"Condición: {self.var_condicion_pago.get()}", ln=1)
        pdf.cell(0, 6, f"Validez: {self.var_validez.get()}", ln=1)

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

        terms = self.txt_terms.get("1.0", "end").strip()
        if terms == self.placeholder_terms:
            terms = ""
        if terms:
            pdf.ln(10)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(40, 40, 40)
            pdf.cell(0, 6, "Términos y Condiciones:", ln=1)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, 5, terms)

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
            messagebox.showerror("Archivo", f"No se pudo abrir el PDF generado:\n{e}")

        messagebox.showinfo("OK", f"Cotización generada:\n{file_path}\nN° {numero}")
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
            messagebox.showerror("Archivo", f"No se pudo abrir el PDF generado:\n{e}")

        self._enviar_correo(str(file_path), numero)
        self._reset_cotizacion()


# ==== RUN =============================================================
if __name__ == "__main__":
    app = CotizadorApp()
    app.mainloop()
