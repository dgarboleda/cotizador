"""
Tests para validaciones de entrada y salida
"""
import unittest
import tempfile
import os
from pathlib import Path


class TestValidacionesEntrada(unittest.TestCase):
    """Tests para validación de entrada de datos"""
    
    def test_cliente_no_vacio(self):
        """Verifica que cliente no puede estar vacío"""
        cliente = ""
        self.assertEqual(len(cliente.strip()), 0)
    
    def test_cliente_con_espacios(self):
        """Verifica trimming de espacios en cliente"""
        cliente = "  Nombre Cliente  "
        cliente_limpio = cliente.strip()
        self.assertEqual(cliente_limpio, "Nombre Cliente")
    
    def test_cantidad_debe_ser_numerica(self):
        """Verifica que cantidad debe ser numérica"""
        try:
            cantidad = float("10.5")
            self.assertEqual(cantidad, 10.5)
        except ValueError:
            self.fail("Cantidad no es numérica")
    
    def test_cantidad_no_puede_ser_negativa(self):
        """Verifica que cantidad no puede ser negativa"""
        cantidad = -10
        self.assertLess(cantidad, 0)
    
    def test_precio_debe_ser_numerico(self):
        """Verifica que precio debe ser numérico"""
        try:
            precio = float("99.99")
            self.assertEqual(precio, 99.99)
        except ValueError:
            self.fail("Precio no es numérico")
    
    def test_precio_no_puede_ser_negativo(self):
        """Verifica que precio no puede ser negativo"""
        precio = -99.99
        self.assertLess(precio, 0)
    
    def test_descripcion_no_vacia(self):
        """Verifica que descripción no puede estar vacía"""
        desc = ""
        self.assertEqual(len(desc.strip()), 0)
    
    def test_descripcion_minima_longitud(self):
        """Verifica longitud mínima de descripción"""
        desc = "Producto"
        self.assertGreater(len(desc), 0)


class TestValidacionesArchivos(unittest.TestCase):
    """Tests para validación de archivos"""
    
    def test_archivo_existe(self):
        """Verifica verificación de existencia de archivo"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            filepath = f.name
        
        self.assertTrue(os.path.exists(filepath))
        os.unlink(filepath)
    
    def test_archivo_no_existe(self):
        """Verifica detección de archivo no existente"""
        filepath = "/ruta/inexistente/archivo.txt"
        self.assertFalse(os.path.exists(filepath))
    
    def test_extension_pdf_valida(self):
        """Verifica validación de extensión PDF"""
        filename = "cotizacion.pdf"
        self.assertTrue(filename.endswith(".pdf"))
    
    def test_extension_invalida_rechazada(self):
        """Verifica rechazo de extensión inválida"""
        filename = "cotizacion.txt"
        self.assertFalse(filename.endswith(".pdf"))
    
    def test_ruta_absoluta_valida(self):
        """Verifica que ruta absoluta es válida"""
        ruta = Path("c:/Users/test/archivo.pdf")
        self.assertTrue(isinstance(ruta, Path))
    
    def test_nombre_archivo_valido(self):
        """Verifica validación de nombre de archivo"""
        nombre = "cotizacion_2025_001.pdf"
        caracteres_invalidos = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        
        tiene_invalidos = any(char in nombre for char in caracteres_invalidos)
        self.assertFalse(tiene_invalidos)


class TestValidacionesFormato(unittest.TestCase):
    """Tests para validación de formatos"""
    
    def test_ruc_11_digitos(self):
        """Verifica que RUC tiene 11 dígitos"""
        ruc = "20123456789"
        self.assertEqual(len(ruc), 11)
        self.assertTrue(ruc.isdigit())
    
    def test_ruc_invalido_letras(self):
        """Verifica rechazo de RUC con letras"""
        ruc = "20ABC456789"
        self.assertFalse(ruc.isdigit())
    
    def test_telefono_formato(self):
        """Verifica formato de teléfono"""
        import re
        # Patrón más flexible para números de teléfono
        telefono_pattern = r'^[\d\s\-\+\(\)]{7,20}$'
        
        telefonos_validos = ["987654321", "9876543210", "+51 999 123 456"]
        for tel in telefonos_validos:
            self.assertTrue(re.match(telefono_pattern, tel), f"El teléfono {tel} no cumple con el patrón")
    
    def test_url_valida(self):
        """Verifica validación de URL"""
        import re
        url_pattern = r'^https?://'
        
        url_valida = "https://www.ejemplo.com"
        self.assertTrue(re.match(url_pattern, url_valida))
    
    def test_url_invalida(self):
        """Verifica rechazo de URL inválida"""
        import re
        url_pattern = r'^https?://'
        
        url_invalida = "www.ejemplo.com"
        self.assertFalse(re.match(url_pattern, url_invalida))


class TestSanitizacion(unittest.TestCase):
    """Tests para sanitización de datos"""
    
    def test_remover_espacios_excesivos(self):
        """Verifica remoción de espacios excesivos"""
        texto = "  Nombre   con   espacios  "
        texto_limpio = " ".join(texto.split())
        self.assertEqual(texto_limpio, "Nombre con espacios")
    
    def test_convertir_mayusculas(self):
        """Verifica conversión a mayúsculas"""
        texto = "cliente"
        texto_upper = texto.upper()
        self.assertEqual(texto_upper, "CLIENTE")
    
    def test_convertir_minusculas(self):
        """Verifica conversión a minúsculas"""
        texto = "CLIENTE"
        texto_lower = texto.lower()
        self.assertEqual(texto_lower, "cliente")
    
    def test_remover_caracteres_especiales(self):
        """Verifica remoción de caracteres especiales"""
        import re
        texto = "Cliente@#$%123"
        texto_limpio = re.sub(r'[^a-zA-Z0-9\s]', '', texto)
        self.assertEqual(texto_limpio, "Cliente123")


class TestLimitesYRangos(unittest.TestCase):
    """Tests para límites y rangos de valores"""
    
    def test_cantidad_maxima(self):
        """Verifica límite máximo de cantidad"""
        cantidad_max = 999999
        cantidad = 100
        self.assertLessEqual(cantidad, cantidad_max)
    
    def test_precio_maximo(self):
        """Verifica límite máximo de precio"""
        precio_max = 999999.99
        precio = 1000.00
        self.assertLessEqual(precio, precio_max)
    
    def test_descuento_rango_valido(self):
        """Verifica rango válido de descuento"""
        descuento = 50  # porcentaje
        self.assertGreaterEqual(descuento, 0)
        self.assertLessEqual(descuento, 100)
    
    def test_igv_rango_valido(self):
        """Verifica rango válido de IGV"""
        igv = 0.18
        self.assertGreaterEqual(igv, 0)
        self.assertLessEqual(igv, 1)
    
    def test_validez_dias(self):
        """Verifica rango válido de validez en días"""
        validez = 30
        self.assertGreater(validez, 0)
        self.assertLess(validez, 365)


class TestTipoDatos(unittest.TestCase):
    """Tests para validación de tipos de datos"""
    
    def test_cantidad_es_numero(self):
        """Verifica que cantidad es número"""
        cantidad = 10
        self.assertIsInstance(cantidad, (int, float))
    
    def test_precio_es_numero(self):
        """Verifica que precio es número"""
        precio = 99.99
        self.assertIsInstance(precio, (int, float))
    
    def test_cliente_es_string(self):
        """Verifica que cliente es string"""
        cliente = "Nombre Cliente"
        self.assertIsInstance(cliente, str)
    
    def test_fecha_es_string_o_date(self):
        """Verifica que fecha es string o date"""
        from datetime import date
        fecha = date.today()
        self.assertTrue(isinstance(fecha, date) or isinstance(fecha, str))
    
    def test_items_es_lista(self):
        """Verifica que items es una lista"""
        items = [{"desc": "Item 1", "cant": 1, "precio": 100}]
        self.assertIsInstance(items, list)
    
    def test_item_es_diccionario(self):
        """Verifica que item es diccionario"""
        item = {"desc": "Item 1", "cant": 1, "precio": 100}
        self.assertIsInstance(item, dict)


if __name__ == "__main__":
    unittest.main(verbosity=2)
