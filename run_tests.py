#!/usr/bin/env python
"""
Script para ejecutar los tests del Cotizador
"""

import subprocess
import sys
import argparse
from pathlib import Path


def run_tests(mode='normal', file_pattern=None, test_name=None):
    """
    Ejecuta los tests según el modo especificado
    
    Args:
        mode: 'normal', 'verbose', 'coverage', 'quiet'
        file_pattern: Filtro de archivo (ej: test_cotizador.py)
        test_name: Nombre específico del test (ej: TestCalculos::test_calculo_igv_18_porciento)
    """
    
    cmd = [sys.executable, '-m', 'pytest']
    
    # Agregar ruta base
    test_path = 'tests/'
    if file_pattern:
        test_path += file_pattern
    if test_name:
        test_path += f'::{test_name}'
    
    cmd.append(test_path)
    
    # Agregar opciones según el modo
    if mode == 'verbose':
        cmd.extend(['-v', '--tb=short'])
    elif mode == 'coverage':
        cmd.extend([
            '--cov=cotizador',
            '--cov-report=term-missing',
            '--cov-report=html',
            '-v'
        ])
    elif mode == 'quiet':
        cmd.append('-q')
    else:  # normal
        cmd.append('-v')
    
    print(f"Ejecutando: {' '.join(cmd)}\n")
    result = subprocess.run(cmd)
    
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description='Ejecutor de tests para Cotizador',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python run_tests.py                                    # Todos los tests
  python run_tests.py --mode coverage                    # Con cobertura
  python run_tests.py --file test_cotizador.py           # Solo un archivo
  python run_tests.py --test TestCalculos                # Solo una clase
  python run_tests.py --file test_cotizador.py --test TestCalculos::test_calculo_igv_18_porciento
        """
    )
    
    parser.add_argument(
        '--mode',
        choices=['normal', 'verbose', 'coverage', 'quiet'],
        default='verbose',
        help='Modo de ejecución (default: verbose)'
    )
    parser.add_argument(
        '--file',
        help='Archivo de test específico (ej: test_cotizador.py)'
    )
    parser.add_argument(
        '--test',
        help='Test específico (ej: TestCalculos o TestCalculos::test_calculo_igv_18_porciento)'
    )
    
    args = parser.parse_args()
    
    # Ejecutar tests
    returncode = run_tests(
        mode=args.mode,
        file_pattern=args.file,
        test_name=args.test
    )
    
    # Mostrar información adicional
    if args.mode == 'coverage':
        print("\n📊 Reporte HTML generado en: htmlcov/index.html")
    
    return returncode


if __name__ == '__main__':
    sys.exit(main())
