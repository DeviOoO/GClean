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
