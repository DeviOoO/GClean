import subprocess
import os
import shutil
import time

def netclean(progressAtt):
    
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

    return 0

def cachetempclean(progressAtt):
    #Inicio
    progressAtt(0)
    
    temp = os.getenv('TEMP')
    if temp is None:
        return 0
    arquivos = os.listdir(temp)
    print("Quantidade de arquivos: ", len(arquivos))
    
    total_arquivos = len(arquivos)
    apagados = 0
    ignorados = 0
    
    if total_arquivos == 0:
        progressAtt(1)
        return 0
    
    
    for item in arquivos:
        caminho = os.path.join(temp, item)
        
        try:
            if os.path.isfile(caminho):
                #print(f"arquivo: {caminho}")
                os.remove(caminho)
                apagados += 1 
                
            elif os.path.isdir(caminho):
                #print(f"pasta: {caminho}")
                shutil.rmtree(caminho)
                apagados += 1 
               
        except Exception:
            ignorados += 1
        
        progresso = (apagados + ignorados) / total_arquivos
        progressAtt(progresso)

    print("Número de arquivos apagados: ",apagados)
    print("Número de arquivos ignorados: ",ignorados)
    return apagados, ignorados, total_arquivos