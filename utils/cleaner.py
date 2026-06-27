import subprocess
import os
import shutil
import time

def netclean(progressAtt):
    """Faz a correção profunda e otimização da rede/DNS."""
    progressAtt(0.05)
    time.sleep(0.1)

    # 1. Limpeza de Caches de Rede e DNS
    subprocess.run(['ipconfig', '/flushdns'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    subprocess.run(['nbtstat', '-R'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    subprocess.run(['nbtstat', '-rr'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    progressAtt(0.20)

    # 2. Liberação e Renovação de IP (Aumentado timeout para evitar perda de conexão)
    subprocess.run(['ipconfig', '/release'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    progressAtt(0.40)
    
    # RENOVAÇÃO: timeout maior porque o DHCP do roteador pode demorar para responder
    subprocess.run(['ipconfig', '/renew'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    progressAtt(0.55)

    # 3. Resets de Protocolos e Catálogos
    subprocess.run(['netsh', 'winsock', 'reset'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    subprocess.run(['netsh', 'int', 'ip', 'reset'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    progressAtt(0.70)

    # 4. Otimizações TCP e Otimização de Entrega do Windows Update
    subprocess.run(['netsh', 'advfirewall', 'reset'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    subprocess.run(['netsh', 'int', 'tcp', 'set', 'heuristics', 'disabled'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    subprocess.run(['netsh', 'int', 'tcp', 'set', 'global', 'autotuninglevel=normal'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    
    # Desativa Seeding do Windows Update de forma nativa e silenciosa
    subprocess.run(['powershell', '-Command', 'Set-SeedingPreference -Value 0'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    progressAtt(0.85)

    # 5. Aplicação de DNS Gamer (Cloudflare) tratando múltiplas placas ativas
    try:
        # Retorna as placas separadas por vírgula caso haja mais de uma ativa
        comando_nome_rede = "(Get-NetAdapter | Where-Object {$_.Status -eq 'Up'}).Name"
        resultado = subprocess.run(['powershell', '-Command', comando_nome_rede], capture_output=True, text=True, shell=True, timeout=5)
        
        # Divide o retorno por linhas e limpa espaços vazios
        placas = [linha.strip() for list_linha in resultado.stdout.split('\n') if (linha := list_linha.strip())]

        for placa_ativa in placas:
            if placa_ativa:
                # Configura DNS Primário e Secundário para cada adaptador ativo encontrado
                subprocess.run(['netsh', 'interface', 'ipv4', 'set', 'dns', f'name="{placa_ativa}"', 'static', '1.1.1.1', 'primary'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                subprocess.run(['netsh', 'interface', 'ipv4', 'add', 'dns', f'name="{placa_ativa}"', '1.0.0.1', 'index=2'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    except Exception:
        pass 

    progressAtt(1.0)
    time.sleep(0.5)
    progressAtt(0)


def DeleteArquivos(caminho):
    """Deleta arquivos ou subdiretórios de forma segura sem derrubar a pasta raiz."""
    try:
        if os.path.isfile(caminho) or os.path.islink(caminho):
            os.remove(caminho)
        elif os.path.isdir(caminho):
            # Em vez de apagar a pasta em si, removemos o conteúdo dela de forma limpa
            shutil.rmtree(caminho, ignore_errors=True)
    except Exception:
        raise # Deixa o bloco superior contar como ignorado no try-except principal
        
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
    
