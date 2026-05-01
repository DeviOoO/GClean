import tkinter as tk
import customtkinter as ctk
from utils.cleaner import *
from core.thread import *
import psutil

#Set de aparencia 
ctk.set_appearance_mode("system")
ctk.set_default_color_theme("dark-blue")

#Set de variaveis    
root = ctk.CTk()
root.title("GClenaer")
root.geometry("600x900")

uso = psutil.cpu_percent()
ram = psutil.virtual_memory()

frame = ctk.CTkFrame(master=root, corner_radius=(15), fg_color="#121316")
cpu = ctk.CTkFrame(master=frame, corner_radius= 20, fg_color= "#66C0F4")
progress = ctk.CTkProgressBar(master=frame, orientation="horizontal", corner_radius= 5, mode="determinate", width=500)
resultado_label = ctk.CTkLabel(master= cpu)

#Criação de Funções
def progressAtt(valor):
    root.after(0, progress.set(valor))
    
def atualizar_resultado(apagados, ignorados, total):
        resultado_label.pack()
        resultado_label.configure(
        text=f"Total de Arquivos: {total} | Apagados: {apagados} | Ignorados: {ignorados}"
    )

def LimpezaCache():
    apagados, ignorados, total = cachetempclean(progressAtt)
        
    root.after(0, atualizar_resultado, apagados, ignorados, total)
    root.after(0, EnableBtnCache)
    return 0

def LimpezaNet():
    netclean(progressAtt)
    root.after(0, EnableBtnNet)
    return 0

def LimpezaCacheExec():
    DisableBtnCache()
    SegundoPlano(LimpezaCache)
    return 0

def LimpezaNetExec():
    DisableBtnNet()
    SegundoPlano(LimpezaNet)
    return 0

def Geral():
    LimpezaCacheExec()
    LimpezaNetExec()
    return 0

#Criação de Butoes
btn_geral = ctk.CTkButton(master=frame, corner_radius= 5, fg_color="#2A475E", text="Limpeza Geral", font=("Bebas Neue", 20), command=Geral)
btn_cache = ctk.CTkButton(master=frame, corner_radius= 5, fg_color="#2A475E", text="Limpar apenas os Caches", font=("Bebas Neue", 20), command=LimpezaCacheExec)
btn_net = ctk.CTkButton(master=frame, corner_radius= 5, fg_color="#2A475E", text="Corrigir erros de Internet", font=("Bebas Neue", 20), command=LimpezaNetExec)

def DisableBtnCache():
    btn_cache.configure(text="Limpando...", state="disabled")
    return 0

def EnableBtnCache():
    btn_cache.configure(text="Limpar apenas os Caches", state="normal")
    return 0

def DisableBtnNet():
    btn_net.configure(text="Corrigindo...", state="disabled")
    return 0

def EnableBtnNet():
    btn_net.configure(text="Corrigir erros de Internet", state="normal")
    return 0

#Interface
def InterfaceRoot():
    
    #frame
    frame.pack(pady=10, padx=10, fill="both", expand=True)
    
    #cpu status
    cpu.pack(pady=10, padx=10, fill= "both", expand=True)
    textocpu = ctk.CTkLabel(master=cpu, text="CPU STATUS", fg_color="transparent", font=("Montserrat", 30))
    textocpu.pack()
    
    def atualizar_cpu():
        uso = psutil.cpu_percent()
        cpuinf.configure(text=f"Informações \n CPU: {uso}% \n Ram Total: {ram.total / (1024**3):.2f} GB \n Uso de Ram: {ram.used / (1024**3):.2f} GB")
        root.after(1000, atualizar_cpu)  # roda de novo em 1s
        
    cpuinf = ctk.CTkLabel(master=cpu, text=f"Informações \n Uso da Cpu: {uso}%", fg_color="transparent")
    cpuinf.pack()
    atualizar_cpu()
    
    #Progressão
    progress.pack()
    progress.set(0)
    
    #Butoes
    btn_geral.pack(pady=25, padx=20, fill="both", expand=True)
    
    btn_net.pack(pady=25, padx=20, fill="both", expand=True)
    
    btn_cache.pack(pady=25, padx=20, fill="both", expand=True)
    
    return 0
InterfaceRoot()
root.mainloop()#Mantem o codigo rodando
