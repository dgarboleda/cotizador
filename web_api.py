from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qs, urlparse

from cotizador import (
    CONFIG_PATH,
    HIST_PATH,
    IGV_RATE,
    SIMBOLOS_MONEDA,
    load_json_safe,
    parse_numero_version,
    save_json_safe,
    validar_ruc_peruano,
)

JSONDict = Dict[str, Any]


def _config_path() -> Path:
    override = os.getenv("COTIZADOR_CONFIG_PATH")
    return Path(override) if override else CONFIG_PATH


def _historial_path() -> Path:
    override = os.getenv("COTIZADOR_HIST_PATH")
    return Path(override) if override else HIST_PATH


def _load_config() -> dict:
    base_config = {
        "empresa": {"nombre": "", "ruc": "", "direccion": "", "telefono": ""},
        "tasa_igv": IGV_RATE,
        "moneda": "SOLES",
        "serie": f"COT-{datetime.now().year}",
        "correlativo": 1,
    }
    data = load_json_safe(_config_path(), {})

    if not isinstance(data, dict):
        return base_config

    if isinstance(data.get("empresa"), dict):
        base_config["empresa"].update(data["empresa"])

    for key in ("tasa_igv", "moneda", "serie", "correlativo"):
        if key in data:
            base_config[key] = data[key]

    return base_config


def _load_historial() -> list:
    data = load_json_safe(_historial_path(), [])
    return data if isinstance(data, list) else []


def _save_historial(historial: list) -> None:
    path = _historial_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    save_json_safe(path, historial)


def _next_numero_cotizacion(historial: list, serie: str, correlativo_base: int) -> str:
    max_correlativo = max(correlativo_base - 1, 0)

    for registro in historial:
        numero = registro.get("numero", "")
        base, _ = parse_numero_version(numero)
        partes = base.split("-")

        if len(partes) == 3 and f"{partes[0]}-{partes[1]}" == serie:
            try:
                correlativo = int(partes[2])
                if correlativo > max_correlativo:
                    max_correlativo = correlativo
            except ValueError:
                continue

    siguiente = max_correlativo + 1
    return f"{serie}-{siguiente:05d}"


def _calcular_totales(items: List[JSONDict], aplicar_igv: bool, tasa_igv: float) -> dict:
    subtotal = sum(item["cantidad"] * item["precio_unitario"] for item in items)
    igv = round(subtotal * tasa_igv, 2) if aplicar_igv else 0.0
    total = round(subtotal + igv, 2)
    return {
        "subtotal": round(subtotal, 2),
        "igv": igv,
        "total": total,
    }


def _validar_items(items: Any) -> Tuple[List[JSONDict], str | None]:
    if not isinstance(items, list) or not items:
        return [], "Debe incluir al menos un ítem."

    normalizados: List[JSONDict] = []

    for item in items:
        if not isinstance(item, dict):
            return [], "Cada ítem debe ser un diccionario."

        desc = str(item.get("descripcion", "")).strip()
        if not desc:
            return [], "La descripción del ítem es obligatoria."

        try:
            cantidad = float(item.get("cantidad", 0))
            precio = float(item.get("precio_unitario", 0))
        except (TypeError, ValueError):
            return [], "La cantidad y el precio deben ser numéricos."

        if cantidad <= 0 or precio <= 0:
            return [], "La cantidad y el precio deben ser mayores que cero."

        normalizados.append(
            {
                "descripcion": desc,
                "cantidad": cantidad,
                "precio_unitario": precio,
                "imagen": item.get("imagen"),
            }
        )

    return normalizados, None


def _normalizar_payload(payload: JSONDict, config: dict) -> Tuple[JSONDict | None, str | None]:
    if not isinstance(payload, dict):
        return None, "El cuerpo debe ser un JSON válido."

    cliente = payload.get("cliente") or {}
    if not isinstance(cliente, dict):
        return None, "El cliente debe ser un objeto."

    nombre = str(cliente.get("nombre", "")).strip()
    if not nombre:
        return None, "El nombre del cliente es obligatorio."

    ruc = cliente.get("ruc")
    if ruc:
        ruc = str(ruc).strip()
        if not validar_ruc_peruano(ruc):
            return None, "El RUC del cliente no es válido."

    cliente_normalizado = {
        "nombre": nombre,
        "ruc": ruc,
        "email": str(cliente.get("email", "")).strip() or None,
        "direccion": str(cliente.get("direccion", "")).strip() or None,
        "telefono": str(cliente.get("telefono", "")).strip() or None,
    }

    items_normalizados, error_items = _validar_items(payload.get("items"))
    if error_items:
        return None, error_items

    moneda = str(payload.get("moneda", config.get("moneda", "SOLES"))).upper()
    if moneda not in SIMBOLOS_MONEDA:
        return None, f"Moneda no soportada: {moneda}."

    aplicar_igv = bool(payload.get("aplicar_igv", True))
    try:
        tasa_igv = float(payload.get("tasa_igv", config.get("tasa_igv", IGV_RATE)))
    except (TypeError, ValueError):
        return None, "La tasa de IGV debe ser numérica."

    if tasa_igv < 0 or tasa_igv > 1:
        return None, "La tasa de IGV debe estar entre 0 y 1."

    validez = payload.get("validez_dias", 30)
    if validez is not None:
        try:
            validez_int = int(validez)
            if validez_int <= 0 or validez_int > 365:
                return None, "La validez debe estar entre 1 y 365 días."
            validez = validez_int
        except (TypeError, ValueError):
            return None, "La validez debe ser un número entero."

    notas = payload.get("notas")
    if notas is not None:
        notas = str(notas).strip()
        if len(notas) > 1000:
            return None, "Las notas no pueden exceder 1000 caracteres."

    return (
        {
            "cliente": cliente_normalizado,
            "items": items_normalizados,
            "moneda": moneda,
            "aplicar_igv": aplicar_igv,
            "tasa_igv": tasa_igv,
            "validez_dias": validez,
            "notas": notas or None,
        },
        None,
    )


def _crear_registro(normalizado: JSONDict, config: dict) -> JSONDict:
    historial = _load_historial()
    serie = str(config.get("serie") or f"COT-{datetime.now().year}")
    correlativo_base = int(config.get("correlativo", 1) or 1)
    numero = _next_numero_cotizacion(historial, serie, correlativo_base)

    totales = _calcular_totales(
        normalizado["items"],
        normalizado["aplicar_igv"],
        normalizado["tasa_igv"],
    )
    simbolo = SIMBOLOS_MONEDA.get(normalizado["moneda"], "S/")
    fecha_emision = datetime.now().strftime("%Y-%m-%d")

    registro = {
        "numero": numero,
        "fecha_emision": fecha_emision,
        "cliente": normalizado["cliente"],
        "items": normalizado["items"],
        "moneda": normalizado["moneda"],
        "simbolo_moneda": simbolo,
        "totales": totales,
        "validez_dias": normalizado["validez_dias"],
        "notas": normalizado["notas"],
    }

    historial.append(registro)
    _save_historial(historial)

    return registro


def create_cotizacion(payload: JSONDict) -> JSONDict:
    config = _load_config()
    normalizado, error = _normalizar_payload(payload, config)
    if error:
        raise ValueError(error)
    return _crear_registro(normalizado, config)


class QuoteRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _write_json(self, payload: JSONDict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _parse_json_body(self) -> JSONDict | None:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return None
        try:
            raw = self.rfile.read(length)
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            return self._write_json(
                {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}
            )

        if parsed.path == "/api/config":
            config = _load_config()
            simbolo = SIMBOLOS_MONEDA.get(str(config.get("moneda", "")).upper(), "S/")
            return self._write_json(
                {
                    "empresa": config.get("empresa", {}),
                    "moneda": config.get("moneda", "SOLES"),
                    "simbolo_moneda": simbolo,
                    "tasa_igv": config.get("tasa_igv", IGV_RATE),
                    "serie": config.get("serie", f"COT-{datetime.now().year}"),
                }
            )

        if parsed.path == "/api/cotizaciones":
            try:
                params = parse_qs(parsed.query)
                limit = int(params.get("limit", ["20"])[0])
                limit = max(1, min(limit, 100))
            except (ValueError, TypeError):
                limit = 20

            historial = _load_historial()
            historial_ordenado = sorted(
                historial,
                key=lambda r: r.get("fecha_emision", ""),
                reverse=True,
            )
            return self._write_json(historial_ordenado[:limit])

        self.send_error(HTTPStatus.NOT_FOUND.value, "Endpoint no encontrado")

    def do_POST(self):
        if self.path != "/api/cotizaciones":
            self.send_error(HTTPStatus.NOT_FOUND.value, "Endpoint no encontrado")
            return

        payload = self._parse_json_body()
        if payload is None:
            self._write_json(
                {"detail": "El cuerpo debe ser un JSON válido."},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        config = _load_config()
        normalizado, error = _normalizar_payload(payload, config)
        if error:
            self._write_json({"detail": error}, status=HTTPStatus.BAD_REQUEST)
            return

        registro = _crear_registro(normalizado, config)
        self._write_json(registro, status=HTTPStatus.CREATED)

    def log_message(self, format: str, *args: Any) -> None:
        # Reducir ruido en pruebas automatizadas
        return


def create_server(host: str = "0.0.0.0", port: int = 8000) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), QuoteRequestHandler)


def start_in_background(host: str = "0.0.0.0", port: int = 8000) -> tuple[ThreadingHTTPServer, threading.Thread]:
    server = create_server(host, port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


if __name__ == "__main__":
    server = create_server()
    host, port = server.server_address
    print(f"Servidor del cotizador web escuchando en http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando servidor...")
    finally:
        server.shutdown()
