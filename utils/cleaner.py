import subprocess
import os
import shutil
import time



def netclean(progressAtt):
    """Faz a correção profunda e otimização da Internet"""    
    # início
    progressAtt(0.05)
    time.sleep(0.2)

    # 1. Limpeza de Caches de Rede e DNS
    subprocess.run(['ipconfig', '/flushdns'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    subprocess.run(['nbtstat', '-R'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    subprocess.run(['nbtstat', '-rr'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)

    progressAtt(0.20)
    time.sleep(0.2)

    # 2. Liberação e Renovação de IP
    subprocess.run(['ipconfig', '/release'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    progressAtt(0.40)
    time.sleep(0.2)
    
    subprocess.run(['ipconfig', '/renew'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    progressAtt(0.55)
    time.sleep(0.2)

    # 3. Resets de Protocolos e Catálogos (Winsock e IP)
    subprocess.run(['netsh', 'winsock', 'reset'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    subprocess.run(['netsh', 'int', 'ip', 'reset'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    progressAtt(0.70)
    time.sleep(0.2)

    # 4. Otimizações de desempenho TCP e Redefinição do Firewall
    subprocess.run(['netsh', 'advfirewall', 'reset'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    subprocess.run(['netsh', 'int', 'tcp', 'set', 'heuristics', 'disabled'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    subprocess.run(['netsh', 'int', 'tcp', 'set', 'global', 'autotuninglevel=normal'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    
    # [NOVO] Desativar o Seeding do Windows Update (Otimização de Entrega)
    subprocess.run(['powershell', '-Command', 'Set-SeedingPreference -Value 0'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    
    progressAtt(0.85)
    time.sleep(0.2)

    # 5. [NOVO] Aplicação de DNS Gamer (Cloudflare) na Placa Ativa
    try:
        comando_nome_rede = "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Select-Object -ExpandProperty Name"
        resultado = subprocess.run(['powershell', '-Command', comando_nome_rede], capture_output=True, text=True, shell=True, timeout=5)
        nome_placa_ativa = resultado.stdout.strip()

        if nome_placa_ativa:
            # Configura DNS Primário
            subprocess.run(['netsh', 'interface', 'ipv4', 'set', 'dns', f'name="{nome_placa_ativa}"', 'static', '1.1.1.1', 'primary'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            # Configura DNS Secundário
            subprocess.run(['netsh', 'interface', 'ipv4', 'add', 'dns', f'name="{nome_placa_ativa}"', '1.0.0.1', 'index=2'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    except Exception:
        pass # Se falhar em achar a rede, apenas pula para não travar o app

    # Finalização
    progressAtt(1.0)
    time.sleep(0.5)
    progressAtt(0)


def DeleteArquivos(caminho):
    """
    Args:
        caminho string: Caminho para o arquivo ou pasta a apagar

    """    
    if os.path.isfile(caminho):
        os.remove(caminho)
                
    elif os.path.isdir(caminho):
        shutil.rmtree(caminho)

def cachetempclean(progressAtt):
    """Faz a limpeza dos arquivos temporarios

    Args:
        progressAtt (function): Função callback para atualizar a barra de progresso.

    Returns:
        Tuple: (apagados, ignorados, total)
    """    
    #Diretorio Raiz
    windir = os.getenv('SystemRoot')
    prefetch_dir = os.path.join(windir, 'Prefetch')
    win_temp_dir = os.path.join(windir, 'Temp')
    temp = os.getenv('TEMP')
    
    #Inicio
    progressAtt(0)
    
    #Checagem
    if temp is None:
        return 0, 0, 0
    
    if not os.path.exists(prefetch_dir):
        return 0, 0, 0
    
    if not os.path.exists(win_temp_dir):
        return 0, 0, 0
    
    #Pega prefetch
    try:
        arq_prefetch = os.listdir(prefetch_dir)
        
    except Exception:
        arq_prefetch = []
        print("Prefetch não foi pego")
        
    #Pega %Temp%
    try:
        arquivos = os.listdir(temp)
    except Exception:
        arquivos = []
        print("%Temp% não foi pego")
    
    #Pega win/temp
    try:
        arq_wintemp = os.listdir(win_temp_dir)
    except Exception:
        arq_wintemp = []
        print("Win/Temp não foi pego")
    
    total_arquivos = len(arquivos) + len(arq_prefetch) + len(arq_wintemp)
    
    print("Quantidade de arquivos: ", total_arquivos)
    
    apagados = 0
    ignorados = 0
    
    if total_arquivos == 0:
        progressAtt(1)
        return 0, 0, 0
    
    pasta_limpeza = [(temp, arquivos), (prefetch_dir, arq_prefetch), (win_temp_dir, arq_wintemp)]

    for diretorio, lista_arquivos in pasta_limpeza:
        for item in lista_arquivos:
            # Ignora os arquivos com prefixo _MEI do próprio PyInstaller para evitar crash
            if item.startswith('_MEI'):
                ignorados += 1
                continue
                
            caminho = os.path.join(diretorio, item)
            try:
                DeleteArquivos(caminho)
                apagados += 1 
            except Exception:
                ignorados += 1
                
            progresso = (apagados + ignorados) / total_arquivos
            progressAtt(progresso)
    
    progressAtt(1)
    return apagados, ignorados, total_arquivos
    