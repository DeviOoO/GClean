import subprocess
import os

try:
    import winreg
except ImportError:
    winreg = None


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