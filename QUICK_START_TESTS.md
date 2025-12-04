# 🚀 Guía Rápida - Tests Cotizador

## ⚡ Inicio Rápido

### Ejecutar todos los tests (recomendado)
```bash
python -m pytest tests/ -v
```

### Con cobertura de código
```bash
python -m pytest tests/ --cov=cotizador --cov-report=term-missing --cov-report=html
```

### O usar el script
```bash
python run_tests.py --mode coverage
```

## 📊 Resultados Esperados

✅ **93/93 tests pasando**
- Tiempo: ~0.7-1 segundo
- Cobertura: 8% (normal para GUI)
- Todos los módulos funcionales

## 📁 Archivos Importantes

| Archivo | Propósito |
|---------|-----------|
| `tests/test_cotizador.py` | 37 tests - Lógica principal |
| `tests/test_validaciones.py` | 25 tests - Validaciones |
| `tests/test_pdf.py` | 31 tests - Generación PDF |
| `pytest.ini` | Configuración de pytest |
| `run_tests.py` | Script facilitador |
| `TEST_RESULTS.md` | Resultados detallados |
| `tests/README.md` | Documentación completa |

## ✅ Qué se Testea

- ✅ Cálculos financieros (IGV, descuentos, totales)
- ✅ Validaciones de datos (entrada, archivos, formatos)
- ✅ Generación de PDFs
- ✅ Formateo de monedas (S/, $, €)
- ✅ Manipulación de fechas
- ✅ Configuración
- ✅ Integración completa

## 🔧 Casos de Uso

### Solo ciertos tests
```bash
# Solo tests de cálculos
python -m pytest tests/test_cotizador.py::TestCalculos -v

# Solo tests de PDF
python -m pytest tests/test_pdf.py -v

# Un test específico
python -m pytest tests/test_cotizador.py::TestCalculos::test_calculo_igv_18_porciento -v
```

### Modo silencioso
```bash
python -m pytest tests/ -q
```

### Modo verbose completo
```bash
python -m pytest tests/ -vv --tb=long
```

## 📈 Ver Cobertura

```bash
# Terminal
python -m pytest tests/ --cov=cotizador --cov-report=term-missing

# HTML (abrir htmlcov/index.html en navegador)
python -m pytest tests/ --cov=cotizador --cov-report=html
```

## 🔍 Solucionar Problemas

### Si los tests fallan

1. Verificar versión de Python
   ```bash
   python --version
   ```

2. Reinstalar dependencias
   ```bash
   pip install pytest pytest-cov
   ```

3. Limpiar cache
   ```bash
   rmdir /s /q .pytest_cache __pycache__
   ```

### Si pytest no está instalado
```bash
pip install pytest pytest-cov
```

## 📝 Información de Versión

- **Python**: 3.13.6 (recomendado 3.10+)
- **pytest**: 9.0.1+
- **Sistema**: Windows/Linux/macOS

## 💡 Consejos

- Los tests corren en **menos de 1 segundo**
- Todos los tests son **independientes**
- Se pueden ejecutar en **cualquier orden**
- **No necesitan configuración adicional**

## 🎯 Próximos Pasos

1. ✅ Todos los tests pasando
2. 📊 Generar reporte de cobertura
3. 🚀 Agregar más tests de integración (opcional)
4. 🔄 Configurar CI/CD (opcional)

---

**Última verificación**: 4 de diciembre de 2025 ✅  
**Estado**: 🟢 Operacional
