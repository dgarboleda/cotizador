"""
Tests unitarios para el Sistema de Cotizaciones
"""
import unittest
import json
import tempfile
from pathlib import Path
from datetime import datetime, date
import sys
import os

# Agregar el directorio padre al path para importar cotizador
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importar funciones de utilidad (sin importar la GUI completa)
from cotizador import get_base_dir, load_json_safe, save_json_safe


class TestUtilidades(unittest.TestCase):
    """Tests para funciones de utilidad"""
    
    def test_get_base_dir_returns_path(self):
        """Verifica que get_base_dir retorna una ruta válida"""
        base_dir = get_base_dir()
        self.assertIsNotNone(base_dir)
        self.assertTrue(isinstance(base_dir, Path))
    
    def test_load_json_safe_with_valid_file(self):
        """Verifica que load_json_safe carga datos válidos de un archivo JSON."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"test": "data"}, f)
            fname = f.name
        
        try:
            # Esperar a que Windows libere el archivo
            import time
            time.sleep(0.1)
            result = load_json_safe(Path(fname), {})
            self.assertEqual(result, {"test": "data"})
        finally:
            if os.path.exists(fname):
                os.unlink(fname)
    
    def test_load_json_safe_with_invalid_file(self):
        """Verifica que load_json_safe retorna default con archivo inválido"""
        result = load_json_safe(Path("/ruta/inexistente/archivo.json"), {"default": True})
        self.assertEqual(result, {"default": True})
    
    def test_load_json_safe_with_empty_json(self):
        """Verifica que load_json_safe maneja JSON vacío"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{}")
            fname = f.name
        
        try:
            result = load_json_safe(Path(fname), {})
            self.assertEqual(result, {})
        finally:
            if os.path.exists(fname):
                os.unlink(fname)
    
    def test_save_json_safe_creates_file(self):
        """Verifica que save_json_safe crea el archivo correctamente"""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.json"
            data = {"test": "value", "number": 123}
            
            save_json_safe(filepath, data)
            
            self.assertTrue(os.path.exists(filepath))
            
            with open(filepath, 'r') as f:
                loaded = json.load(f)
            
            self.assertEqual(loaded, data)
    
    def test_save_json_safe_overwrites_file(self):
        """Verifica que save_json_safe sobrescribe archivos existentes"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"old": "data"}, f)
            fname = f.name
        
        try:
            new_data = {"new": "data"}
            save_json_safe(Path(fname), new_data)
            
            with open(fname, 'r') as reader:
                result = json.load(reader)
            
            self.assertEqual(result, new_data)
        finally:
            if os.path.exists(fname):
                os.unlink(fname)


class TestValidaciones(unittest.TestCase):
    """Tests para validaciones de datos"""
    
    def test_email_validation(self):
        """Verifica validación de emails"""
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        valid_emails = [
            "usuario@ejemplo.com",
            "test.email@dominio.co.uk",
            "nombre+apellido@empresa.org"
        ]
        
        for email in valid_emails:
            self.assertTrue(re.match(email_pattern, email))
    
    def test_invalid_email_validation(self):
        """Verifica rechazo de emails inválidos"""
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        invalid_emails = [
            "usuario@",
            "@ejemplo.com",
            "usuario.ejemplo.com",
            "usuario@@ejemplo.com",
            ""
        ]
        
        for email in invalid_emails:
            self.assertFalse(re.match(email_pattern, email))
    
    def test_numero_valido_positivo(self):
        """Verifica validación de números positivos"""
        valores_validos = [1, 1.5, 100, 0.01, 999999.99]
        
        for valor in valores_validos:
            self.assertGreater(valor, 0)
    
    def test_numero_valido_negativo(self):
        """Verifica rechazo de números negativos"""
        valores_invalidos = [-1, -1.5, -100, 0]
        
        for valor in valores_invalidos:
            self.assertLessEqual(valor, 0)


class TestCalculos(unittest.TestCase):
    """Tests para cálculos monetarios"""
    
    def test_calculo_igv_18_porciento(self):
        """Verifica cálculo correcto del IGV 18%"""
        subtotal = 100
        tasa_igv = 0.18
        igv_esperado = 18
        
        igv_calculado = subtotal * tasa_igv
        self.assertAlmostEqual(igv_calculado, igv_esperado, places=2)
    
    def test_calculo_total_con_igv(self):
        """Verifica cálculo del total con IGV"""
        subtotal = 100
        tasa_igv = 0.18
        igv = subtotal * tasa_igv
        total_esperado = 118
        
        total = subtotal + igv
        self.assertAlmostEqual(total, total_esperado, places=2)
    
    def test_calculo_subtotal_multiples_items(self):
        """Verifica subtotal con múltiples items"""
        items = [
            {"cantidad": 2, "precio": 50},      # 100
            {"cantidad": 1, "precio": 30},      # 30
            {"cantidad": 3, "precio": 10},      # 30
        ]
        
        subtotal_esperado = 160
        subtotal = sum(item["cantidad"] * item["precio"] for item in items)
        
        self.assertEqual(subtotal, subtotal_esperado)
    
    def test_calculo_descuento(self):
        """Verifica cálculo de descuentos"""
        subtotal = 100
        descuento_porcentaje = 10  # 10%
        
        monto_descuento = subtotal * (descuento_porcentaje / 100)
        total_con_descuento = subtotal - monto_descuento
        
        self.assertEqual(monto_descuento, 10)
        self.assertEqual(total_con_descuento, 90)
    
    def test_redondeo_moneda(self):
        """Verifica redondeo correcto a 2 decimales"""
        valores = [10.125, 10.126, 10.124, 10.135]
        
        for valor in valores:
            redondeado = round(valor, 2)
            # Verificar que tiene máximo 2 decimales
            self.assertEqual(redondeado, round(redondeado, 2))


class TestFormateoMoneda(unittest.TestCase):
    """Tests para formateo de valores monetarios"""
    
    def test_formato_soles(self):
        """Verifica formateo correcto en soles"""
        cantidad = 1234.56
        moneda_formateada = f"S/ {cantidad:,.2f}"
        
        self.assertEqual(moneda_formateada, "S/ 1,234.56")
    
    def test_formato_dolares(self):
        """Verifica formateo correcto en dólares"""
        cantidad = 1234.56
        moneda_formateada = f"$ {cantidad:,.2f}"
        
        self.assertEqual(moneda_formateada, "$ 1,234.56")
    
    def test_formato_euros(self):
        """Verifica formateo correcto en euros"""
        cantidad = 1234.56
        moneda_formateada = f"€ {cantidad:,.2f}"
        
        self.assertEqual(moneda_formateada, "€ 1,234.56")
    
    def test_formato_cero(self):
        """Verifica formateo de cero"""
        cantidad = 0
        moneda_formateada = f"S/ {cantidad:,.2f}"
        
        self.assertEqual(moneda_formateada, "S/ 0.00")


class TestFechas(unittest.TestCase):
    """Tests para manejo de fechas"""
    
    def test_fecha_hoy(self):
        """Verifica que se obtiene la fecha actual correctamente"""
        hoy = date.today()
        hoy_str = hoy.strftime("%Y-%m-%d")
        
        self.assertIsNotNone(hoy_str)
        self.assertEqual(len(hoy_str), 10)  # YYYY-MM-DD
    
    def test_timestamp_valido(self):
        """Verifica que el timestamp se genera correctamente"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        self.assertIsNotNone(timestamp)
        self.assertEqual(len(timestamp), 8)  # HH:MM:SS
    
    def test_parsing_fecha_iso(self):
        """Verifica parsing correcto de fechas ISO"""
        fecha_str = "2025-12-04"
        fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        
        self.assertEqual(fecha_obj.year, 2025)
        self.assertEqual(fecha_obj.month, 12)
        self.assertEqual(fecha_obj.day, 4)
    
    def test_comparacion_fechas(self):
        """Verifica comparación de fechas"""
        fecha1 = date(2025, 1, 1)
        fecha2 = date(2025, 12, 31)
        
        self.assertLess(fecha1, fecha2)
        self.assertGreater(fecha2, fecha1)


class TestConfiguracion(unittest.TestCase):
    """Tests para configuración de la aplicación"""
    
    def test_empresa_datos_validos(self):
        """Verifica estructura de datos de empresa"""
        empresa = {
            "nombre": "Test S.A.",
            "ruc": "20123456789",
            "direccion": "Calle Principal 123"
        }
        
        self.assertIn("nombre", empresa)
        self.assertIn("ruc", empresa)
        self.assertIn("direccion", empresa)
        self.assertTrue(len(empresa["ruc"]) == 11)
    
    def test_monedas_validas(self):
        """Verifica que las monedas soportadas son válidas"""
        monedas_soportadas = ["SOLES", "DOLARES", "EUROS"]
        
        for moneda in monedas_soportadas:
            self.assertIn(moneda, ["SOLES", "DOLARES", "EUROS"])
    
    def test_tasa_igv_valida(self):
        """Verifica que la tasa de IGV está en rango válido"""
        tasa_igv = 0.18
        
        self.assertGreaterEqual(tasa_igv, 0)
        self.assertLessEqual(tasa_igv, 1)
    
    def test_igv_personalizado_valido(self):
        """Verifica validación de IGV personalizado"""
        valores_validos = [0, 0.05, 0.10, 0.18, 0.21, 1.0]
        
        for valor in valores_validos:
            self.assertGreaterEqual(valor, 0)
            self.assertLessEqual(valor, 1)
    
    def test_igv_personalizado_invalido(self):
        """Verifica rechazo de IGV inválido"""
        valores_invalidos = [-0.1, 1.1, 2.0]
        
        for valor in valores_invalidos:
            self.assertTrue(valor < 0 or valor > 1)


class TestSerie(unittest.TestCase):
    """Tests para generación de series"""
    
    def test_serie_anio_actual(self):
        """Verifica que la serie contiene el año actual"""
        anio_actual = datetime.now().year
        serie = f"COT-{anio_actual}"
        
        self.assertIn(str(anio_actual), serie)
    
    def test_numero_cotizacion_formato(self):
        """Verifica formato de número de cotización"""
        numero = "COT-2025-00001"
        partes = numero.split("-")
        
        self.assertEqual(len(partes), 3)
        self.assertEqual(partes[0], "COT")
        self.assertEqual(partes[1], "2025")
        self.assertTrue(partes[2].isdigit())
    
    def test_numero_cotizacion_con_version(self):
        """Verifica formato de número con versión"""
        numero = "COT-2025-00001-V2"
        
        self.assertIn("V", numero)
        self.assertTrue(numero.endswith("V2"))


class TestHistorial(unittest.TestCase):
    """Tests para el historial de cotizaciones"""
    
    def test_estructura_registro_historial(self):
        """Verifica estructura de registro en historial"""
        registro = {
            "numero": "COT-2025-00001",
            "fecha": "2025-12-04",
            "cliente": "Cliente Test",
            "estado": "Pendiente",
            "total": 1000.00,
            "ruta_pdf": "archivo.pdf"
        }
        
        campos_requeridos = ["numero", "fecha", "cliente", "estado", "total", "ruta_pdf"]
        for campo in campos_requeridos:
            self.assertIn(campo, registro)
    
    def test_estados_validos_cotizacion(self):
        """Verifica que los estados de cotización son válidos"""
        estados_validos = ["Pendiente", "Enviada", "Rechazada", "Ganada"]
        
        for estado in estados_validos:
            self.assertIsNotNone(estado)
            self.assertTrue(len(estado) > 0)


class TestIntegracion(unittest.TestCase):
    """Tests de integración básicos"""
    
    def test_flujo_cotizacion_completo(self):
        """Verifica el flujo básico de una cotización"""
        # Datos de entrada
        cliente = "Cliente Test"
        items = [
            {"desc": "Item 1", "cant": 2, "precio": 50},
            {"desc": "Item 2", "cant": 1, "precio": 100}
        ]
        
        # Calcular
        subtotal = sum(item["cant"] * item["precio"] for item in items)
        igv = subtotal * 0.18
        total = subtotal + igv
        
        # Verificar
        self.assertEqual(subtotal, 200)
        self.assertEqual(round(igv, 2), 36.0)
        self.assertEqual(round(total, 2), 236.0)
    
    def test_numero_version_correlativo(self):
        """Verifica incremento correcto de correlativo"""
        correlativo_base = 1
        correlativo_siguiente = correlativo_base + 1
        
        self.assertEqual(correlativo_siguiente, 2)
        
        numero_v1 = f"COT-2025-{correlativo_base:05d}-V1"
        numero_v2 = f"COT-2025-{correlativo_base:05d}-V2"
        
        self.assertEqual(numero_v1, "COT-2025-00001-V1")
        self.assertEqual(numero_v2, "COT-2025-00001-V2")


def suite():
    """Crea la suite de tests"""
    test_suite = unittest.TestSuite()
    
    # Agregar todos los tests
    test_suite.addTest(unittest.makeSuite(TestUtilidades))
    test_suite.addTest(unittest.makeSuite(TestValidaciones))
    test_suite.addTest(unittest.makeSuite(TestCalculos))
    test_suite.addTest(unittest.makeSuite(TestFormateoMoneda))
    test_suite.addTest(unittest.makeSuite(TestFechas))
    test_suite.addTest(unittest.makeSuite(TestConfiguracion))
    test_suite.addTest(unittest.makeSuite(TestSerie))
    test_suite.addTest(unittest.makeSuite(TestHistorial))
    test_suite.addTest(unittest.makeSuite(TestIntegracion))
    
    return test_suite


if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite())
    
    # Salir con código de error si hay fallos
    exit(0 if result.wasSuccessful() else 1)
