import subprocess
import os
import shutil
import time
import re
import ctypes
import json
import sys
import logging

try:
    import winreg
except ImportError:
    winreg = None

try:
    import psutil
except ImportError:
    psutil = None

# ---------------------------------------------------------------------------
# Constantes de persistência (salva dados do app entre sessões)
# ---------------------------------------------------------------------------
_PASTA_APP = os.path.join(os.getenv('LOCALAPPDATA', '.'), 'GCleaner')
_ARQ_PLANO_ORIGINAL = os.path.join(_PASTA_APP, 'plano_original.txt')
_NOME_TAREFA_AGENDADA = "GCleaner_Limpeza_Semanal"


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


def netclean(progressAtt, simulacao=False):
    """Faz a correção profunda e otimização da rede/DNS.

    Args:
        progressAtt (function): Função callback para atualizar a barra de progresso.
        simulacao (bool): Se True, descreve o que seria feito sem executar nada.

    Returns:
        list[Tuple[str, bool, str]]: lista de (etapa, sucesso, detalhe) para exibir ao usuário.
    """
    if simulacao:
        progressAtt(1.0)
        time.sleep(0.3)
        progressAtt(0)
        return [
            ("Cache de rede/DNS",   True, "[SIMULAÇÃO] Limparia cache DNS e NetBIOS"),
            ("Renovação de IP",     True, "[SIMULAÇÃO] Faria release/renew do IP via DHCP"),
            ("Reset de protocolos", True, "[SIMULAÇÃO] Resetaria catálogos Winsock e IP stack"),
            ("Firewall (com backup)",True,"[SIMULAÇÃO] Exportaria backup e resetaria regras do firewall"),
            ("Otimização TCP",      True, "[SIMULAÇÃO] Desabilitaria heuristics TCP e P2P do Windows Update"),
            ("DNS",                 True, "[SIMULAÇÃO] Aplicaria Cloudflare 1.1.1.1 nos adaptadores em DHCP"),
        ]
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


def _oem_encoding():
    """Retorna o code page OEM do Windows (ex: 'cp850') para decodificar saída do console.

    O console do Windows usa o code page OEM (GetOEMCP), diferente do code page
    ANSI (CP1252) que o Python usa por padrão com text=True. Misturar os dois
    faz caracteres acentuados — como o 'á' de 'Máximo' — virarem lixo ou
    espaços não-quebráveis, quebrando a busca por nome de plano de energia.
    """
    try:
        oem = ctypes.windll.kernel32.GetOEMCP()
        return f'cp{oem}'
    except Exception:
        return 'cp850'  # fallback: CP850 é o padrão OEM no Brasil e Europa Ocidental


def _normalizar(texto):
    """Remove acentos e converte para minúsculo para comparação segura entre encodings."""
    import unicodedata
    sem_acento = ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )
    return sem_acento.lower()


def _listar_planos_energia():
    """Lista todos os planos de energia já existentes na máquina via `powercfg /list`.

    Decodifica a saída com o code page OEM real do console (via GetOEMCP) em vez
    de deixar o Python usar CP1252 por padrão — evitando que 'á' de 'Máximo'
    vire lixo/espaço e quebre a busca por nome.

    Returns:
        list[Tuple[str, str]]: lista de (guid, nome_do_plano).
    """
    try:
        resultado = subprocess.run(
            ['powercfg', '/list'], shell=True, capture_output=True, timeout=5
        )
        texto = resultado.stdout.decode(_oem_encoding(), errors='replace')
    except Exception:
        return []

    planos = []
    padrao_linha = re.compile(
        r'([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\s*\((.*?)\)'
    )
    for linha in texto.splitlines():
        match = padrao_linha.search(linha)
        if match:
            planos.append((match.group(1), match.group(2).strip()))
    return planos


def _buscar_guid_por_nome(planos, padroes_nome):
    """Procura, entre os planos já existentes, um cujo nome bata com algum padrão.

    Usa _normalizar() em ambos os lados da comparação para ser imune a
    diferenças de encoding ou acentuação entre o que o Windows retorna e o
    que passamos como padrão (ex: 'maximo' bate com 'Máximo' ou 'M ximo').

    Args:
        planos (list[Tuple[str, str]]): saída de _listar_planos_energia().
        padroes_nome (list[str]): trechos a procurar no nome do plano.

    Returns:
        str | None: GUID do plano encontrado, ou None.
    """
    padroes_norm = [_normalizar(p) for p in padroes_nome]
    for guid, nome in planos:
        nome_norm = _normalizar(nome)
        if any(padrao in nome_norm for padrao in padroes_norm):
            return guid
    return None


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


def _guid_plano_ativo():
    """Lê o GUID do plano de energia atualmente ativo.

    Returns:
        str | None
    """
    try:
        atual = subprocess.run(
            ['powercfg', '/getactivescheme'], shell=True, capture_output=True, text=True, timeout=5
        )
        match = re.search(
            r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',
            atual.stdout or ""
        )
        return match.group(0) if match else None
    except Exception:
        return None


def _limpar_planos_duplicados(planos, nomes_padroes, manter_guid=None):
    """Remove planos de energia duplicados (mesmo nome) acumulados de execuções
    anteriores, mantendo apenas um.

    Isso resolve o acúmulo de várias cópias de "Desempenho Máximo" que ficavam
    para trás quando o GClean ainda comparava pelo GUID do template em vez do
    nome — cada otimização criava uma cópia nova sem nunca reconhecer as
    anteriores.

    Args:
        planos (list[Tuple[str, str]]): saída de _listar_planos_energia().
        nomes_padroes (list[str]): trechos (lowercase) que identificam o grupo de planos.
        manter_guid (str | None): GUID a preservar preferencialmente, se fizer parte do grupo.

    Returns:
        Tuple[int, list[str]]: quantidade removida e lista de GUIDs removidos.
    """
    candidatos = [(guid, nome) for guid, nome in planos if any(p in nome.lower() for p in nomes_padroes)]
    if len(candidatos) <= 1:
        return 0, []

    guid_para_manter = manter_guid if manter_guid and any(g == manter_guid for g, _ in candidatos) else candidatos[0][0]
    guid_ativo = _guid_plano_ativo()

    removidos = []
    for guid, _ in candidatos:
        if guid == guid_para_manter:
            continue
        # O Windows não deixa apagar o plano ativo no momento; pula e tenta na próxima execução
        if guid_ativo and guid.lower() == guid_ativo.lower():
            continue
        try:
            subprocess.run(
                ['powercfg', '/delete', guid],
                shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5
            )
            removidos.append(guid)
        except Exception:
            continue

    return len(removidos), removidos


def _arquivo_estado_gclean():
    """Caminho do arquivo de estado persistente do GClean (em %APPDATA%\\GCleaner).

    Returns:
        str
    """
    pasta = os.path.join(os.getenv('APPDATA', '.'), 'GCleaner')
    try:
        os.makedirs(pasta, exist_ok=True)
    except Exception:
        pass
    return os.path.join(pasta, 'estado.json')


def _ler_estado_gclean():
    """Lê o arquivo de estado persistente, devolvendo {} se não existir ou estiver corrompido."""
    caminho = _arquivo_estado_gclean()
    if not os.path.exists(caminho):
        return {}
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _salvar_estado_gclean(dados):
    """Grava o dicionário de estado no disco, ignorando falhas silenciosamente."""
    try:
        with open(_arquivo_estado_gclean(), 'w', encoding='utf-8') as f:
            json.dump(dados, f)
    except Exception:
        pass


def _salvar_plano_original_se_necessario(guid_atual):
    """Guarda o GUID do plano de energia ativo ANTES de qualquer alteração do
    GClean — mas só na primeira vez. Se já houver um valor salvo, não
    sobrescreve, para que uma segunda otimização não grave "Desempenho
    Máximo" como se fosse o plano "original" do usuário.
    """
    if not guid_atual:
        return
    dados = _ler_estado_gclean()
    if 'plano_energia_original' not in dados:
        dados['plano_energia_original'] = guid_atual
        _salvar_estado_gclean(dados)


def restaurar_plano_energia_original():
    """Restaura o plano de energia que estava ativo antes da primeira vez que
    o GClean alterou as configurações de energia.

    Returns:
        Tuple[bool, str]
    """
    dados = _ler_estado_gclean()
    guid_original = dados.get('plano_energia_original')

    if not guid_original:
        return False, "Nenhum plano original salvo ainda — rode a Otimização de Sistema ao menos uma vez antes"

    try:
        if _tentar_ativar_plano(guid_original):
            return True, "Plano de energia original restaurado"
        return False, "Não foi possível reativar o plano original (pode ter sido removido do sistema)"
    except Exception as e:
        return False, f"Falha ao restaurar plano original ({e.__class__.__name__})"


def _ajustar_plano_energia():
    """Tenta ativar o melhor plano de energia disponível, em ordem de prioridade:

    1. Desempenho Máximo (Ultimate Performance) — template oculto da Microsoft
       (GUID e9a42b02-d5df-448d-aa00-03f14749eb61). Antes de duplicar, busca em
       `powercfg /list` se algum plano já existente tem nome de Desempenho
       Máximo/Ultimate Performance e, se achar, apenas ativa esse. Também
       consolida duplicatas acumuladas de execuções anteriores, mantendo só
       uma cópia.
    2. Alto Desempenho — fallback caso o template de Desempenho Máximo não
       possa ser duplicado (GUID 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c). Mesma
       lógica de busca por nome e consolidação antes de duplicar.

    O plano ativo antes da primeira execução é salvo em disco, permitindo
    restaurá-lo depois via restaurar_plano_energia_original().

    Em notebooks na bateria nenhum plano é alterado, para não aumentar o
    consumo/temperatura sem o usuário saber o motivo.

    Returns:
        Tuple[bool, str]: sucesso e mensagem descritiva.
    """
    dados = _ler_estado_gclean()
    guid_original = dados.get('plano_energia_original')

    GUID_MAXIMO = "e9a42b02-d5df-448d-aa00-03f14749eb61"
    GUID_ALTO = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"

    NOMES_MAXIMO = ["desempenho máximo", "desempenho maximo", "ultimate performance"]
    NOMES_ALTO = ["alto desempenho", "high performance"]

    if psutil is not None:
        try:
            bateria = psutil.sensors_battery()
            if bateria is not None and not bateria.power_plugged:
                return False, "Notebook na bateria — plano de energia mantido para economizar carga"
        except Exception:
            pass

    try:
        _salvar_plano_original_se_necessario(_guid_plano_ativo())

        planos = _listar_planos_energia()

        # Consolida duplicatas acumuladas de execuções anteriores ao fix de busca-por-nome
        removidos_max, _ = _limpar_planos_duplicados(planos, NOMES_MAXIMO)
        removidos_alto, _ = _limpar_planos_duplicados(planos, NOMES_ALTO)
        if removidos_max or removidos_alto:
            planos = _listar_planos_energia()

        def sufixo_limpeza(qtd):
            return f" ({qtd} duplicata(s) antiga(s) removida(s))" if qtd else ""

        # Salva o plano original em disco antes de qualquer troca.
        # Só grava se ainda não existir (mantém o plano "verdadeiro" do usuário,
        # não o plano do GCleaner de uma execução anterior).
        try:
            if guid_original and not os.path.exists(_ARQ_PLANO_ORIGINAL):
                os.makedirs(_PASTA_APP, exist_ok=True)
                with open(_ARQ_PLANO_ORIGINAL, 'w') as f:
                    f.write(guid_original)
        except OSError as e:
            logging.warning("Não foi possível salvar o plano original: %s", e)

        # --- Desempenho Máximo: busca por nome antes de duplicar de novo ---
        guid_existente = _buscar_guid_por_nome(planos, NOMES_MAXIMO)
        if guid_existente and _tentar_ativar_plano(guid_existente):
            return True, f"Plano Desempenho Máximo já existia — ativado sem duplicar{sufixo_limpeza(removidos_max)}"

        # Também cobre o caso raro do template já estar listado com o próprio GUID padrão
        if any(guid.lower() == GUID_MAXIMO.lower() for guid, _ in planos):
            if _tentar_ativar_plano(GUID_MAXIMO):
                return True, f"Plano Desempenho Máximo ativado{sufixo_limpeza(removidos_max)}"

        novo = _duplicar_e_ativar(GUID_MAXIMO)
        if novo:
            return True, f"Plano Desempenho Máximo criado e ativado{sufixo_limpeza(removidos_max)}"

        # --- Fallback: Alto Desempenho, mesma lógica de não duplicar à toa ---
        guid_existente = _buscar_guid_por_nome(planos, NOMES_ALTO)
        if guid_existente and _tentar_ativar_plano(guid_existente):
            return True, f"Desempenho Máximo indisponível — Plano Alto Desempenho já existia, ativado sem duplicar{sufixo_limpeza(removidos_alto)}"

        if any(guid.lower() == GUID_ALTO.lower() for guid, _ in planos):
            if _tentar_ativar_plano(GUID_ALTO):
                return True, f"Desempenho Máximo indisponível — Plano Alto Desempenho ativado{sufixo_limpeza(removidos_alto)}"

        novo = _duplicar_e_ativar(GUID_ALTO)
        if novo:
            return True, f"Desempenho Máximo indisponível — Plano Alto Desempenho criado e ativado{sufixo_limpeza(removidos_alto)}"

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

    sucesso, detalhe = _ajustar_plano_energia()
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


# ===========================================================================
# Funções públicas novas
# ===========================================================================

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


def limpar_planos_duplicados():
    """Remove cópias excedentes de planos de energia acumuladas por execuções anteriores.

    O /duplicatescheme sempre gera um GUID diferente a cada chamada, então
    sem essa limpeza cada otimização criaria mais um "Desempenho Máximo (2)",
    "(3)", etc. Esta função mantém apenas UM plano de cada tipo (o primeiro
    encontrado na lista) e apaga os demais.

    Returns:
        Tuple[bool, str]
    """
    NOMES_MAXIMO = ["desempenho máximo", "desempenho maximo", "ultimate performance"]
    NOMES_ALTO   = ["alto desempenho", "high performance"]

    try:
        planos = _listar_planos_energia()
        grupos = {"maximo": [], "alto": []}

        for guid, nome in planos:
            nome_l = nome.lower()
            if any(p in nome_l for p in NOMES_MAXIMO):
                grupos["maximo"].append((guid, nome))
            elif any(p in nome_l for p in NOMES_ALTO):
                grupos["alto"].append((guid, nome))

        deletados = 0
        for lista in grupos.values():
            for guid, _ in lista[1:]:   # Mantém o [0], apaga o resto
                try:
                    subprocess.run(
                        ['powercfg', '/delete', guid],
                        shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5
                    )
                    deletados += 1
                except Exception:
                    continue

        if deletados == 0:
            return True, "Nenhum plano duplicado encontrado"
        return True, f"{deletados} plano(s) duplicado(s) removido(s)"
    except Exception as e:
        return False, f"Falha ao limpar planos duplicados ({e.__class__.__name__})"


def restaurar_plano_energia():
    """Restaura o plano de energia que estava ativo antes do GCleaner alterar.

    O GUID original é salvo em %LOCALAPPDATA%\\GCleaner\\plano_original.txt na
    primeira vez que o sysoptimize é executado. Este arquivo persiste entre
    sessões, então o usuário pode restaurar mesmo após reiniciar o app.

    Returns:
        Tuple[bool, str]
    """
    try:
        if not os.path.exists(_ARQ_PLANO_ORIGINAL):
            return False, "Nenhum plano original salvo — rode 'Otimizar Sistema' ao menos uma vez"
        with open(_ARQ_PLANO_ORIGINAL, 'r') as f:
            guid = f.read().strip()
        if not guid:
            return False, "Arquivo de plano original está vazio"
        if _tentar_ativar_plano(guid):
            return True, f"Plano original restaurado ({guid})"
        return False, f"Não foi possível ativar o plano salvo ({guid}) — pode ter sido deletado"
    except Exception as e:
        return False, f"Falha ao restaurar plano ({e.__class__.__name__})"


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


# ---------------------------------------------------------------------------
# Gerenciador de inicialização
# ---------------------------------------------------------------------------

def listar_itens_inicializacao():
    """Lista todos os programas que iniciam com o Windows.

    Lê dois locais: chaves Run do registro (HKCU e HKLM) e tarefas do Task
    Scheduler marcadas para rodar no logon. Para cada item determina se está
    habilitado ou desabilitado via a chave StartupApproved.

    Returns:
        list[dict]: cada dict tem chaves nome, caminho, habilitado, fonte.
                    Retorna lista vazia se winreg não estiver disponível.
    """
    if winreg is None:
        return []

    itens = []

    def _status_aprovado(hive, aprovado_path, nome):
        """Retorna True se o item estiver habilitado na chave StartupApproved."""
        try:
            chave = winreg.OpenKey(hive, aprovado_path)
            dados, _ = winreg.QueryValueEx(chave, nome)
            winreg.CloseKey(chave)
            # Primeiro byte: 0x02 = habilitado, 0x03 = desabilitado
            return isinstance(dados, (bytes, bytearray)) and dados[0] == 0x02
        except Exception:
            return True  # Sem entrada no StartupApproved = habilitado por padrão

    chaves = [
        (winreg.HKEY_CURRENT_USER,
         r"Software\Microsoft\Windows\CurrentVersion\Run",
         r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
         "HKCU"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"Software\Microsoft\Windows\CurrentVersion\Run",
         r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
         "HKLM"),
    ]

    for hive, run_path, aprovado_path, fonte in chaves:
        try:
            chave_run = winreg.OpenKey(hive, run_path)
            i = 0
            while True:
                try:
                    nome, valor, _ = winreg.EnumValue(chave_run, i)
                    habilitado = _status_aprovado(hive, aprovado_path, nome)
                    itens.append({
                        "nome":       nome,
                        "caminho":    valor,
                        "habilitado": habilitado,
                        "fonte":      fonte,
                        "hive":       hive,
                        "run_path":   run_path,
                        "aprov_path": aprovado_path,
                    })
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(chave_run)
        except Exception:
            continue

    # Task Scheduler — tarefas de logon
    try:
        resultado = subprocess.run(
            ['schtasks', '/query', '/fo', 'CSV', '/v'],
            capture_output=True, text=True, shell=True, timeout=10
        )
        for linha in (resultado.stdout or "").splitlines()[1:]:
            partes = [p.strip('"') for p in linha.split('","')]
            if len(partes) < 9:
                continue
            gatilho = partes[8].lower() if len(partes) > 8 else ""
            if "logon" not in gatilho and "at log on" not in gatilho:
                continue
            nome_tarefa = partes[1] if len(partes) > 1 else ""
            status_str  = partes[3] if len(partes) > 3 else ""
            acao        = partes[6] if len(partes) > 6 else ""
            if not nome_tarefa or nome_tarefa == "TaskName":
                continue
            itens.append({
                "nome":       os.path.basename(nome_tarefa),
                "caminho":    acao,
                "habilitado": "disabled" not in status_str.lower(),
                "fonte":      "Agendador",
                "hive":       None,
                "run_path":   None,
                "aprov_path": None,
                "task_path":  nome_tarefa,
            })
    except Exception:
        pass

    return itens


def toggle_item_inicializacao(item, habilitar):
    """Habilita ou desabilita um item de inicialização.

    Para itens do registro, usa a chave StartupApproved (forma correta no
    Windows moderno — não apaga o valor Run, apenas marca como desabilitado).
    Para tarefas do Agendador, usa schtasks /change /enable ou /disable.

    Args:
        item (dict): um item retornado por listar_itens_inicializacao().
        habilitar (bool): True para habilitar, False para desabilitar.

    Returns:
        Tuple[bool, str]
    """
    nome = item.get("nome", "?")
    fonte = item.get("fonte", "")
    acao = "habilitado" if habilitar else "desabilitado"

    if fonte == "Agendador":
        task_path = item.get("task_path", nome)
        flag = "/enable" if habilitar else "/disable"
        try:
            subprocess.run(
                ['schtasks', '/change', '/tn', task_path, flag],
                shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10
            )
            return True, f"Tarefa '{nome}' {acao}"
        except Exception as e:
            return False, f"Falha ao alterar tarefa '{nome}' ({e.__class__.__name__})"

    if winreg is None:
        return False, "winreg não disponível"

    try:
        hive       = item.get("hive")
        aprov_path = item.get("aprov_path")
        if hive is None or aprov_path is None:
            return False, f"Dados insuficientes para alterar '{nome}'"

        # Cria/atualiza a chave StartupApproved com o byte de controle correto
        byte_status = 0x02 if habilitar else 0x03
        valor_bin   = bytes([byte_status]) + bytes(11)  # 12 bytes no total

        chave = winreg.OpenKey(
            hive, aprov_path, 0,
            winreg.KEY_SET_VALUE | winreg.KEY_CREATE_SUB_KEY
        )
        winreg.SetValueEx(chave, nome, 0, winreg.REG_BINARY, valor_bin)
        winreg.CloseKey(chave)
        return True, f"'{nome}' {acao} na inicialização"
    except Exception as e:
        return False, f"Falha ao alterar '{nome}' ({e.__class__.__name__})"


# ---------------------------------------------------------------------------
# Agendamento de limpeza automática
# ---------------------------------------------------------------------------

def agendar_limpeza_semanal(dia="DOM", horario="09:00"):
    """Cria uma tarefa no Agendador do Windows para rodar o GCleaner semanalmente.

    Args:
        dia (str): sigla do dia em português (SEG, TER, QUA, QUI, SEX, SAB, DOM).
        horario (str): horário no formato HH:MM.

    Returns:
        Tuple[bool, str]
    """
    # schtasks aceita abreviaturas em inglês
    mapa_dia = {
        "SEG": "MON", "TER": "TUE", "QUA": "WED",
        "QUI": "THU", "SEX": "FRI", "SAB": "SAT", "DOM": "SUN",
    }
    dia_en = mapa_dia.get(dia.upper(), "SUN")

    exe = sys.executable
    script = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'main.py'))

    try:
        subprocess.run([
            'schtasks', '/create',
            '/tn',  _NOME_TAREFA_AGENDADA,
            '/tr',  f'"{exe}" "{script}"',
            '/sc',  'weekly',
            '/d',   dia_en,
            '/st',  horario,
            '/rl',  'highest',   # Roda como Administrador
            '/f'                 # Sobrescreve se já existir
        ], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)

        return True, f"Limpeza agendada toda {dia} às {horario}"
    except Exception as e:
        return False, f"Falha ao agendar ({e.__class__.__name__})"


def cancelar_agendamento():
    """Remove a tarefa agendada do GCleaner do Agendador do Windows.

    Returns:
        Tuple[bool, str]
    """
    try:
        r = subprocess.run(
            ['schtasks', '/delete', '/tn', _NOME_TAREFA_AGENDADA, '/f'],
            shell=True, capture_output=True, timeout=10
        )
        if r.returncode == 0:
            return True, "Agendamento cancelado com sucesso"
        return False, "Tarefa não encontrada ou falha ao cancelar"
    except Exception as e:
        return False, f"Falha ao cancelar agendamento ({e.__class__.__name__})"


def verificar_agendamento():
    """Verifica se a tarefa agendada do GCleaner existe.

    Returns:
        bool
    """
    try:
        r = subprocess.run(
            ['schtasks', '/query', '/tn', _NOME_TAREFA_AGENDADA],
            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5
        )
        return r.returncode == 0
    except Exception:
        return False