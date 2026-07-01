import os
import shutil
import time

def DeleteArquivos(caminho):
    """Deleta arquivos ou subdiretórios de forma segura sem derrubar a pasta raiz."""
    try:
        if os.path.isfile(caminho) or os.path.islink(caminho):
            os.remove(caminho)
        elif os.path.isdir(caminho):
            shutil.rmtree(caminho, ignore_errors=True)
    except Exception:
        raise


def cachetempclean(progressAtt, simulacao=False):
    """Faz a limpeza dos arquivos temporarios

    Args:
        progressAtt (function): Função callback para atualizar a barra de progresso.
        simulacao (bool): Se True, conta os arquivos sem apagá-los.

    Returns:
        Tuple: (apagados, ignorados, total)
    """
    windir = os.getenv('SystemRoot')
    temp = os.getenv('TEMP')

    progressAtt(0)

    # Checagem ANTES de montar os caminhos: a versão original fazia
    # os.path.join(windir, ...) antes de checar se windir era None, o que
    # gerava um TypeError não tratado e travava a thread silenciosamente
    # (o botão "Limpar Cache" ficava desabilitado para sempre).
    if windir is None or temp is None:
        progressAtt(1)
        time.sleep(0.3)
        progressAtt(0)
        return 0, 0, 0

    prefetch_dir = os.path.join(windir, 'Prefetch')
    win_temp_dir = os.path.join(windir, 'Temp')

    if not os.path.exists(prefetch_dir) or not os.path.exists(win_temp_dir):
        progressAtt(1)
        time.sleep(0.3)
        progressAtt(0)
        return 0, 0, 0

    try:
        arq_prefetch = os.listdir(prefetch_dir)
    except Exception:
        arq_prefetch = []
        print("Prefetch não foi pego")

    try:
        arquivos = os.listdir(temp)
    except Exception:
        arquivos = []
        print("%Temp% não foi pego")

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
        time.sleep(0.3)
        progressAtt(0)
        return 0, 0, 0

    # Modo simulação: conta os arquivos candidatos mas não apaga nada.
    if simulacao:
        progressAtt(1)
        time.sleep(0.3)
        progressAtt(0)
        return 0, 0, total_arquivos

    pasta_limpeza = [(temp, arquivos), (prefetch_dir, arq_prefetch), (win_temp_dir, arq_wintemp)]

    for diretorio, lista_arquivos in pasta_limpeza:
        for item in lista_arquivos:
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

    # Reseta a barra ao final, igual ao netclean/sysoptimize fazem — antes a
    # barra ficava parada em 100% até a próxima operação ser disparada.
    progressAtt(1)
    time.sleep(0.5)
    progressAtt(0)
    return apagados, ignorados, total_arquivos