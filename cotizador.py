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

CONFIG_PATH = Path("config_cotizador.json")
HIST_PATH = Path("historial_cotizaciones.json")
IGV_RATE = 0.18


# ==== PDF ===============================================================
class CotizadorPDF(FPDF):
    def __init__(self, empresa, logo_path=None, numero=None, *args, **kwargs):
        """
        numero: cadena tipo 'COT-2025-00001' para mostrar en el título.
        """
        super().__init__(*args, **kwargs)
        self.logo_path = logo_path
        self.empresa = empresa
        self.numero = numero

    def header(self):
        # Logo
        if self.logo_path:
            try:
                self.image(self.logo_path, x=10, y=8, w=30)
            except Exception:
                pass

        # Datos empresa
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

        # Título moderno: Cotización N°: SERIE-CORRELATIVO
        self.ln(5)
        self.set_font("Helvetica", "B", 15)
        title = f"Cotización N°: {self.numero}" if self.numero else "Cotización"
        self.cell(0, 10, title, ln=1, align="C")
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Página {self.page_no()}", align="C")


# ==== APP ===============================================================
class CotizadorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sistema de Cotizaciones")
        self.geometry("1150x800")

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

        # Estado de edición de ítems
        self.item_editing = None

        # Listbox de sugerencias
        self.lb_suggestions = None

        self._build_ui()

    # ==== CONFIG FILE ==================================================
    def _load_config(self):
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if "empresa" in data:
                    self.empresa.update(data["empresa"])

                logo = data.get("logo_path")
                if logo and Path(logo).exists():
                    self.logo_path = logo

                self.serie = data.get("serie", self.serie)
                self.correlativo = int(data.get("correlativo", self.correlativo))

                if "email_config" in data:
                    self.email_config.update(data["email_config"])
            except Exception:
                pass

    def _save_config(self):
        data = {
            "empresa": self.empresa,
            "logo_path": self.logo_path,
            "serie": self.serie,
            "correlativo": self.correlativo,
            "email_config": self.email_config,
        }
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

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
        ttk.Entry(frm, textvariable=self.var_direccion, width=40).grid(row=0, column=3, sticky="w")

        ttk.Label(frm, text="Email cliente:").grid(row=1, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.var_cliente_email, width=30).grid(row=1, column=1, sticky="w")

        ttk.Label(frm, text="Pago:").grid(row=1, column=2, sticky="w")
        ttk.Entry(frm, textvariable=self.var_condicion_pago, width=40).grid(row=1, column=3, sticky="w")

        ttk.Label(frm, text="Validez:").grid(row=2, column=0, sticky="w")
        ttk.Entry(frm, textvariable=self.var_validez, width=20).grid(row=2, column=1, sticky="w")

        ttk.Label(frm, text="Clientes frecuentes:").grid(row=2, column=2, sticky="w")
        self.cmb_clientes = ttk.Combobox(frm, state="readonly", width=38)
        self.cmb_clientes.grid(row=2, column=3, sticky="w")
        self.cmb_clientes.bind("<<ComboboxSelected>>", self._on_cliente_frecuente_selected)

        # Listbox de sugerencias (flotante bajo el entry)
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
        frame.pack(fill="both", expand=True, padx=10)

        self.tree = ttk.Treeview(
            frame,
            columns=("desc", "cant", "precio", "subtotal"),
            show="headings"
        )
        self.tree.heading("desc", text="Descripción")
        self.tree.heading("cant", text="Cant.")
        self.tree.heading("precio", text="Precio")
        self.tree.heading("subtotal", text="Subtotal")

        self.tree.column("desc", width=500)
        self.tree.column("cant", width=80, anchor="e")
        self.tree.column("precio", width=110, anchor="e")
        self.tree.column("subtotal", width=130, anchor="e")

        self.tree.pack(fill="both", expand=True)

        frm = ttk.Frame(frame)
        frm.pack(fill="x", pady=5)

        self.var_desc = tk.StringVar()
        self.var_cant = tk.StringVar()
        self.var_precio = tk.StringVar()

        ttk.Entry(frm, textvariable=self.var_desc, width=50).grid(row=0, column=0, padx=2)
        ttk.Entry(frm, textvariable=self.var_cant, width=10).grid(row=0, column=1, padx=2)
        ttk.Entry(frm, textvariable=self.var_precio, width=12).grid(row=0, column=2, padx=2)

        self.btn_add = ttk.Button(frm, text="Agregar", command=self.agregar_item)
        self.btn_add.grid(row=0, column=3, padx=5)

        ttk.Button(frm, text="Editar", command=self.editar_item).grid(row=0, column=4, padx=5)
        ttk.Button(frm, text="Eliminar", command=self.eliminar_item).grid(row=0, column=5, padx=5)

        self.btn_cancel = ttk.Button(frm, text="Cancelar", command=self.cancelar_edicion)
        self.btn_cancel.grid(row=0, column=6, padx=5)
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

    # ==== CONFIG WINDOW =================================================
    def abrir_configuracion(self):
        win = tk.Toplevel(self)
        win.title("Configuración")
        win.geometry("500x420")
        win.grab_set()

        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        # --- Pestaña Empresa ---
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

        # --- Pestaña Correo ---
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

        # --- Guardar / Cancelar ---
        def guardar_config():
            # Empresa
            self.empresa["nombre"] = var_emp_nombre.get().strip()
            self.empresa["ruc"] = var_emp_ruc.get().strip()
            self.empresa["direccion"] = var_emp_dir.get().strip()
            self.serie = var_serie.get().strip() or self.serie

            # Logo
            logo_val = var_logo.get().strip()
            self.logo_path = logo_val or None

            # Correo
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
    def agregar_item(self):
        desc = self.var_desc.get().strip()
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
            self.tree.item(
                self.item_editing,
                values=(desc, f"{cant:.2f}", f"{precio:.2f}", f"{subtotal:.2f}")
            )
        else:
            self.tree.insert(
                "", "end",
                values=(desc, f"{cant:.2f}", f"{precio:.2f}", f"{subtotal:.2f}")
            )

        self._reset_form()
        self._refresh_totals()

    def editar_item(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Selecciona un ítem.")
            return

        item = sel[0]
        vals = self.tree.item(item)["values"]

        self.var_desc.set(vals[0])
        self.var_cant.set(vals[1])
        self.var_precio.set(vals[2])

        self.item_editing = item
        self.btn_add["text"] = "Guardar"
        self.btn_cancel["state"] = "normal"
        self.tree.tag_configure("edit", background="#FFF3CD")
        self.tree.item(item, tags=("edit",))

    def cancelar_edicion(self):
        if self.item_editing:
            self.tree.item(self.item_editing, tags=())
        self._reset_form()

    def eliminar_item(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Selecciona un ítem.")
            return
        self.tree.delete(sel[0])
        self._refresh_totals()

    def _reset_form(self):
        self.var_desc.set("")
        self.var_cant.set("")
        self.var_precio.set("")
        self.btn_add["text"] = "Agregar"
        self.btn_cancel["state"] = "disabled"
        if self.item_editing:
            self.tree.item(self.item_editing, tags=())
        self.item_editing = None

    def _refresh_totals(self):
        subtotal = 0.0
        for i in self.tree.get_children():
            subtotal += float(self.tree.item(i)["values"][3])

        igv = subtotal * IGV_RATE if self.var_igv_enabled.get() else 0.0
        total = subtotal + igv

        self.var_subtotal.set(f"S/ {subtotal:,.2f}")
        self.var_igv.set(f"S/ {igv:,.2f}")
        self.var_total.set(f"S/ {total:,.2f}")

    # ==== HISTORIAL / CLIENTES ========================================
    def _guardar_en_historial(self, numero, ruta_pdf, subtotal, igv, total, estado):
        registro = {
            "numero": numero,
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "cliente": self.var_cliente.get().strip(),
            "email": self.var_cliente_email.get().strip(),
            "direccion_cliente": self.var_direccion.get().strip(),
            "subtotal": float(f"{subtotal:.2f}"),
            "igv": float(f"{igv:.2f}"),
            "total": float(f"{total:.2f}"),
            "ruta_pdf": str(ruta_pdf),
            "estado": estado,
        }
        data = []
        if HIST_PATH.exists():
            try:
                with open(HIST_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = []
        data.append(registro)
        try:
            with open(HIST_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        self._cargar_clientes_frecuentes_en_combo()

    def _cargar_clientes_frecuentes_en_combo(self):
        self.clientes_hist = {}
        if not HIST_PATH.exists():
            self.cmb_clientes["values"] = []
            return
        try:
            with open(HIST_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = []

        for r in data:
            nombre = r.get("cliente", "").strip()
            if not nombre:
                continue
            # último registro por cliente
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
        self.var_cliente_email.set(reg.get("email", ""))
        self.var_direccion.set(reg.get("direccion_cliente", ""))

    def _on_cliente_frecuente_selected(self, event):
        nombre = self.cmb_clientes.get()
        self._rellenar_cliente_por_nombre(nombre)

    # ==== AUTOCOMPLETE AVANZADO =======================================
    def _on_cliente_key(self, event):
        if event.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return

        texto = self.var_cliente.get().strip()
        if not texto or len(self.clientes_hist) == 0:
            self._hide_suggestions()
            return

        matches = []
        for reg in self.clientes_hist.values():
            nombre = reg.get("cliente", "")
            if texto.lower() in nombre.lower():
                matches.append(nombre)

        matches = sorted(set(matches))

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

        if texto.lower() in self.clientes_hist:
            self._rellenar_cliente_por_nombre(texto)

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

    # ==== HISTORIAL / EXPORT / ESTADOS =================================
    def abrir_historial(self):
        if not HIST_PATH.exists():
            messagebox.showinfo("Historial", "No hay cotizaciones registradas.")
            return

        try:
            with open(HIST_PATH, "r", encoding="utf-8") as f:
                hist_data = json.load(f)
        except Exception:
            messagebox.showerror("Error", "No se pudo leer el historial.")
            return

        win = tk.Toplevel(self)
        win.title("Historial de cotizaciones")
        win.geometry("950x450")
        win.grab_set()

        # --- Filtros ---
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

        # --- Treeview ---
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

        # --- Acciones sobre estado ---
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

            # Confirmación ligera para cambios críticos
            if new_state in ("Aceptada", "Rechazada"):
                if not messagebox.askyesno(
                    "Confirmar",
                    f"¿Marcar la cotización {numero} como {new_state}?"
                ):
                    return

            # Actualizar en memoria
            found = False
            for r in hist_data:
                if r.get("numero") == numero:
                    r["estado"] = new_state
                    found = True
                    break

            if not found:
                messagebox.showerror("Estado", "No se encontró el registro en el historial.")
                return

            # Guardar en disco
            try:
                with open(HIST_PATH, "w", encoding="utf-8") as f:
                    json.dump(hist_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                messagebox.showerror("Estado", f"No se pudo actualizar el historial:\n{e}")
                return

            # Refrescar vista
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

        # --- Función para refrescar según filtros ---
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

        # Enlazar filtros a refresco
        cb_estado.bind("<<ComboboxSelected>>", refrescar_tree)
        ent_buscar.bind("<KeyRelease>", refrescar_tree)

        # Primera carga
        refrescar_tree()

        # Doble clic -> abrir PDF asociado
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

                try:
                    self._abrir_pdf(path)
                except Exception as e:
                    messagebox.showerror(
                        "Archivo",
                        f"No se pudo abrir el archivo:\n{e}"
                    )
            except Exception as e:
                messagebox.showerror(
                    "Error",
                    f"Ocurrió un problema al intentar abrir el archivo:\n{e}"
                )

        tree.bind("<Double-1>", on_double_click)

    def exportar_historial_excel(self):
        if not HIST_PATH.exists():
            messagebox.showinfo("Historial", "No hay cotizaciones para exportar.")
            return
        try:
            with open(HIST_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            messagebox.showerror("Error", "No se pudo leer el historial.")
            return

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
        dest = self.var_cliente_email.get().strip()
        if not dest:
            dest = simpledialog.askstring("Correo", "Correo del cliente:")
            if not dest:
                messagebox.showinfo("Correo", "No se envió correo (sin destinatario).")
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

        body = (
            f"Estimado(a) {self.var_cliente.get()},\n\n"
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

    # ==== UTIL: ABRIR ARCHIVOS / CARPETA ===============================
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
        base_dir = Path(__file__).resolve().parent
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
        self.var_cliente.set("")
        self.var_direccion.set("")
        self.var_cliente_email.set("")
        self.var_condicion_pago.set("50% adelanto - 50% contraentrega")
        self.var_validez.set("15 días")
        self.txt_terms.delete("1.0", "end")

        for i in self.tree.get_children():
            self.tree.delete(i)

        self._reset_form()
        self._refresh_totals()
        self._hide_suggestions()

    # ==== CORE: CREAR PDF EN /Cotizaciones ============================
    def _crear_pdf_en_carpeta(self):
        if not self.tree.get_children():
            messagebox.showwarning("Error", "No hay ítems.")
            return None

        if not self.var_cliente.get().strip():
            messagebox.showwarning("Error", "Cliente es obligatorio.")
            return None

        # Carpeta Cotizaciones en el mismo directorio que el script
        base_dir = Path(__file__).resolve().parent
        cot_dir = base_dir / "Cotizaciones"
        cot_dir.mkdir(exist_ok=True)

        numero = self._next_numero_cotizacion()

        # Sanitizar cliente para nombre de archivo
        cliente_raw = self.var_cliente.get().strip() or "SinCliente"
        safe_cliente = re.sub(r"[^\w\s\-_.]", "", cliente_raw).strip()
        safe_cliente = safe_cliente.replace("  ", " ").replace(" ", "_")

        file_name = f"{safe_cliente} - {numero}.pdf"
        file_path = cot_dir / file_name

        # PDF con título moderno
        pdf = CotizadorPDF(self.empresa, self.logo_path, numero=numero)
        pdf.set_auto_page_break(True, 15)
        pdf.add_page()

        # Línea suave bajo cabecera
        pdf.set_draw_color(200, 200, 200)
        pdf.set_line_width(0.2)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(4)

        # Bloque datos de la cotización
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(0, 6, f"Fecha: {datetime.now().strftime('%d/%m/%Y')}", ln=1)
        pdf.cell(0, 6, f"Cliente: {cliente_raw}", ln=1)
        if self.var_direccion.get().strip():
            pdf.cell(0, 6, f"Dirección: {self.var_direccion.get()}", ln=1)
        if self.var_cliente_email.get().strip():
            pdf.cell(0, 6, f"Email: {self.var_cliente_email.get()}", ln=1)
        pdf.cell(0, 6, f"Condición: {self.var_condicion_pago.get()}", ln=1)
        pdf.cell(0, 6, f"Validez: {self.var_validez.get()}", ln=1)

        pdf.ln(8)
        widths = [90, 20, 30, 30]
        headers = ["Descripción", "Cant.", "Precio", "Subtotal"]

        # Encabezado de tabla con estilo moderno
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_fill_color(240, 240, 240)
        pdf.set_draw_color(200, 200, 200)
        pdf.set_text_color(30, 30, 30)
        for h, w in zip(headers, widths):
            pdf.cell(w, 8, h, border=1, align="C", fill=True)
        pdf.ln()

        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(50, 50, 50)

        # Filas de ítems
        for item in self.tree.get_children():
            d, c, p, s = self.tree.item(item)["values"]

            lines = pdf.multi_cell(widths[0], 6, d, split_only=True)
            row_h = 6 * len(lines)
            x = pdf.get_x()
            y = pdf.get_y()

            pdf.multi_cell(widths[0], 6, d, border=1)
            pdf.set_xy(x + widths[0], y)
            pdf.cell(widths[1], row_h, c, border=1, align="R")
            pdf.cell(widths[2], row_h, p, border=1, align="R")
            pdf.cell(widths[3], row_h, s, border=1, align="R")
            pdf.ln(row_h)

        # Totales alineados al borde derecho de la tabla
        subtotal = sum(float(self.tree.item(i)["values"][3]) for i in self.tree.get_children())
        igv = subtotal * IGV_RATE if self.var_igv_enabled.get() else 0.0
        total = subtotal + igv

        pdf.ln(5)
        table_width = sum(widths)
        label_w = 80
        value_w = 30
        start_x = pdf.l_margin + table_width - (label_w + value_w)

        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(40, 40, 40)

        # SUBTOTAL
        pdf.set_xy(start_x, pdf.get_y())
        pdf.cell(label_w, 8, "SUBTOTAL:", align="R")
        pdf.cell(value_w, 8, f"S/ {subtotal:.2f}", border=1, ln=1, align="R")

        # IGV
        pdf.set_xy(start_x, pdf.get_y())
        pdf.cell(label_w, 8, "IGV:", align="R")
        pdf.cell(value_w, 8, f"S/ {igv:.2f}", border=1, ln=1, align="R")

        # TOTAL destacado
        pdf.set_xy(start_x, pdf.get_y())
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_fill_color(230, 230, 250)
        pdf.cell(label_w, 8, "TOTAL:", align="R", fill=True)
        pdf.cell(value_w, 8, f"S/ {total:.2f}", border=1, ln=1, align="R", fill=True)

        # Términos y condiciones
        terms = self.txt_terms.get("1.0", "end").strip()
        if terms:
            pdf.ln(10)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(40, 40, 40)
            pdf.cell(0, 6, "Términos y Condiciones:", ln=1)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(50, 50, 50)
            pdf.multi_cell(0, 5, terms)

        pdf.output(str(file_path))

        # Devuelvo todo para que el caller decida estado y lo guarde
        return numero, cot_dir, file_path, subtotal, igv, total

    # ==== GENERAR PDF (solo genera / abre) ============================
    def generar_pdf(self):
        result = self._crear_pdf_en_carpeta()
        if result is None:
            return

        numero, cot_dir, file_path, subtotal, igv, total = result

        # Guardar en historial con estado "Generada"
        self._guardar_en_historial(numero, str(file_path), subtotal, igv, total, "Generada")

        # Abrir PDF
        try:
            self._abrir_pdf(file_path)
        except Exception as e:
            messagebox.showerror("Archivo", f"No se pudo abrir el PDF generado:\n{e}")

        messagebox.showinfo("OK", f"Cotización generada:\n{file_path}\nN° {numero}")

        # Reset para siguiente operación
        self._reset_cotizacion()

    # ==== ENVIAR POR CORREO (genera + correo) ==========================
    def enviar_por_correo(self):
        result = self._crear_pdf_en_carpeta()
        if result is None:
            return

        numero, cot_dir, file_path, subtotal, igv, total = result

        # Guardar en historial con estado "Enviada"
        self._guardar_en_historial(numero, str(file_path), subtotal, igv, total, "Enviada")

        # Abrir PDF
        try:
            self._abrir_pdf(file_path)
        except Exception as e:
            messagebox.showerror("Archivo", f"No se pudo abrir el PDF generado:\n{e}")

        # Enviar correo (SMTP)
        self._enviar_correo(str(file_path), numero)

        self._reset_cotizacion()


# ==== RUN ==============================================================
if __name__ == "__main__":
    app = CotizadorApp()
    app.mainloop()
