import shutil
import os

try:
    import psutil
except ImportError:
    psutil = None

def capturar_snapshot():
    """Captura o estado atual de disco e RAM para comparação antes/depois.

    Returns:
        dict: {'disco_livre_gb': float, 'ram_usada_gb': float, 'ram_total_gb': float}
              Retorna zeros em caso de erro para não travar o fluxo principal.
    """
    resultado = {"disco_livre_gb": 0.0, "ram_usada_gb": 0.0, "ram_total_gb": 0.0}
    try:
        drive = os.getenv('SystemDrive', 'C:\\')
        uso_disco = shutil.disk_usage(drive)
        resultado["disco_livre_gb"] = uso_disco.free / (1024 ** 3)
    except Exception:
        pass
    if psutil is not None:
        try:
            ram = psutil.virtual_memory()
            resultado["ram_usada_gb"] = ram.used  / (1024 ** 3)
            resultado["ram_total_gb"] = ram.total / (1024 ** 3)
        except Exception:
            pass
    return resultado