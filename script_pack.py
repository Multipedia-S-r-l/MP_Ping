import json
import os
import time
import smtplib
from ping3 import ping
import tkinter as tk
from tkinter import messagebox
from threading import Thread

# Configurazione
CONNECTIONS_FILE = "connections.json"
monitoring = False
update_interval = 5 * 60  # 5 minuti in secondi

def load_connections():
    if os.path.exists(CONNECTIONS_FILE):
        with open(CONNECTIONS_FILE, "r") as file:
            return json.load(file)
    return []

def save_connections(connections):
    with open(CONNECTIONS_FILE, "w") as file:
        json.dump(connections, file, indent=4)

connections = load_connections()

def add_connection(name, ip):
    connections.append({"name": name, "ip": ip})
    save_connections(connections)

def remove_connection(index):
    del connections[index]
    save_connections(connections)

def send_email_alert(name, ip, status):
    # Configura l'invio di email qui
    print(f"ALERT: {name} ({ip}) è ora {status}")

def monitor_ips(update_label):
    global monitoring
    last_status = {conn["ip"]: None for conn in connections}
    while monitoring:
        for i in range(update_interval, 0, -1):
            update_label.config(text=f"Prossimo ping in {i} secondi")
            update_label.update()
            time.sleep(1)

        for conn in connections:
            Thread(target=ping_connection, args=(conn, last_status)).start()

def ping_connection(conn, last_status):
    ip = conn["ip"]
    name = conn["name"]
    response = ping(ip)
    current_status = "UP" if response else "DOWN"
    if last_status[ip] is not None and last_status[ip] != current_status:
        send_email_alert(name, ip, current_status)
    last_status[ip] = current_status

def start_monitoring(update_label, start_button, stop_button):
    global monitoring
    if not monitoring:
        monitoring = True
        start_button.pack_forget()  # Nascondi il pulsante "Inizia"
        stop_button.pack()  # Mostra il pulsante "Ferma"
        Thread(target=monitor_ips, args=(update_label,), daemon=True).start()

def stop_monitoring(start_button, stop_button):
    global monitoring
    monitoring = False
    stop_button.pack_forget()  # Nascondi il pulsante "Ferma"
    start_button.pack()  # Mostra il pulsante "Inizia"

# Creazione dell'interfaccia GUI
def create_gui():
    def add_connection_gui():
        name = name_entry.get()
        ip = ip_entry.get()
        if name and ip:
            add_connection(name, ip)
            listbox.insert(tk.END, f"{name} - {ip}")
            name_entry.delete(0, tk.END)
            ip_entry.delete(0, tk.END)
        else:
            messagebox.showwarning("Attenzione", "Inserisci un nome e un IP validi.")

    def remove_selected_connection():
        selected = listbox.curselection()
        if selected:
            index = selected[0]
            listbox.delete(index)
            remove_connection(index)

    root = tk.Tk()
    root.title("Gestore Connessioni")
    
    # Imposta la dimensione della finestra (larghezza x altezza)
    root.geometry("800x600")  # Modifica la dimensione a piacere

    tk.Label(root, text="Nome:").pack(pady=(30, 0))  # Margine superiore e inferiore
    name_entry = tk.Entry(root)
    name_entry.pack()

    tk.Label(root, text="Indirizzo IP:").pack(pady=(10, 0))  # Margine superiore e inferiore
    ip_entry = tk.Entry(root)
    ip_entry.pack()

    tk.Button(root, text="Aggiungi Connessione", command=add_connection_gui).pack()
    tk.Button(root, text="Rimuovi Connessione Selezionata", command=remove_selected_connection).pack()

    # Aumenta la dimensione della Listbox
    listbox = tk.Listbox(root, height=20, width=100)  # Puoi regolare altezza e larghezza
    listbox.pack()
    for conn in connections:
        listbox.insert(tk.END, f"{conn['name']} - {conn['ip']}")

    status_label = tk.Label(root, text="Monitoraggio non attivo")
    status_label.pack()

    start_button = tk.Button(root, text="Inizia Monitoraggio", command=lambda: start_monitoring(status_label, start_button, stop_button))
    stop_button = tk.Button(root, text="Ferma Monitoraggio", command=lambda: stop_monitoring(start_button, stop_button))

    start_button.pack()  # Inizialmente, il pulsante "Inizia" è visibile
    stop_button.pack_forget()  # Nascondi il pulsante "Ferma"

    # Avvia automaticamente il monitoraggio all'avvio del programma
    start_monitoring(status_label, start_button, stop_button)

    root.mainloop()

if __name__ == "__main__":
    create_gui()
