import tkinter as tk
from tkinter import messagebox

# Funzioni di gestione (placeholder per l'aggiunta di connessioni)
def add_connection_gui():
    name = name_entry.get()
    ip = ip_entry.get()
    if name and ip:
        listbox.insert(tk.END, f"{name} - {ip}")
        name_entry.delete(0, tk.END)
        ip_entry.delete(0, tk.END)
    else:
        messagebox.showwarning("Attenzione", "Inserisci un nome e un IP validi.")

def remove_selected_connection():
    selected = listbox.curselection()
    if selected:
        listbox.delete(selected)

def create_gui():
    root = tk.Tk()
    root.title("Gestore Connessioni")
    root.geometry("790x550")  # Imposta dimensioni della finestra

    # Elementi grafici
    tk.Label(root, text="Nome").grid(row=0, column=0, padx=15, pady=(10, 0), sticky="w")
    global name_entry
    name_entry = tk.Entry(root, width=50)
    name_entry.grid(row=1, column=0, padx=20, pady=5)

    tk.Label(root, text="Indirizzo IP").grid(row=0, column=1, padx=15, pady=(10, 0), sticky="w")
    global ip_entry
    ip_entry = tk.Entry(root, width=50)
    ip_entry.grid(row=1, column=1, padx=15, pady=5)

    add_button = tk.Button(root, text="Aggiungi ➕", command=add_connection_gui)
    add_button.grid(row=1, column=2, padx=10, pady=5, sticky="e")

    remove_button = tk.Button(root, text="Rimuovi Connessione selezionata", command=remove_selected_connection)
    remove_button.grid(row=2, column=0, columnspan=3, pady=10)

    global listbox
    listbox = tk.Listbox(root, height=20, width=120)
    listbox.grid(row=3, column=0, columnspan=3, padx=10, pady=10)

    status_label = tk.Label(root, text="Prossimo ping in xx secondi")
    status_label.grid(row=4, column=0, columnspan=3, pady=5)

    stop_button = tk.Button(root, text="Ferma monitoraggio")
    stop_button.grid(row=5, column=0, columnspan=3, pady=10)

    root.mainloop()

create_gui()
