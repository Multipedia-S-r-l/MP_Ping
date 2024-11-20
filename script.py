import json
import os
import threading
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from ping3 import ping
import tkinter as tk
from tkinter import messagebox
from threading import Thread

# Configurazione
CONNECTIONS_FILE = "connections.json"
monitoring = False
update_interval = 5 * 60  # 5 minuti in secondi
completed_pings = 0  # Contatore globale per tenere traccia dei ping completati
lock = threading.Lock()  # Blocco per evitare condizioni di race quando si modifica il contatore

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

    sender_email = "postmaster@multipedia.it"  # Inserisci la tua email
    sender_password = "pm-MP@22"  # Inserisci la tua password (assicurati di tenerla al sicuro)
    recipient_email = "assistenza@multipedia.it"  # Inserisci l'email del destinatario
    smtp_server = "out.postassl.it"  # Server SMTP del tuo provider (es. smtp.gmail.com per Gmail)
    sender_name = "Multipedia Ping"  # Nome che desideri mostrare come mittente

    # Creazione del messaggio
    subject = f"Connessione {status}: {name} ({ip})"
    body = f"L'indirizzo IP {ip} ({name}) è ora {status}."
    msg = MIMEMultipart()
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = recipient_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        # Creazione della connessione SMTP utilizzando SSL
        with smtplib.SMTP_SSL(smtp_server, 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        print(f"Email inviata con successo a {recipient_email}.")
    except Exception as e:
        print(f"Errore nell'invio dell'email: {e}")

def monitor_ips(update_label):
    global monitoring, completed_pings
    last_status = {conn["ip"]: None for conn in connections}
    while monitoring:
        completed_pings = 0  # Resetta il contatore all'inizio di ogni ciclo di monitoraggio
        total_connections = len(connections)  # Numero totale di connessioni

        for conn in connections:
            Thread(target=ping_connection, args=(conn, last_status, total_connections)).start()

        for i in range(update_interval, 0, -1):
            if not monitoring:
                update_label.config(text="Monitoraggio non attivo")
                break
            update_label.config(text=f"Prossimo ping in {i} secondi")
            update_label.update()
            time.sleep(1)

def ping_connection(conn, last_status, total_connections):
    global completed_pings
    ip = conn["ip"]
    name = conn["name"]
    response = ping(ip)
    current_status = "UP" if response else "DOWN"
    if last_status[ip] is not None and last_status[ip] != current_status:
        send_email_alert(name, ip, current_status)
    last_status[ip] = current_status

    with lock:
        completed_pings += 1
        if completed_pings == total_connections:
            update_listbox_with_status(last_status)  # Aggiorna la GUI solo quando tutti i ping sono completati

def start_monitoring(update_label, start_button, stop_button):
    global monitoring
    if not monitoring:
        monitoring = True
        start_button.grid_remove()  # Nascondi il pulsante "Inizia"
        stop_button.grid()  # Mostra il pulsante "Ferma"
        Thread(target=monitor_ips, args=(update_label,), daemon=True).start()

def stop_monitoring(start_button, stop_button):
    global monitoring
    monitoring = False
    stop_button.grid_remove()  # Nascondi il pulsante "Ferma"
    start_button.grid()  # Mostra il pulsante "Inizia"

def update_listbox_with_status(last_status):
    # Rimuovi tutti i dati esistenti e aggiorna con gli stati correnti
    global listbox
    listbox.delete(0, tk.END)
    for conn in connections:
        ip = conn["ip"]
        name = conn["name"]
        # Determina lo stato corrente (supponendo che tu mantenga uno stato in una variabile/dizionario)
        current_status = last_status.get(ip, "UNKNOWN")  # Puoi aggiornare questa logica con il tuo monitoraggio
        status_text = f"✅" if current_status == "UP" else "❌"
        
        # Aggiungi l'elemento alla listbox con il colore appropriato
        listbox.insert(tk.END, f"{status_text} {name} | {ip}")

# Creazione dell'interfaccia GUI
def create_gui():
    def add_connection_gui():
        name = name_entry.get()
        ip = ip_entry.get()
        if name and ip:
            add_connection(name, ip)
            listbox.insert(tk.END, f"❓ {name} | {ip}")
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
    root.geometry("790x550")  # Imposta dimensioni della finestra

    # Elementi grafici
    tk.Label(root, text="Nome").grid(row=0, column=0, padx=15, pady=(10, 0), sticky="w")
    name_entry = tk.Entry(root, width=50)
    name_entry.grid(row=1, column=0, padx=20, pady=5)

    tk.Label(root, text="Indirizzo IP").grid(row=0, column=1, padx=15, pady=(10, 0), sticky="w")
    ip_entry = tk.Entry(root, width=50)
    ip_entry.grid(row=1, column=1, padx=15, pady=5)

    add_button = tk.Button(root, text="Aggiungi ➕", command=add_connection_gui)
    add_button.grid(row=1, column=2, padx=10, pady=5, sticky="e")

    remove_button = tk.Button(root, text="🗑️ Rimuovi Connessione selezionata", command=remove_selected_connection)
    remove_button.grid(row=2, column=0, columnspan=3, pady=10)

    global listbox
    listbox = tk.Listbox(root, height=20, width=120)
    listbox.grid(row=3, column=0, columnspan=3, padx=10, pady=10)
    for conn in connections:
        listbox.insert(tk.END, f"{conn['name']} - {conn['ip']}")

    status_label = tk.Label(root, text="Monitoraggio non attivo")
    status_label.grid(row=4, column=0, columnspan=3, pady=5)

    start_button = tk.Button(root, text="Inizia Monitoraggio ▶️", command=lambda: start_monitoring(status_label, start_button, stop_button))
    start_button.grid(row=5, column=0, columnspan=3, pady=10)

    stop_button = tk.Button(root, text="Ferma Monitoraggio ⏸️", command=lambda: stop_monitoring(start_button, stop_button))
    stop_button.grid(row=5, column=0, columnspan=3, pady=10)

    start_button.grid()  # Inizialmente, il pulsante "Inizia" è visibile
    stop_button.grid_remove()  # Nascondi il pulsante "Ferma"

    # Avvia automaticamente il monitoraggio all'avvio del programma
    start_monitoring(status_label, start_button, stop_button)

    root.mainloop()

if __name__ == "__main__":
    create_gui()
