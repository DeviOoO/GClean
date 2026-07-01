import subprocess
import os
import re
import ctypes
import json
import logging

try:
    import psutil
except ImportError:
    psutil = None

_PASTA_APP = os.path.join(os.getenv('LOCALAPPDATA', '.'), 'GCleaner')
_ARQ_PLANO_ORIGINAL = os.path.join(_PASTA_APP, 'plano_original.txt')



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