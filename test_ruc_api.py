import urllib.request
import urllib.error
import json
import ssl

ruc = "20131312955"
url = f"https://dniruc.apisperu.com/api/v1/ruc/{ruc}?token=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6ImRnYXJib2xlZGFAZ21haWwuY29tIn0.rXW9BEWvNp0sStv33XImkUudScHfq63_LxL-Yw8mvG8"

print(f"Consultando RUC: {ruc}")
print(f"URL: {url}\n")

try:
    # Crear contexto SSL que no verifique certificados
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0')
    
    with urllib.request.urlopen(req, timeout=5, context=ssl_context) as response:
        data = json.loads(response.read().decode('utf-8'))
        
        print("="*60)
        print("RESPUESTA COMPLETA DE LA API:")
        print("="*60)
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print("="*60)
        
        print("\nExtracción de campos:")
        print(f"  - razonSocial: {data.get('razonSocial')}")
        print(f"  - nombre: {data.get('nombre')}")
        print(f"  - nombreORazonSocial: {data.get('nombreORazonSocial')}")
        print(f"  - direccion: {data.get('direccion')}")
        print(f"  - direccionCompleta: {data.get('direccionCompleta')}")
        
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
