import tkinter as tk
import customtkinter as ctk
from utils.cleaner import *
from core.Thread import *
import psutil
import sys

# Set de aparencia 
ctk.set_appearance_mode("system")
ctk.set_default_color_theme("dark-blue")


class App:
    def __init__(self):
        # Set de variaveis
        # Variaveis Base
        self.root = ctk.CTk()
        self.frame = ctk.CTkFrame(master=self.root, corner_radius=15, fg_color="#121316")
        self.cpu = ctk.CTkFrame(master=self.frame, corner_radius=20, fg_color="#66C0F4")
        self.progress = ctk.CTkProgressBar(master=self.frame, orientation="horizontal", corner_radius=5, mode="determinate", width=500)
        self.resultado_label = ctk.CTkLabel(master=self.cpu, text="")
        self.root.title("GCleaner") # Corrigido o erro de digitação
        self.root.geometry("600x900")
        
        self.uso = psutil.cpu_percent()
        self.ram = psutil.virtual_memory()
        
        self.textocpu = ctk.CTkLabel(master=self.cpu, text="CPU STATUS", fg_color="transparent", font=("Montserrat", 30))
        self.cpuinf = ctk.CTkLabel(master=self.cpu, text=f"Informações \n Uso da Cpu: {self.uso}%", fg_color="transparent")
        
        # Criação de Botões
        self.btn_cache = ctk.CTkButton(master=self.frame, corner_radius=5, fg_color="#2A475E", text="Limpar apenas os Caches", font=("Bebas Neue", 20), command=self.limpeza_cache_exec)
        self.btn_geral = ctk.CTkButton(master=self.frame, corner_radius=5, fg_color="#2A475E", text="Limpeza geral", font=("Bebas Neue", 20), command=self.geral_exec)
        self.btn_net = ctk.CTkButton(master=self.frame, corner_radius=5, fg_color="#2A475E", text="Corrigir erros de Internet", font=("Bebas Neue", 20), command=self.corrigir_net_exec)
        self.btn_otimizar = ctk.CTkButton(master=self.frame, corner_radius=5, fg_color="#2A475E", text="Otimizar Sistema", font=("Bebas Neue", 20), command=self.otimizar_exec)

        # Interface
        self.frame.pack(pady=10, padx=10, fill="both", expand=True)
        self.cpu.pack(pady=10, padx=10, fill="both", expand=True)
        self.textocpu.pack()
        self.cpuinf.pack()
        self.atualizar_cpu()
        self.resultado_label.pack()
        
        # Progressão
        self.progress.pack()
        self.progress.set(0)
        
        # Botões
        self.btn_geral.pack(pady=25, padx=20, fill="both", expand=True)
        self.btn_net.pack(pady=25, padx=20, fill="both", expand=True)
        self.btn_cache.pack(pady=25, padx=20, fill="both", expand=True)
        self.btn_otimizar.pack(pady=25, padx=20, fill="both", expand=True)
        self.root.protocol("WM_DELETE_WINDOW", self.fechar_janela)
        
    # Criação de Métodos
    def otimizar(self):
        """Faz a otimização do sistema chamando a função do cleaner."""
        sysoptimize(self.progress_att)
        self.root.after(0, self.enable_btn_otimizar)

    def limpeza_cache(self):
        """Faz limpeza de arquivos temporários."""
        apagados, ignorados, total = cachetempclean(self.progress_att)
        self.root.after(0, self.atualizar_resultado, apagados, ignorados, total)
        self.root.after(0, self.enable_btn_cache)
            
    def progress_att(self, valor):
        """Atualiza a barra de progresso de forma segura na Main Thread."""
        self.root.after(0, self.progress.set, valor)

    def atualizar_resultado(self, apagados, ignorados, total):
        """Adiciona no GPU status as informações da limpeza."""
        self.resultado_label.configure(
            text=f"Total de Arquivos: {total} | Apagados: {apagados} | Ignorados: {ignorados}"
        )

    def corrigir_net(self):
        """Faz a correção da Internet."""
        netclean(self.progress_att)
        self.root.after(0, self.enable_btn_net)

    # Métodos de Disparo (Tratamento de cliques e Threads)
    def limpeza_cache_exec(self):
        self.disable_btn_cache()
        SegundoPlano(self.limpeza_cache)

    def otimizar_exec(self):
        self.disable_btn_otimizar()
        SegundoPlano(self.otimizar)

    def corrigir_net_exec(self):
        self.disable_btn_net()
        SegundoPlano(self.corrigir_net)

    def geral_exec(self):
        """Desabilita todos os botões e inicia a rotina geral sequencial."""
        self.btn_geral.configure(text="Executando Geral...", state="disabled")
        self.disable_btn_cache()
        self.disable_btn_net()
        self.disable_btn_otimizar()
        SegundoPlano(self.rotina_geral)

    def rotina_geral(self):
        """Executa todas as manutenções sequencialmente dividindo a barra de progresso."""
        # 1. Limpeza de Cache (Ocupa de 0% a 33% da barra)
        apagados, ignorados, total = cachetempclean(lambda v: self.progress_att(v * 0.33))
        self.root.after(0, self.atualizar_resultado, apagados, ignorados, total)
        
        # 2. Correção de Rede (Ocupa de 33% a 66% da barra)
        netclean(lambda v: self.progress_att(0.33 + (v * 0.33)))
        
        # 3. Otimização do Sistema (Ocupa de 66% a 100% da barra)
        sysoptimize(lambda v: self.progress_att(0.66 + (v * 0.34)))
        
        # Reativa todos os botões ao finalizar
        self.root.after(0, self.enable_all_buttons)

    # Métodos de Gerenciamento de Estado dos Botões
    def disable_btn_cache(self):
        self.btn_cache.configure(text="Limpando...", state="disabled")

    def disable_btn_otimizar(self):
        self.btn_otimizar.configure(text="Otimizando...", state="disabled")

    def disable_btn_net(self):
        self.btn_net.configure(text="Corrigindo...", state="disabled")

    def enable_btn_otimizar(self):
        self.btn_otimizar.configure(text="Otimizar Sistema", state="normal")

    def enable_btn_cache(self):
        self.btn_cache.configure(text="Limpar apenas os Caches", state="normal")

    def enable_btn_net(self):
        self.btn_net.configure(text="Corrigir erros de Internet", state="normal")

    def enable_all_buttons(self):
        """Ativa todos os botões após a limpeza geral."""
        self.btn_geral.configure(text="Limpeza geral", state="normal")
        self.enable_btn_cache()
        self.enable_btn_net()
        self.enable_btn_otimizar()
        self.progress_att(0) # Reseta a barra para o início

    def atualizar_cpu(self):
        """Atualiza o uso da cpu e da RAM em tempo real (1s)."""
        self.uso = psutil.cpu_percent()
        self.ram = psutil.virtual_memory() # CORRIGIDO: Captura os dados de RAM atualizados
        
        self.cpuinf.configure(
            text=f"Informações \n CPU: {self.uso}% \n Ram Total: {self.ram.total / (1024**3):.2f} GB \n Uso de Ram: {self.ram.used / (1024**3):.2f} GB"
        )
        self.root.after(1000, self.atualizar_cpu)

    def run(self):
        self.root.mainloop()

    def fechar_janela(self):
        self.root.destroy()
        sys.exit(0)