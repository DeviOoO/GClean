import subprocess
import os
import time
import ctypes
from .cache import DeleteArquivos
from .power import ajustar_plano_energia, limpar_planos_duplicados

try:
    import psutil
except ImportError:
    psutil = None

def _limpar_logs_sistema():
    """Remove arquivos de %SystemRoot%\\Logs reutilizando a exclusão segura.

    Returns:
        Tuple[bool, str]: sucesso e detalhe de quantos itens foram removidos.
    """
    removidos = 0
    try:
        windir = os.getenv('SystemRoot')
        if not windir:
            return False, "Variável SystemRoot não encontrada"

        logs_dir = os.path.join(windir, 'Logs')
        if not os.path.exists(logs_dir):
            return True, "Nenhum log para limpar"

        for item in os.listdir(logs_dir):
            caminho = os.path.join(logs_dir, item)
            try:
                DeleteArquivos(caminho)
                removidos += 1
            except Exception:
                continue
        return True, f"{removidos} itens removidos"
    except Exception as e:
        return False, f"Falha na limpeza de logs ({e.__class__.__name__})"


def _otimizar_disco():
    """Detecta o tipo de disco do sistema e aplica a otimização correta.

    SSD -> dispara TRIM via Optimize-Volume -ReTrim (rápido, seguro, recomendado
    pela própria Microsoft). HDD mecânico -> roda desfragmentação real, mas com
    timeout limitado para não travar a otimização inteira em discos muito
    fragmentados; se exceder o tempo, sinaliza como recomendação manual.

    Substitui o antigo `fsutil behavior set memoryusage 2`, que é um parâmetro
    legado do Windows 2000/XP sem efeito real em versões modernas do Windows.

    Returns:
        Tuple[bool, str]: sucesso e descrição do que foi feito.
    """
    drive_sistema = os.getenv('SystemDrive', 'C:').rstrip('\\').rstrip(':')

    try:
        consulta = subprocess.run(
            ['powershell', '-Command',
             f"(Get-Partition -DriveLetter {drive_sistema} | Get-Disk | Get-PhysicalDisk).MediaType"],
            capture_output=True, text=True, shell=True, timeout=10
        )
        tipo = (consulta.stdout or "").strip()
    except Exception as e:
        return False, f"Falha ao identificar tipo de disco ({e.__class__.__name__})"

    if "SSD" in tipo:
        try:
            subprocess.run(
                ['powershell', '-Command', f"Optimize-Volume -DriveLetter {drive_sistema} -ReTrim"],
                shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60
            )
            return True, "TRIM aplicado no SSD do sistema"
        except subprocess.TimeoutExpired:
            return False, "TRIM do SSD excedeu o tempo limite"
        except Exception as e:
            return False, f"Falha ao aplicar TRIM ({e.__class__.__name__})"

    if "HDD" in tipo:
        try:
            subprocess.run(
                ['powershell', '-Command', f"Optimize-Volume -DriveLetter {drive_sistema} -Defrag"],
                shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180
            )
            return True, "Desfragmentação aplicada no HD do sistema"
        except subprocess.TimeoutExpired:
            return False, "HD muito fragmentado — desfragmentação não concluída a tempo, recomenda-se rodar manualmente"
        except Exception as e:
            return False, f"Falha ao desfragmentar ({e.__class__.__name__})"

    return False, "Tipo de disco não identificado"


def _limpar_cache_windows_update():
    """Para o serviço wuauserv, limpa o cache de downloads do Windows Update e religa o serviço.

    O serviço é sempre religado, mesmo em caso de erro no meio do processo,
    para não deixar o Windows Update travado.

    Returns:
        Tuple[bool, str]: sucesso e descrição.
    """
    try:
        windir = os.getenv('SystemRoot')
        if not windir:
            return False, "Variável SystemRoot não encontrada"

        pasta_download = os.path.join(windir, 'SoftwareDistribution', 'Download')

        subprocess.run(['net', 'stop', 'wuauserv'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)

        removidos = 0
        if os.path.exists(pasta_download):
            for item in os.listdir(pasta_download):
                try:
                    DeleteArquivos(os.path.join(pasta_download, item))
                    removidos += 1
                except Exception:
                    continue

        return True, f"{removidos} itens de cache do Windows Update removidos"
    except Exception as e:
        return False, f"Falha na limpeza do cache do Windows Update ({e.__class__.__name__})"
    finally:
        # Garante que o serviço volte a rodar mesmo se algo falhar no meio do caminho
        try:
            subprocess.run(['net', 'start', 'wuauserv'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        except Exception:
            pass


def _liberar_memoria_sistema():
    """Libera RAM de todo o sistema, não só do processo do GCleaner.

    A versão original chamava EmptyWorkingSet apenas no próprio processo do
    app, que já é minúsculo — sem efeito perceptível. Esta versão percorre os
    processos do usuário (como o Mem Reduct ou o RAMMap fazem) e força a
    liberação do working set de cada um, devolvendo páginas inativas de RAM
    física ao sistema. É importante deixar claro para o usuário que esse é um
    efeito temporário — processos ativos voltam a reivindicar a RAM que
    precisam logo depois — mas ajuda a "destravar" RAM ociosa acumulada por
    apps em segundo plano.

    Returns:
        Tuple[bool, str]: sucesso e quantos processos foram afetados.
    """
    if psutil is None:
        return False, "psutil não disponível"

    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_SET_QUOTA = 0x0100
    acesso = PROCESS_QUERY_INFORMATION | PROCESS_SET_QUOTA

    afetados = 0
    pid_proprio = os.getpid()

    try:
        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi

        for proc in psutil.process_iter(['pid']):
            pid = proc.info['pid']
            if pid in (0, 4, pid_proprio):
                continue
            try:
                handle = kernel32.OpenProcess(acesso, False, pid)
                if handle:
                    if psapi.EmptyWorkingSet(handle):
                        afetados += 1
                    kernel32.CloseHandle(handle)
            except Exception:
                continue

        return True, f"RAM liberada em {afetados} processos"
    except Exception as e:
        return False, f"Falha ao liberar memória ({e.__class__.__name__})"

def _limpar_componentes_windows():
    """Executa DISM para limpar componentes antigos do WinSxS.

    É a operação que mais libera espaço em disco em máquinas que acumularam
    muitas atualizações — pode devolver vários GBs. Demora mais que as outras
    etapas (o timeout é generoso), e exige privilégios de Administrador.

    Returns:
        Tuple[bool, str]
    """
    try:
        resultado = subprocess.run(
            ['dism', '/Online', '/Cleanup-Image', '/StartComponentCleanup'],
            capture_output=True, text=True, shell=True, timeout=600
        )
        if resultado.returncode == 0:
            return True, "Componentes WinSxS limpos com sucesso"
        # DISM retorna 3010 quando precisa de reinicialização (ainda é sucesso)
        if resultado.returncode == 3010:
            return True, "WinSxS limpo — reinicie o PC para concluir"
        return False, f"DISM retornou código {resultado.returncode}"
    except subprocess.TimeoutExpired:
        return False, "DISM excedeu o tempo limite (10 min) — rode manualmente como Administrador"
    except Exception as e:
        return False, f"Falha no DISM ({e.__class__.__name__})"

def sysoptimize(progressAtt, simulacao=False):
    """Faz a otimização real do sistema.

    Etapas: plano de energia → limpeza de planos duplicados → logs →
    TRIM/desfrag → cache do Windows Update → DISM/WinSxS → liberação de RAM.

    Args:
        progressAtt (function): Callback para atualizar a barra de progresso.
        simulacao (bool): Se True, descreve o que seria feito sem executar nada.

    Returns:
        list[Tuple[str, bool, str]]: lista de (etapa, sucesso, detalhe).
    """
    if simulacao:
        drive = os.getenv('SystemDrive', 'C:').rstrip('\\')
        progressAtt(1.0)
        time.sleep(0.3)
        progressAtt(0)
        return [
            ("Plano de energia",         True, "[SIMULAÇÃO] Ativaria Desempenho Máximo ou Alto Desempenho"),
            ("Planos duplicados",         True, "[SIMULAÇÃO] Removeria cópias excedentes de planos de energia"),
            ("Logs do sistema",           True, f"[SIMULAÇÃO] Limparia arquivos em %SystemRoot%\\Logs"),
            ("Otimização de disco",       True, f"[SIMULAÇÃO] Aplicaria TRIM/Desfrag no disco {drive}"),
            ("Cache Windows Update",      True, "[SIMULAÇÃO] Limparia SoftwareDistribution\\Download"),
            ("Limpeza WinSxS (DISM)",     True, "[SIMULAÇÃO] Rodaria DISM /Cleanup-Image /StartComponentCleanup"),
            ("Liberação de memória",      True, "[SIMULAÇÃO] Liberaria RAM dos processos em background"),
        ]

    resultados = []
    progressAtt(0.05)
    time.sleep(0.1)

    sucesso, detalhe = ajustar_plano_energia()
    resultados.append(("Plano de energia", sucesso, detalhe))
    progressAtt(0.15)

    sucesso, detalhe = limpar_planos_duplicados()
    resultados.append(("Planos duplicados", sucesso, detalhe))
    progressAtt(0.28)

    sucesso, detalhe = _limpar_logs_sistema()
    resultados.append(("Logs do sistema", sucesso, detalhe))
    progressAtt(0.42)

    sucesso, detalhe = _otimizar_disco()
    resultados.append(("Otimização de disco", sucesso, detalhe))
    progressAtt(0.58)

    sucesso, detalhe = _limpar_cache_windows_update()
    resultados.append(("Cache Windows Update", sucesso, detalhe))
    progressAtt(0.72)

    sucesso, detalhe = _limpar_componentes_windows()
    resultados.append(("Limpeza WinSxS (DISM)", sucesso, detalhe))
    progressAtt(0.88)

    sucesso, detalhe = _liberar_memoria_sistema()
    resultados.append(("Liberação de memória", sucesso, detalhe))

    progressAtt(1.0)
    time.sleep(0.5)
    progressAtt(0)
    return resultados

