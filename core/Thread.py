import threading
from multiprocessing import Process

def SegundoPlano(Alvo):
    """Executa a função enviada como argumento para ser feito em segundo plano.

    Args:
        Alvo (Function): Função a ser executada

    Returns:
        number: 0
    """    
    thread = threading.Thread(target=Alvo)
    thread.start()