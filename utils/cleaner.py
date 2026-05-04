import subprocess
import os
import shutil
import time



def netclean(progressAtt):
    """Faz a correção da Internet

    Args:
        progressAtt (number): Porcentagem do progresso

    """    
    # início
    progressAtt(0.1)
    time.sleep(0.3)

    subprocess.run(['ipconfig', '/flushdns'])

    progressAtt(0.3)
    time.sleep(0.3)

    subprocess.run(['ipconfig', '/release'])

    progressAtt(0.5)
    time.sleep(0.3)

    subprocess.run(['ipconfig', '/renew'])

    progressAtt(0.7)
    time.sleep(0.3)

    subprocess.run(['netsh','winsock','reset'])

    progressAtt(0.85)
    time.sleep(0.3)

    subprocess.run(['netsh','int','ip','reset'])

    progressAtt(0.95)
    time.sleep(0.3)

    subprocess.run(['nbtstat', '-rr'])

    progressAtt(1.0)


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
        return 0
    
    if not os.path.exists(win_temp_dir):
        return 0
    
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
    
    
    for item in arquivos:
        caminho = os.path.join(temp, item)
        try:
            DeleteArquivos(caminho)
            apagados += 1 
            
        except Exception:
            ignorados += 1
        progresso = (apagados + ignorados) / total_arquivos
        progressAtt(progresso)
        
    for item in arq_prefetch:
        caminho_temp = os.path.join(prefetch_dir, item)
        try:
            DeleteArquivos(caminho_temp)
            apagados += 1 
        except Exception:
            ignorados += 1       
        progresso = (apagados + ignorados) / total_arquivos
        progressAtt(progresso)

    for item in arq_wintemp:
        caminho_wintemp = os.path.join(win_temp_dir, item)
        try:
            DeleteArquivos(caminho_wintemp)
            apagados += 1
        except Exception:
            ignorados += 1
        progresso = (apagados + ignorados) / total_arquivos
        progressAtt(progresso)
    
    progressAtt(1)
    print("Número de arquivos apagados: ",apagados)
    print("Número de arquivos ignorados: ",ignorados)
    return apagados, ignorados, total_arquivos