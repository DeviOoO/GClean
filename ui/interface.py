import tkinter as tk
import customtkinter as ctk
from utils.cleaner import *
from core.Thread import *
import psutil
import sys

#Set de aparencia 
ctk.set_appearance_mode("system")
ctk.set_default_color_theme("dark-blue")


class App:
    def __init__(self):
        #Set de variaveis
            #Variaveis Base
        self.root = ctk.CTk()
        self.frame = ctk.CTkFrame(master=self.root, corner_radius=(15), fg_color="#121316")
        self.cpu = ctk.CTkFrame(master=self.frame, corner_radius= 20, fg_color= "#66C0F4")
        self.progress = ctk.CTkProgressBar(master=self.frame, orientation="horizontal", corner_radius= 5, mode="determinate", width=500)
        self.resultado_label = ctk.CTkLabel(master=self.cpu, text="")
        self.root.title("GClenaer")
        self.root.geometry("600x900")
        self.uso = psutil.cpu_percent()
        self.ram = psutil.virtual_memory()
        self.textocpu = ctk.CTkLabel(master=self.cpu, text="CPU STATUS", fg_color="transparent", font=("Montserrat", 30))
        self.cpuinf = ctk.CTkLabel(master=self.cpu, text=f"Informações \n Uso da Cpu: {self.uso}%", fg_color="transparent")
        
        #Criação de Butoes
        self.btn_cache = ctk.CTkButton(master=self.frame, corner_radius= 5, fg_color="#2A475E", text="Limpar apenas os Caches", font=("Bebas Neue", 20), command=self.limpeza_cache_exec)
        self.btn_geral = ctk.CTkButton(master=self.frame, corner_radius= 5, fg_color="#2A475E", text="Limpeza geral", font=("Bebas Neue", 20), command=self.geral)
        self.btn_net = ctk.CTkButton(master=self.frame, corner_radius= 5, fg_color="#2A475E", text="Corrigir erros de Internet", font=("Bebas Neue", 20), command=self.corrigir_net_exec)

        #Interface
        self.frame.pack(pady=10, padx=10, fill="both", expand=True)
        self.cpu.pack(pady=10, padx=10, fill= "both", expand=True)
        self.textocpu.pack()
        self.cpuinf.pack()
        self.atualizar_cpu()
        self.resultado_label.pack()
        
        #Progressão
        self.progress.pack()
        self.progress.set(0)
        
        #Butoes
        self.btn_geral.pack(pady=25, padx=20, fill="both", expand=True)
        self.btn_net.pack(pady=25, padx=20, fill="both", expand=True)
        self.btn_cache.pack(pady=25, padx=20, fill="both", expand=True)
        self.root.protocol("WM_DELETE_WINDOW", self.fechar_janela)
        
        
        #Criação de Metodos
    def limpeza_cache(self):
            """Faz limpeza de arquivos, fazendo a chamada da função e recebe os valores da limpeza, então atualiza o Root para mostrar
            """
            apagados, ignorados, total = cachetempclean(self.progress_att)
            
            self.root.after(0, self.atualizar_resultado, apagados, ignorados, total)
            self.root.after(0, self.enable_btn_cache)
            
    def progress_att(self, valor):
            """Atualiza a barra de progresso

            Args:
                valor (number): Porcentagem da barra
            """    
            self.root.after(0, self.progress.set, valor)

    def atualizar_resultado(self, apagados, ignorados, total):
            """Adiciona no GPU status a quantidade de arquivos e quantos foram apagadados ou ignorados

            Args:
                apagados (number): Quantidade de arquivos apagados
                ignorados (number): Quantidade de arquivos ignorados
                total (number): Quantidade de arquivos
            """    
            self.resultado_label.configure(
                text=f"Total de Arquivos: {total} | Apagados: {apagados} | Ignorados: {ignorados}"
            )

    def corrigir_net(self):
            """Faz a correção da Internet, fazendo a chamada da função
            """    
            netclean(self.progress_att)
            self.root.after(0, self.enable_btn_net)

    def limpeza_cache_exec(self):
            """Execução do botão, chamando as funções disable_btn_cache e fazendo execução em segundo plano de Limpeza Cache
            """    
            self.disable_btn_cache()
            SegundoPlano(self.limpeza_cache)

    def corrigir_net_exec(self):
            """Execução do botão, chamando as funções disable_btn_net e fazendo execução em segundo plano de corrigir_net
            """    
            self.disable_btn_net()
            SegundoPlano(self.corrigir_net)

    def geral(self):
            """Faz o uso de todas as outras funções
            """    
            self.limpeza_cache_exec()
            self.corrigir_net_exec()

    def disable_btn_cache(self):
            """Desabilita o botão de limpar cache e muda o texto
            """    
            self.btn_cache.configure(text="Limpando...", state="disabled")

    def enable_btn_cache(self):
            """Ativa o botão de limpar cache
            """    
            self.btn_cache.configure(text="Limpar apenas os Caches", state="normal")

    def disable_btn_net(self):
            """Desativa o botão de corrigir Internet e muda o texto
            """    
            self.btn_net.configure(text="Corrigindo...", state="disabled")

    def enable_btn_net(self):
            """Ativa o botão de Corrigir Internet
            """    
            self.btn_net.configure(text="Corrigir erros de Internet", state="normal")

    def atualizar_cpu(self):
            """Atualiza o uso da cpu em tempo real
            """        
            self.uso = psutil.cpu_percent()
            self.cpuinf.configure(text=f"Informações \n CPU: {self.uso}% \n Ram Total: {self.ram.total / (1024**3):.2f} GB \n Uso de Ram: {self.ram.used / (1024**3):.2f} GB")
            self.root.after(1000, self.atualizar_cpu)  # roda de novo em 1s

    def run(self):
        self.root.mainloop()