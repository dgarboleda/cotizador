import http.client
import importlib
import json
import os
import sys
import threading
from pathlib import Path
from typing import Tuple


def _start_server(tmp_path: Path, config_data: dict | None = None):
    config_path = tmp_path / "config.json"
    hist_path = tmp_path / "historial.json"

    if config_data is None:
        config_data = {
            "empresa": {"nombre": "Empresa Test", "ruc": "20100000009"},
            "moneda": "SOLES",
            "tasa_igv": 0.18,
            "serie": "COT-2030",
            "correlativo": 1,
        }

    config_path.write_text(json.dumps(config_data), encoding="utf-8")

    os.environ["COTIZADOR_CONFIG_PATH"] = str(config_path)
    os.environ["COTIZADOR_HIST_PATH"] = str(hist_path)

    if "web_api" in sys.modules:
        importlib.reload(importlib.import_module("web_api"))
    else:
        importlib.import_module("web_api")

    import web_api

    server = web_api.create_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    host, port = server.server_address
    return server, thread, host, port, hist_path


def _stop_server(server, thread):
    server.shutdown()
    thread.join(timeout=2)


def _post_json(host: str, port: int, path: str, payload: dict) -> Tuple[int, dict]:
    conn = http.client.HTTPConnection(host, port)
    body = json.dumps(payload)
    headers = {"Content-Type": "application/json"}
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read().decode("utf-8")
    conn.close()
    return resp.status, json.loads(data or "{}")


def _get_json(host: str, port: int, path: str) -> Tuple[int, dict | list]:
    conn = http.client.HTTPConnection(host, port)
    conn.request("GET", path)
    resp = conn.getresponse()
    data = resp.read().decode("utf-8")
    conn.close()
    parsed = json.loads(data or "{}")
    return resp.status, parsed


def test_health_check(tmp_path):
    server, thread, host, port, _ = _start_server(tmp_path)
    try:
        status, data = _get_json(host, port, "/api/health")
        assert status == 200
        assert data["status"] == "ok"
        assert "timestamp" in data
    finally:
        _stop_server(server, thread)


def test_crear_cotizacion_persiste_en_historial(tmp_path):
    server, thread, host, port, hist_path = _start_server(tmp_path)
    try:
        payload = {
            "cliente": {
                "nombre": "Cliente Web",
                "email": "cliente@example.com",
                "ruc": "20100000009",
                "direccion": "Av. Test",
            },
            "items": [
                {"descripcion": "Servicio de mantenimiento", "cantidad": 2, "precio_unitario": 150},
                {"descripcion": "Repuestos", "cantidad": 1, "precio_unitario": 50},
            ],
            "moneda": "SOLES",
            "aplicar_igv": True,
            "tasa_igv": 0.18,
            "validez_dias": 15,
            "notas": "Entrega en 48h",
        }

        status, data = _post_json(host, port, "/api/cotizaciones", payload)
        assert status == 201
        assert data["numero"].startswith("COT-2030-")
        assert data["totales"]["subtotal"] == 350.0
        assert data["totales"]["igv"] == 63.0
        assert data["totales"]["total"] == 413.0
        assert data["simbolo_moneda"] == "S/"

        assert hist_path.exists()
        hist_data = json.loads(hist_path.read_text(encoding="utf-8"))
        assert len(hist_data) == 1
        assert hist_data[0]["numero"] == data["numero"]
        assert hist_data[0]["totales"]["total"] == 413.0
    finally:
        _stop_server(server, thread)


def test_listar_cotizaciones_devuelve_registros_recientes(tmp_path):
    server, thread, host, port, hist_path = _start_server(tmp_path)
    try:
        payload = {
            "cliente": {"nombre": "Cliente Web", "ruc": "20100000009"},
            "items": [{"descripcion": "Auditoría", "cantidad": 1, "precio_unitario": 200}],
            "moneda": "DOLARES",
            "aplicar_igv": False,
        }

        status, _ = _post_json(host, port, "/api/cotizaciones", payload)
        assert status == 201

        listado_status, data = _get_json(host, port, "/api/cotizaciones?limit=5")
        assert listado_status == 200
        assert len(data) == 1
        assert data[0]["numero"].startswith("COT-2030-")
        assert data[0]["moneda"] == "DOLARES"

        hist_data = json.loads(hist_path.read_text(encoding="utf-8"))
        assert hist_data == data
    finally:
        _stop_server(server, thread)


def test_config_predeterminada_si_no_existe_archivo(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    hist_path = tmp_path / "historial.json"

    monkeypatch.setenv("COTIZADOR_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("COTIZADOR_HIST_PATH", str(hist_path))

    if "web_api" in sys.modules:
        importlib.reload(importlib.import_module("web_api"))
    else:
        importlib.import_module("web_api")

    import web_api

    server = web_api.create_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address

    try:
        status, data = _get_json(host, port, "/api/config")
        assert status == 200
        assert data["moneda"] == "SOLES"
        assert data["tasa_igv"] == 0.18
        assert data["simbolo_moneda"] == "S/"
    finally:
        _stop_server(server, thread)
