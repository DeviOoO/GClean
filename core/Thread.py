import threading
from multiprocessing import Process

def SegundoPlano(Alvo):
    thread = threading.Thread(target=Alvo)
    thread.start()
    return 0