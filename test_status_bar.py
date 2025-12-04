#!/usr/bin/env python3
"""
Script de prueba para verificar la barra de estado y el log de notificaciones.
Ejecutar: python test_status_bar.py
"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime

class TestApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Prueba de Barra de Estado")
        self.geometry("600x300")
        
        # Historial de notificaciones
        self.notification_log = []
        
        # Frame de prueba
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        ttk.Label(frame, text="Haz click en los botones para generar mensajes:").pack(anchor="w", pady=5)
        
        ttk.Button(frame, text="✓ Mensaje de Éxito", 
                  command=lambda: self.show_status("Cotización generada exitosamente", "success")).pack(anchor="w", pady=2)
        ttk.Button(frame, text="✗ Mensaje de Error", 
                  command=lambda: self.show_status("No se pudo cargar el archivo", "error")).pack(anchor="w", pady=2)
        ttk.Button(frame, text="⚠ Mensaje de Advertencia", 
                  command=lambda: self.show_status("El servidor SMTP no está configurado", "warning")).pack(anchor="w", pady=2)
        ttk.Button(frame, text="ℹ Mensaje Informativo", 
                  command=lambda: self.show_status("Historial guardado correctamente", "info")).pack(anchor="w", pady=2)
        
        ttk.Button(frame, text="🔍 Ver Historial (click en barra de estado abajo)", 
                  command=self.abrir_log_notificaciones).pack(anchor="w", pady=5, ipady=5)
        
        # Barra de estado (clickeable)
        self.status_bar = ttk.Label(self, text="Listo", relief="sunken", anchor="w", 
                                    background="#f0f0f0", foreground="#555555")
        self.status_bar.pack(side="bottom", fill="x", padx=2, pady=2)
        self.status_bar.bind("<Button-1>", lambda e: self.abrir_log_notificaciones())
    
    def show_status(self, message, tipo="info", duracion=5000):
        colores = {
            "success": ("#d4edda", "#155724"),
            "error": ("#f8d7da", "#721c24"),
            "warning": ("#fff3cd", "#856404"),
            "info": ("#f0f0f0", "#555555")
        }
        bg, fg = colores.get(tipo, colores["info"])
        self.status_bar.config(text=message, background=bg, foreground=fg)
        
        # Guardar en el historial
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.notification_log.append((timestamp, tipo, message))
        if len(self.notification_log) > 100:
            self.notification_log.pop(0)
        
        if duracion > 0:
            self.after(duracion, lambda: self.status_bar.config(
                text="Listo", background="#f0f0f0", foreground="#555555"
            ))
    
    def abrir_log_notificaciones(self):
        if not self.notification_log:
            self.show_status("No hay notificaciones registradas.", "info")
            return

        win = tk.Toplevel(self)
        win.title("Historial de Notificaciones")
        win.geometry("600x400")
        win.grab_set()

        text_widget = tk.Text(win, wrap="word", height=20, width=70)
        text_widget.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        text_widget.tag_config("success", foreground="#155724", background="#d4edda")
        text_widget.tag_config("error", foreground="#721c24", background="#f8d7da")
        text_widget.tag_config("warning", foreground="#856404", background="#fff3cd")
        text_widget.tag_config("info", foreground="#555555", background="#f0f0f0")
        text_widget.tag_config("timestamp", foreground="#666666")

        for timestamp, tipo, mensaje in reversed(self.notification_log):
            text_widget.insert("end", f"[{timestamp}] ", "timestamp")
            text_widget.insert("end", f"{mensaje}\n", tipo)

        text_widget.config(state="disabled")

        bottom_frame = ttk.Frame(win)
        bottom_frame.pack(fill="x", padx=10, pady=(5, 10))

        ttk.Button(bottom_frame, text="Copiar todo", 
                  command=lambda: self._copiar_log(text_widget)).pack(side="left", padx=5)
        ttk.Button(bottom_frame, text="Cerrar", command=win.destroy).pack(side="right", padx=5)
    
    def _copiar_log(self, text_widget):
        try:
            contenido = text_widget.get("1.0", "end")
            self.clipboard_clear()
            self.clipboard_append(contenido)
            self.show_status("Historial copiado al portapapeles.", "success")
        except Exception as e:
            self.show_status(f"Error al copiar: {e}", "error")

if __name__ == "__main__":
    app = TestApp()
    app.mainloop()
