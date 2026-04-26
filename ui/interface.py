import tkinter as tk
import customtkinter as ctk


ctk.set_appearance_mode("system")
ctk.set_default_color_theme("dark-blue")
    
root = ctk.CTk()
root.title("GClenaer")
root.geometry("600x900")

def InterfaceRoot():
    
    frame = ctk.CTkFrame(master=root, corner_radius=(15), fg_color="#121316")
    frame.pack(pady=10, padx=10, fill="both", expand=True)
    
    #cpu status
    cpu = ctk.CTkFrame(master=frame, corner_radius= 20, fg_color= "#66C0F4")
    cpu.pack(pady=10, padx=10, fill= "both", expand=True)
    texto = ctk.CTkLabel(master=cpu, text="CPU status", fg_color="transparent")
    texto.pack()
    
    #Progressão
    
    
    #Butoes
    btn_geral = ctk.CTkButton(master=frame, corner_radius= 5, fg_color="#2A475E", text="Limpeza Geral", font=("Bebas Neue", 20))
    btn_geral.pack(pady=25, padx=20, fill="both", expand=True)
    
    btn_syst = ctk.CTkButton(master=frame, corner_radius= 5, fg_color="#2A475E", text="Limpar apenas o sistema", font=("Bebas Neue", 20))
    btn_syst.pack(pady=25, padx=20, fill="both", expand=True)
    
    btn_cache = ctk.CTkButton(master=frame, corner_radius= 5, fg_color="#2A475E", text="Limpar apenas os Caches", font=("Bebas Neue", 20))
    btn_cache.pack(pady=25, padx=20, fill="both", expand=True)
    
    return 0

InterfaceRoot()
root.mainloop() #Mantem o codigo rodando