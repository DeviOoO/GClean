import subprocess
import os
import sys

_NOME_TAREFA_AGENDADA = "GCleaner_Limpeza_Semanal"

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