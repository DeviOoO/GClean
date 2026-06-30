import tkinter as tk
import customtkinter as ctk
from utils.Cleaner import *
from core.Thread import *
import psutil
import sys

# Aparência
ctk.set_appearance_mode("system")
ctk.set_default_color_theme("dark-blue")

# Paleta interna
_COR_FUNDO    = "#121316"
_COR_PAINEL   = "#66C0F4"
_COR_BOTAO    = "#2A475E"
_COR_SUCESSO  = "#1b4332"
_COR_AVISO    = "#7b4a00"
_FONTE_TITULO = ("Montserrat", 30)
_FONTE_BOTAO  = ("Bebas Neue", 20)
_FONTE_INFO   = ("Consolas", 11)


class App:
    def __init__(self):
        # ------------------------------------------------------------------ #
        # Janela raiz
        # ------------------------------------------------------------------ #
        self.root = ctk.CTk()
        self.root.title("GCleaner")
        largura_tela = self.root.winfo_screenwidth()
        altura_tela = self.root.winfo_screenheight()
        largura = min(650, int(largura_tela * 0.45))
        altura = min(1120, int(altura_tela * 0.90))
        x=(largura_tela-largura)//2
        y=(altura_tela-altura)//2
        self.root.geometry(f"{largura}x{altura}+{x}+{y}")
        self.root.resizable(True, True)

        # Frame principal
        self.frame = ctk.CTkScrollableFrame(master=self.root, corner_radius=15, fg_color=_COR_FUNDO)
        self.frame.pack(pady=10, padx=10, fill="both", expand=True)

        # ------------------------------------------------------------------ #
        # Painel de status (CPU / RAM)
        # ------------------------------------------------------------------ #
        self.cpu_frame = ctk.CTkFrame(master=self.frame, corner_radius=20, fg_color=_COR_PAINEL)
        self.cpu_frame.pack(pady=20, padx=20, fill="both", expand=True)

        ctk.CTkLabel(master=self.cpu_frame, text="CPU STATUS",
                     fg_color="transparent", font=_FONTE_TITULO).pack()

        self.cpuinf = ctk.CTkLabel(master=self.cpu_frame, text="", fg_color="transparent")
        self.cpuinf.pack()

        # Label de resultado (log de etapas)
        self.resultado_label = ctk.CTkLabel(master=self.cpu_frame, text="",
                                            fg_color="transparent", font=_FONTE_INFO,
                                            justify="left")
        self.resultado_label.pack(pady=(4, 2))

        # ------------------------------------------------------------------ #
        # Painel Antes / Depois
        # ------------------------------------------------------------------ #
        self.frame_delta = ctk.CTkFrame(master=self.frame, corner_radius=10, fg_color="#1a1d21")
        self.frame_delta.pack(pady=(0, 6), padx=10, fill="x")

        self.label_delta = ctk.CTkLabel(master=self.frame_delta,
                                         text="Antes / Depois: execute uma operação para ver o resultado",
                                         fg_color="transparent", font=_FONTE_INFO,
                                         text_color="#8fa3b1", justify="left")
        self.label_delta.pack(padx=10, pady=6, anchor="w")

        # ------------------------------------------------------------------ #
        # Barra de progresso
        # ------------------------------------------------------------------ #
        self.progress = ctk.CTkProgressBar(master=self.frame, orientation="horizontal",
                                            corner_radius=5, mode="determinate") 
        self.progress.pack(pady=(0, 8), padx=20, fill="x")
        self.progress.set(0)

        # ------------------------------------------------------------------ #
        # Toggle: Modo Simulação (dry run)
        # ------------------------------------------------------------------ #
        sim_row = ctk.CTkFrame(master=self.frame, fg_color="transparent")
        sim_row.pack(pady=(0, 6), padx=10, fill="x")

        ctk.CTkLabel(master=sim_row, text="Modo Simulação  ",
                     font=("Montserrat", 13), text_color="#8fa3b1").pack(side="left")
        self.switch_simulacao = ctk.CTkSwitch(master=sim_row, text="",
                                               onvalue=True, offvalue=False)
        self.switch_simulacao.pack(side="left")
        ctk.CTkLabel(master=sim_row,
                     text="  (descreve as ações sem executar — use para testar)",
                     font=("Montserrat", 11), text_color="#555e65").pack(side="left")

        # ------------------------------------------------------------------ #
        # Botões principais
        # ------------------------------------------------------------------ #
        def _btn(texto, comando):
            return ctk.CTkButton(master=self.frame, corner_radius=5,
                                  fg_color=_COR_BOTAO, text=texto,
                                  font=_FONTE_BOTAO, command=comando)

        self.btn_geral     = _btn("Limpeza Geral",              self.geral_exec)
        self.btn_net       = _btn("Corrigir Erros de Internet",  self.corrigir_net_exec)
        self.btn_cache     = _btn("Limpar Cache e Temporários",  self.limpeza_cache_exec)
        self.btn_otimizar  = _btn("Otimizar Sistema",            self.otimizar_exec)
        self.btn_restaurar = _btn("↩ Restaurar Plano de Energia", self.restaurar_exec)
        self.btn_startup   = _btn("⚙  Gerenciar Inicialização",  self.abrir_startup_manager)
        self.btn_agendar   = _btn("🕐  Agendar Limpeza Automática", self.abrir_scheduler_dialog)

        for btn in (self.btn_geral, self.btn_net, self.btn_cache,
                    self.btn_otimizar, self.btn_restaurar,
                    self.btn_startup, self.btn_agendar):
            btn.pack(pady=8, padx=20, fill="both")

        # ------------------------------------------------------------------ #
        # Inicializa monitor de CPU
        # ------------------------------------------------------------------ #
        self.atualizar_cpu()
        self.root.protocol("WM_DELETE_WINDOW", self.fechar_janela)

    # ====================================================================== #
    # Monitor de CPU / RAM em tempo real
    # ====================================================================== #
    def atualizar_cpu(self):
        uso = psutil.cpu_percent()
        ram = psutil.virtual_memory()
        self.cpuinf.configure(
            text=(f"CPU: {uso}%   |   "
                  f"RAM: {ram.used / (1024**3):.2f} GB / {ram.total / (1024**3):.2f} GB")
        )
        self.root.after(1000, self.atualizar_cpu)

    # ====================================================================== #
    # Barra de progresso (thread-safe)
    # ====================================================================== #
    def progress_att(self, valor):
        self.root.after(0, self.progress.set, valor)

    # ====================================================================== #
    # Exibição de resultados
    # ====================================================================== #
    def atualizar_resultado(self, apagados, ignorados, total):
        simulacao = self.switch_simulacao.get()
        if simulacao:
            texto = f"[SIMULAÇÃO] Encontrados {total} arquivos temporários para limpar"
        else:
            texto = f"Total: {total} | Apagados: {apagados} | Ignorados: {ignorados}"
        self.resultado_label.configure(text=texto)

    def atualizar_resumo_etapas(self, resultados):
        linhas = []
        for etapa, sucesso, detalhe in resultados:
            marcador = "✅" if sucesso else "⚠️"
            linhas.append(f"{marcador} {etapa}: {detalhe}")
        self.resultado_label.configure(text="\n".join(linhas))

    def atualizar_delta(self, antes, depois):
        """Mostra a diferença de disco livre e RAM entre o snapshot antes e depois."""
        if not antes or not depois:
            return
        delta_disco = depois["disco_livre_gb"] - antes["disco_livre_gb"]
        delta_ram   = antes["ram_usada_gb"]    - depois["ram_usada_gb"]

        partes = []
        if abs(delta_disco) > 0.001:
            sinal = "+" if delta_disco > 0 else ""
            partes.append(f"Disco livre: {sinal}{delta_disco:.2f} GB")
        else:
            partes.append("Disco livre: sem alteração mensurável")

        if abs(delta_ram) > 0.01:
            sinal = "+" if delta_ram > 0 else ""
            partes.append(f"RAM liberada: {sinal}{delta_ram:.2f} GB")
        else:
            partes.append("RAM: sem alteração mensurável")

        self.label_delta.configure(
            text="Antes → Depois   |   " + "   |   ".join(partes),
            text_color="#a8d8a8"
        )

    # ====================================================================== #
    # Lógica das operações (rodam em thread de background)
    # ====================================================================== #
    def limpeza_cache(self):
        sim = self.switch_simulacao.get()
        antes = capturar_snapshot()
        apagados, ignorados, total = cachetempclean(self.progress_att, simulacao=sim)
        depois = capturar_snapshot()
        self.root.after(0, self.atualizar_resultado, apagados, ignorados, total)
        self.root.after(0, self.atualizar_delta, antes, depois)
        self.root.after(0, self.enable_btn_cache)

    def corrigir_net(self):
        sim = self.switch_simulacao.get()
        antes = capturar_snapshot()
        resultados = netclean(self.progress_att, simulacao=sim)
        depois = capturar_snapshot()
        self.root.after(0, self.atualizar_resumo_etapas, resultados)
        self.root.after(0, self.atualizar_delta, antes, depois)
        self.root.after(0, self.enable_btn_net)

    def otimizar(self):
        sim = self.switch_simulacao.get()
        antes = capturar_snapshot()
        resultados = sysoptimize(self.progress_att, simulacao=sim)
        depois = capturar_snapshot()
        self.root.after(0, self.atualizar_resumo_etapas, resultados)
        self.root.after(0, self.atualizar_delta, antes, depois)
        self.root.after(0, self.enable_btn_otimizar)

    def restaurar(self):
        sucesso, detalhe = restaurar_plano_energia()
        marcador = "✅" if sucesso else "⚠️"
        self.root.after(0, self.resultado_label.configure,
                        {"text": f"{marcador} Restauração do plano: {detalhe}"})
        self.root.after(0, self.enable_btn_restaurar)

    def rotina_geral(self):
        sim = self.switch_simulacao.get()
        antes = capturar_snapshot()

        apagados, ignorados, total = cachetempclean(
            lambda v: self.progress_att(v * 0.25), simulacao=sim)
        self.root.after(0, self.atualizar_resultado, apagados, ignorados, total)

        resultados_net = netclean(
            lambda v: self.progress_att(0.25 + v * 0.35), simulacao=sim)

        resultados_sys = sysoptimize(
            lambda v: self.progress_att(0.60 + v * 0.40), simulacao=sim)

        depois = capturar_snapshot()

        self.root.after(0, self.atualizar_resumo_etapas, resultados_net + resultados_sys)
        self.root.after(0, self.atualizar_delta, antes, depois)
        self.root.after(0, self.enable_all_buttons)

    # ====================================================================== #
    # Disparo (tratamento de clique + threads)
    # ====================================================================== #
    def limpeza_cache_exec(self):
        self.disable_btn_cache()
        SegundoPlano(self.limpeza_cache)

    def otimizar_exec(self):
        self.disable_btn_otimizar()
        SegundoPlano(self.otimizar)

    def corrigir_net_exec(self):
        self.disable_btn_net()
        SegundoPlano(self.corrigir_net)

    def restaurar_exec(self):
        self.btn_restaurar.configure(text="Restaurando...", state="disabled")
        SegundoPlano(self.restaurar)

    def geral_exec(self):
        self.btn_geral.configure(text="Executando...", state="disabled")
        self.disable_btn_cache()
        self.disable_btn_net()
        self.disable_btn_otimizar()
        SegundoPlano(self.rotina_geral)

    # ====================================================================== #
    # Estado dos botões
    # ====================================================================== #
    def disable_btn_cache(self):
        self.btn_cache.configure(text="Limpando...", state="disabled")

    def disable_btn_otimizar(self):
        self.btn_otimizar.configure(text="Otimizando...", state="disabled")

    def disable_btn_net(self):
        self.btn_net.configure(text="Corrigindo...", state="disabled")

    def enable_btn_otimizar(self):
        self.btn_otimizar.configure(text="Otimizar Sistema", state="normal")

    def enable_btn_cache(self):
        self.btn_cache.configure(text="Limpar Cache e Temporários", state="normal")

    def enable_btn_net(self):
        self.btn_net.configure(text="Corrigir Erros de Internet", state="normal")

    def enable_btn_restaurar(self):
        self.btn_restaurar.configure(text="↩ Restaurar Plano de Energia", state="normal")

    def enable_all_buttons(self):
        self.btn_geral.configure(text="Limpeza Geral", state="normal")
        self.enable_btn_cache()
        self.enable_btn_net()
        self.enable_btn_otimizar()
        self.progress_att(0)

    # ====================================================================== #
    # Janela: Gerenciar Inicialização
    # ====================================================================== #
    def abrir_startup_manager(self):
        """Abre uma janela separada listando os itens de inicialização do sistema."""
        janela = ctk.CTkToplevel(self.root)
        janela.title("Gerenciar Inicialização")
        janela.geometry("720x560")
        janela.grab_set()

        ctk.CTkLabel(janela, text="Programas que iniciam com o Windows",
                     font=("Montserrat", 16)).pack(pady=(12, 4))
        ctk.CTkLabel(janela, text="Desabilitar itens desnecessários acelera o boot do sistema",
                     font=("Montserrat", 11), text_color="#8fa3b1").pack(pady=(0, 8))

        status_label = ctk.CTkLabel(janela, text="Carregando…",
                                    font=_FONTE_INFO, text_color="#8fa3b1")
        status_label.pack()

        scroll = ctk.CTkScrollableFrame(janela, fg_color="#1a1d21")
        scroll.pack(fill="both", expand=True, padx=10, pady=6)

        def carregar():
            itens = listar_itens_inicializacao()
            janela.after(0, status_label.configure,
                         {"text": f"{len(itens)} item(s) encontrado(s)"})

            for item in itens:
                row = ctk.CTkFrame(scroll, fg_color="#252830", corner_radius=6)
                row.pack(fill="x", pady=3, padx=4)

                info = ctk.CTkFrame(row, fg_color="transparent")
                info.pack(side="left", fill="both", expand=True, padx=8, pady=6)

                ctk.CTkLabel(info, text=item["nome"],
                             font=("Montserrat", 12, "bold"),
                             anchor="w").pack(anchor="w")

                caminho_curto = item["caminho"][:80] + "…" if len(item["caminho"]) > 80 else item["caminho"]
                ctk.CTkLabel(info, text=f"{item['fonte']}  |  {caminho_curto}",
                             font=_FONTE_INFO, text_color="#8fa3b1",
                             anchor="w").pack(anchor="w")

                estado_var = tk.BooleanVar(value=item["habilitado"])
                lbl_estado = ctk.CTkLabel(row,
                                          text="✅ Ativo" if item["habilitado"] else "⛔ Inativo",
                                          font=_FONTE_INFO,
                                          text_color="#a8d8a8" if item["habilitado"] else "#e07070",
                                          width=70)
                lbl_estado.pack(side="right", padx=(0, 8))

                def fazer_toggle(i=item, lbl=lbl_estado, var=estado_var):
                    novo_estado = not var.get()
                    sucesso, msg = toggle_item_inicializacao(i, novo_estado)
                    if sucesso:
                        var.set(novo_estado)
                        lbl.configure(
                            text="✅ Ativo" if novo_estado else "⛔ Inativo",
                            text_color="#a8d8a8" if novo_estado else "#e07070"
                        )
                    else:
                        lbl.configure(text=f"⚠ Erro", text_color="#e07070")

                ctk.CTkButton(row, text="Alternar", width=80,
                               fg_color=_COR_BOTAO, font=_FONTE_INFO,
                               command=fazer_toggle).pack(side="right", padx=4, pady=6)

        SegundoPlano(carregar)

    # ====================================================================== #
    # Janela: Agendamento
    # ====================================================================== #
    def abrir_scheduler_dialog(self):
        """Abre um dialog para configurar ou cancelar o agendamento semanal."""
        janela = ctk.CTkToplevel(self.root)
        janela.title("Agendar Limpeza Automática")
        janela.geometry("440x360")
        janela.grab_set()

        ctk.CTkLabel(janela, text="Limpeza Semanal Automática",
                     font=("Montserrat", 16)).pack(pady=(14, 4))

        # Status atual
        agendado = verificar_agendamento()
        texto_status = "✅ Agendamento ativo" if agendado else "⛔ Sem agendamento ativo"
        cor_status   = "#a8d8a8" if agendado else "#e07070"
        status_label = ctk.CTkLabel(janela, text=texto_status,
                                     font=_FONTE_INFO, text_color=cor_status)
        status_label.pack(pady=(0, 12))

        # Seleção de dia
        ctk.CTkLabel(janela, text="Dia da semana:", font=_FONTE_INFO).pack()
        dias = ["SEG", "TER", "QUA", "QUI", "SEX", "SAB", "DOM"]
        combo_dia = ctk.CTkComboBox(janela, values=dias, width=120)
        combo_dia.set("DOM")
        combo_dia.pack(pady=4)

        # Seleção de horário
        ctk.CTkLabel(janela, text="Horário (HH:MM):", font=_FONTE_INFO).pack(pady=(8, 0))
        entry_hora = ctk.CTkEntry(janela, placeholder_text="09:00", width=120)
        entry_hora.pack(pady=4)

        feedback = ctk.CTkLabel(janela, text="", font=_FONTE_INFO)
        feedback.pack(pady=6)

        def agendar():
            hora = entry_hora.get().strip() or "09:00"
            sucesso, msg = agendar_limpeza_semanal(combo_dia.get(), hora)
            cor = "#a8d8a8" if sucesso else "#e07070"
            feedback.configure(text=msg, text_color=cor)
            if sucesso:
                status_label.configure(text="✅ Agendamento ativo", text_color="#a8d8a8")

        def cancelar():
            sucesso, msg = cancelar_agendamento()
            cor = "#a8d8a8" if sucesso else "#e07070"
            feedback.configure(text=msg, text_color=cor)
            if sucesso:
                status_label.configure(text="⛔ Sem agendamento ativo", text_color="#e07070")

        btn_row = ctk.CTkFrame(janela, fg_color="transparent")
        btn_row.pack(pady=10)

        ctk.CTkButton(btn_row, text="Agendar", fg_color="#1b4332",
                       font=_FONTE_BOTAO, command=agendar).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="Cancelar Agendamento", fg_color="#7b1a1a",
                       font=_FONTE_BOTAO, command=cancelar).pack(side="left", padx=8)

    # ====================================================================== #
    # Loop principal
    # ====================================================================== #
    def run(self):
        self.root.mainloop()

    def fechar_janela(self):
        self.root.destroy()
        sys.exit(0)