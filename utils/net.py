import subprocess
import os
import time

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