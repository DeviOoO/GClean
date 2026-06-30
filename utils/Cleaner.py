import subprocess
import os
import shutil
import time
import re
import ctypes

try:
    import psutil
except ImportError:
    psutil = None


def _limpar_cache_rede():
    """Limpa o cache de resolução DNS e NetBIOS.

    Returns:
        Tuple[bool, str]
    """
    try:
        subprocess.run(['ipconfig', '/flushdns'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        subprocess.run(['nbtstat', '-R'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        subprocess.run(['nbtstat', '-rr'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        return True, "Cache DNS e NetBIOS limpos"
    except Exception as e:
        return False, f"Falha ao limpar cache de rede ({e.__class__.__name__})"


def _renovar_ip():
    """Libera e renova o IP via DHCP.

    `ipconfig /release` e `/renew` só afetam adaptadores configurados para
    obter IP automaticamente — adaptadores com IP estático (comum em
    ambientes de laboratório/empresa) não são alterados por esses comandos.

    Returns:
        Tuple[bool, str]
    """
    try:
        subprocess.run(['ipconfig', '/release'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        # Timeout maior na renovação: o DHCP do roteador pode demorar para responder
        subprocess.run(['ipconfig', '/renew'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        return True, "IP liberado e renovado (adaptadores com IP estático não são afetados)"
    except subprocess.TimeoutExpired:
        return False, "Renovação de IP excedeu o tempo limite — verifique o DHCP do roteador"
    except Exception as e:
        return False, f"Falha ao renovar IP ({e.__class__.__name__})"


def _resetar_protocolos():
    """Reseta os catálogos Winsock e IP (correção de erros de tráfego mais profundos).

    Returns:
        Tuple[bool, str]
    """
    try:
        subprocess.run(['netsh', 'winsock', 'reset'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        subprocess.run(['netsh', 'int', 'ip', 'reset'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        return True, "Catálogos Winsock/IP resetados (reinicie o PC para efeito completo)"
    except Exception as e:
        return False, f"Falha ao resetar protocolos ({e.__class__.__name__})"


def _resetar_firewall_seguro():
    """Reseta o Firewall do Windows, mas só depois de fazer backup das regras atuais.

    A versão original chamava `netsh advfirewall reset` direto, o que apaga
    regras customizadas (VPN, jogos com portas liberadas, softwares de
    monitoramento da empresa) sem nenhuma chance de desfazer. Agora o backup
    é salvo em %TEMP% antes do reset, e o reset só ocorre se o backup for
    confirmado no disco.

    Returns:
        Tuple[bool, str]
    """
    try:
        temp_dir = os.getenv('TEMP', '.')
        backup_path = os.path.join(temp_dir, f'gcleaner_firewall_backup_{int(time.time())}.wfw')

        subprocess.run(
            ['netsh', 'advfirewall', 'export', f'"{backup_path}"'],
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10
        )

        if not os.path.exists(backup_path):
            return False, "Backup do firewall falhou — reset cancelado por segurança"

        subprocess.run(['netsh', 'advfirewall', 'reset'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        return True, f"Firewall resetado (backup salvo em {backup_path})"
    except Exception as e:
        return False, f"Falha ao resetar firewall ({e.__class__.__name__})"


def _otimizar_tcp():
    """Ajusta parâmetros de TCP e desativa o compartilhamento P2P do Windows Update.

    Returns:
        Tuple[bool, str]
    """
    try:
        subprocess.run(['netsh', 'int', 'tcp', 'set', 'heuristics', 'disabled'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        subprocess.run(['netsh', 'int', 'tcp', 'set', 'global', 'autotuninglevel=normal'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        subprocess.run(['powershell', '-Command', 'Set-SeedingPreference -Value 0'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        return True, "TCP ajustado e compartilhamento P2P do Windows Update desativado"
    except Exception as e:
        return False, f"Falha ao otimizar TCP ({e.__class__.__name__})"


def _aplicar_dns_seguro():
    """Aplica DNS Cloudflare (1.1.1.1/1.0.0.1) só em adaptadores no automático.

    A versão original sobrescrevia o DNS de qualquer adaptador ativo, mesmo
    que o usuário (ou a empresa) já tivesse configurado um DNS manual —
    podendo derrubar acesso a recursos internos, VPN ou Pi-hole. Agora, cada
    adaptador é verificado antes: só recebe o DNS Cloudflare se já estiver no
    automático (DHCP). DNS configurado manualmente é preservado.

    Returns:
        Tuple[bool, str]
    """
    try:
        comando = (
            "$adaptadores = Get-NetAdapter | Where-Object {$_.Status -eq 'Up'}; "
            "foreach ($a in $adaptadores) { "
            "$dns = Get-DnsClientServerAddress -InterfaceAlias $a.Name -AddressFamily IPv4; "
            "if (-not $dns.ServerAddresses -or $dns.ServerAddresses.Count -eq 0) { "
            "Write-Output \"AUTOMATICO|$($a.Name)\" "
            "} else { "
            "Write-Output \"MANUAL|$($a.Name)\" "
            "} }"
        )
        resultado = subprocess.run(['powershell', '-Command', comando], capture_output=True, text=True, shell=True, timeout=10)
        linhas = [l.strip() for l in (resultado.stdout or "").splitlines() if l.strip()]

        alterados = []
        preservados = []

        for linha in linhas:
            if '|' not in linha:
                continue
            status, nome_placa = linha.split('|', 1)
            if status == "AUTOMATICO":
                subprocess.run(['netsh', 'interface', 'ipv4', 'set', 'dns', f'name="{nome_placa}"', 'static', '1.1.1.1', 'primary'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                subprocess.run(['netsh', 'interface', 'ipv4', 'add', 'dns', f'name="{nome_placa}"', '1.0.0.1', 'index=2'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                alterados.append(nome_placa)
            else:
                preservados.append(nome_placa)

        partes = []
        if alterados:
            partes.append(f"Cloudflare aplicado em: {', '.join(alterados)}")
        if preservados:
            partes.append(f"DNS manual preservado em: {', '.join(preservados)}")
        if not partes:
            partes.append("Nenhum adaptador ativo encontrado")

        return True, " | ".join(partes)
    except Exception as e:
        return False, f"Falha ao configurar DNS ({e.__class__.__name__})"


def netclean(progressAtt):
    """Faz a correção profunda e otimização da rede/DNS.

    Args:
        progressAtt (function): Função callback para atualizar a barra de progresso.

    Returns:
        list[Tuple[str, bool, str]]: lista de (etapa, sucesso, detalhe) para exibir ao usuário.
    """
    resultados = []
    progressAtt(0.05)
    time.sleep(0.1)

    sucesso, detalhe = _limpar_cache_rede()
    resultados.append(("Cache de rede/DNS", sucesso, detalhe))
    progressAtt(0.20)

    sucesso, detalhe = _renovar_ip()
    resultados.append(("Renovação de IP", sucesso, detalhe))
    progressAtt(0.45)

    sucesso, detalhe = _resetar_protocolos()
    resultados.append(("Reset de protocolos", sucesso, detalhe))
    progressAtt(0.60)

    sucesso, detalhe = _resetar_firewall_seguro()
    resultados.append(("Firewall (com backup)", sucesso, detalhe))
    progressAtt(0.70)

    sucesso, detalhe = _otimizar_tcp()
    resultados.append(("Otimização TCP", sucesso, detalhe))
    progressAtt(0.85)

    sucesso, detalhe = _aplicar_dns_seguro()
    resultados.append(("DNS", sucesso, detalhe))

    progressAtt(1.0)
    time.sleep(0.5)
    progressAtt(0)
    return resultados


def DeleteArquivos(caminho):
    """Deleta arquivos ou subdiretórios de forma segura sem derrubar a pasta raiz."""
    try:
        if os.path.isfile(caminho) or os.path.islink(caminho):
            os.remove(caminho)
        elif os.path.isdir(caminho):
            shutil.rmtree(caminho, ignore_errors=True)
    except Exception:
        raise


def cachetempclean(progressAtt):
    """Faz a limpeza dos arquivos temporarios

    Args:
        progressAtt (function): Função callback para atualizar a barra de progresso.

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


# ---------------------------------------------------------------------------
# Otimização do sistema — funções auxiliares
# ---------------------------------------------------------------------------

def _tentar_ativar_plano(guid):
    """Tenta ativar um plano de energia pelo GUID e confirma via /getactivescheme.

    Args:
        guid (str): GUID do plano a ativar.

    Returns:
        bool: True se o plano ficou ativo, False caso contrário.
    """
    subprocess.run(
        ['powercfg', '/setactive', guid],
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5
    )
    verificacao = subprocess.run(
        ['powercfg', '/getactivescheme'], shell=True, capture_output=True, text=True, timeout=5
    )
    return guid.lower() in (verificacao.stdout or "").lower()


def _duplicar_e_ativar(guid_template):
    """Duplica um plano oculto a partir do template da Microsoft e ativa a cópia.

    Args:
        guid_template (str): GUID do plano template a duplicar.

    Returns:
        str | None: GUID da cópia criada, ou None se falhou.
    """
    duplicado = subprocess.run(
        ['powercfg', '/duplicatescheme', guid_template],
        shell=True, capture_output=True, text=True, timeout=5
    )
    match = re.search(
        r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',
        duplicado.stdout or ""
    )
    if not match:
        return None
    novo_guid = match.group(0)
    subprocess.run(
        ['powercfg', '/setactive', novo_guid],
        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5
    )
    return novo_guid


def _ajustar_plano_energia():
    """Tenta ativar o melhor plano de energia disponível, em ordem de prioridade:

    1. Desempenho Máximo (Ultimate Performance) — template oculto da Microsoft
       (GUID e9a42b02-d5df-448d-aa00-03f14749eb61). Oferece o máximo de
       desempenho eliminando micro-latências de gerenciamento de energia. Pode
       já estar duplicado na máquina; se não estiver, é criado via
       /duplicatescheme.
    2. Alto Desempenho — fallback caso o template de Desempenho Máximo não
       possa ser duplicado (GUID 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c).
       Mesma lógica: tenta ativar direto; se não existir, duplica e ativa.

    Em notebooks na bateria nenhum plano é alterado, para não aumentar o
    consumo/temperatura sem o usuário saber o motivo.

    Returns:
        Tuple[bool, str]: sucesso e mensagem descritiva.
    """
    GUID_MAXIMO      = "e9a42b02-d5df-448d-aa00-03f14749eb61"
    GUID_ALTO        = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"

    # Guarda GUID original para restaurar se nenhum plano superior funcionar
    guid_original = None

    if psutil is not None:
        try:
            bateria = psutil.sensors_battery()
            if bateria is not None and not bateria.power_plugged:
                return False, "Notebook na bateria — plano de energia mantido para economizar carga"
        except Exception:
            pass

    try:
        # Preserva o plano atual antes de alterar qualquer coisa
        atual = subprocess.run(
            ['powercfg', '/getactivescheme'], shell=True, capture_output=True, text=True, timeout=5
        )
        match_atual = re.search(
            r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',
            atual.stdout or ""
        )
        if match_atual:
            guid_original = match_atual.group(0)

        # --- Tentativa 1: Desempenho Máximo já existente na máquina ---
        if _tentar_ativar_plano(GUID_MAXIMO):
            return True, "Plano Desempenho Máximo ativado"

        # --- Tentativa 2: Duplicar o template oculto de Desempenho Máximo ---
        novo = _duplicar_e_ativar(GUID_MAXIMO)
        if novo:
            return True, "Plano Desempenho Máximo criado e ativado"

        # --- Tentativa 3: Alto Desempenho já existente ---
        if _tentar_ativar_plano(GUID_ALTO):
            return True, "Desempenho Máximo indisponível — Plano Alto Desempenho ativado"

        # --- Tentativa 4: Duplicar o template de Alto Desempenho ---
        novo = _duplicar_e_ativar(GUID_ALTO)
        if novo:
            return True, "Desempenho Máximo indisponível — Plano Alto Desempenho criado e ativado"

        return False, "Não foi possível ativar nenhum plano de alto desempenho"

    except Exception as e:
        return False, f"Falha ao ajustar plano de energia ({e.__class__.__name__})"


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


def sysoptimize(progressAtt):
    """Faz a otimização real do sistema.

    Etapas: plano de energia (com checagem de bateria), limpeza de logs,
    TRIM/desfragmentação conforme o tipo de disco, limpeza de cache do
    Windows Update e liberação de RAM em nível de sistema.

    Args:
        progressAtt (function): Função callback para atualizar a barra de progresso.

    Returns:
        list[Tuple[str, bool, str]]: lista de (etapa, sucesso, detalhe) para exibir ao usuário.
    """
    resultados = []
    progressAtt(0.05)
    time.sleep(0.1)

    sucesso, detalhe = _ajustar_plano_energia()
    resultados.append(("Plano de energia", sucesso, detalhe))
    progressAtt(0.25)

    sucesso, detalhe = _limpar_logs_sistema()
    resultados.append(("Logs do sistema", sucesso, detalhe))
    progressAtt(0.40)

    sucesso, detalhe = _otimizar_disco()
    resultados.append(("Otimização de disco", sucesso, detalhe))
    progressAtt(0.65)

    sucesso, detalhe = _limpar_cache_windows_update()
    resultados.append(("Cache do Windows Update", sucesso, detalhe))
    progressAtt(0.85)

    sucesso, detalhe = _liberar_memoria_sistema()
    resultados.append(("Liberação de memória", sucesso, detalhe))

    progressAtt(1.0)
    time.sleep(0.5)
    progressAtt(0)
    return resultados