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
from datetime import datetime

# Configurazione
CONNECTIONS_FILE = "connections.json"
monitoring = False
update_interval = 30#15 * 60  # 15 minuti in secondi
completed_pings = 0  # Contatore globale per tenere traccia dei ping completati
lock = threading.Lock()  # Blocco per evitare condizioni di race quando si modifica il contatore
down_times = {}

def load_connections():
    if os.path.exists(CONNECTIONS_FILE):
        with open(CONNECTIONS_FILE, "r") as file:
            return json.load(file)
    return []

def save_connections(connections):
    with open(CONNECTIONS_FILE, "w") as file:
        json.dump(connections, file, indent=4)

connections = load_connections()
last_status = {conn["ip"]: None for conn in connections}

def add_connection(name, ip):
    connections.append({"name": name, "ip": ip})
    save_connections(connections)

def remove_connection(index):
    del connections[index]
    save_connections(connections)

def send_email_alert(name, ip, status, text=""):
    # Configura l'invio di email qui
    print(f"ALERT: {name} ({ip}) è ora {status}")

    sender_email = "postmaster@multipedia.it"  # Inserisci la tua email
    sender_password = "pm-MP@22"  # Inserisci la tua password (assicurati di tenerla al sicuro)
    recipient_email = "assistenza@multipedia.it"  # Inserisci l'email del destinatario
    smtp_server = "out.postassl.it"  # Server SMTP del tuo provider (es. smtp.gmail.com per Gmail)
    sender_name = "Multipedia Ping"  # Nome che desideri mostrare come mittente

    # Creazione del messaggio
    subject = f"Connessione {status}: {name} ({ip})"
    body = f"L'indirizzo IP {ip} per la connessione {name} è ora {status}.\n\n{text}"
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

def monitor_ips(status_label, update_label):
    global monitoring, completed_pings
    while monitoring:
        completed_pings = 0  # Resetta il contatore all'inizio di ogni ciclo di monitoraggio
        total_connections = len(connections)  # Numero totale di connessioni

        for conn in connections:
            Thread(target=ping_connection, args=(conn, last_status, total_connections, update_label)).start()

        for i in range(update_interval, 0, -1):
            if not monitoring:
                status_label.config(text="Monitoraggio non attivo")
                break
            status_label.config(text=f"Prossimo ping in {i} secondi")
            status_label.update()
            time.sleep(1)

def ping_connection(conn, last_status, total_connections, update_label, retries=10):
    global completed_pings
    ip = conn["ip"]
    name = conn["name"]

    # Salta il ping se la connessione è disabilitata
    if not conn.get("enabled", True):
        last_status[conn["ip"]] = "UNKNOWN"
        with lock:
            completed_pings += 1
            if completed_pings == total_connections:
                update_label.config(text=f"Ultimo aggiornamento: {datetime.now().strftime('%H:%M:%S')}")
                update_label.update()
                update_listbox_with_status(last_status)  # Aggiorna la GUI
        return

    for _ in range(retries):
        response = ping(ip)
        if response is not None:
            break
        time.sleep(0.5)  # Pausa tra i tentativi per evitare sovraccarico

    # print(f"{ip} Ping response: {response}")
    current_status = "UP" if response else "DOWN"

    if last_status[ip] is not None and last_status[ip] != current_status:
        if current_status == "DOWN":
            # Memorizza l'orario di inizio del "DOWN"
            down_times[ip] = datetime.now()
            send_email_alert(name, ip, current_status, f"Connessione DOWN alle {down_times[ip].strftime("%H:%M:%S")}")
        elif current_status == "UP" and ip in down_times:
            # Calcola il tempo di "DOWN" e invia l'email con la durata
            down_duration = datetime.now() - down_times[ip]
            down_minutes = int(down_duration.total_seconds() / 60)
            down_seconds = int(down_duration.total_seconds() % 60)
            send_email_alert(name, ip, current_status, f"Tempo di DOWN: {down_minutes} minuti e {down_seconds} secondi")
            del down_times[ip]  # Rimuovi il record di "DOWN" dopo aver notificato

    last_status[ip] = current_status

    with lock:
        completed_pings += 1
        if completed_pings == total_connections:
            update_label.config(text=f"Ultimo aggiornamento: {datetime.now().strftime("%H:%M:%S")}")
            update_label.update()
            update_listbox_with_status(last_status)  # Aggiorna la GUI solo quando tutti i ping sono completati

def start_monitoring(status_label, update_label, start_button, stop_button):
    global monitoring
    if not monitoring:
        monitoring = True
        start_button.grid_remove()  # Nascondi il pulsante "Inizia"
        stop_button.grid()  # Mostra il pulsante "Ferma"
        Thread(target=monitor_ips, args=(status_label, update_label), daemon=True).start()

def stop_monitoring(start_button, stop_button):
    global monitoring
    monitoring = False
    stop_button.grid_remove()  # Nascondi il pulsante "Ferma"
    start_button.grid()  # Mostra il pulsante "Inizia"

def update_status_totals(last_status):
    total_connections = len(connections)
    paused_count = sum(1 for conn in connections if not conn.get("enabled", True))
    up_count = sum(1 for status in last_status.values() if status == "UP")
    down_count = sum(1 for status in last_status.values() if status == "DOWN")
    # down_count = total_connections - up_count

    global total_label, paused_label, up_label, down_label
    total_label.config(text=f"Connessioni totali: {total_connections}")
    paused_label.config(text=f"Connessioni in pausa: {paused_count}")
    up_label.config(text=f"Connessioni UP: {up_count}")
    down_label.config(text=f"Connessioni DOWN: {down_count}")

def update_listbox_with_status(last_status):
    # Rimuovi tutti i dati esistenti e aggiorna con gli stati correnti
    global listbox
    listbox.delete(0, tk.END)
    for conn in connections:
        ip = conn["ip"]
        name = conn["name"]
        enabled = conn["enabled"]
        current_status = last_status.get(ip, "UNKNOWN")
        if current_status == "UP":
            status_text = "✅"
        elif current_status == "DOWN":
            status_text = "❌"
        else:
            status_text = "❓"
        status_indicator = "🔝" if enabled else "🟢"
        listbox.insert(tk.END, f"{status_indicator} {status_text} {name} | {ip}")

    update_status_totals(last_status)

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
            update_status_totals({})
        else:
            messagebox.showwarning("Attenzione", "Inserisci un nome e un IP validi.")

    def remove_selected_connection():
        selected = listbox.curselection()
        if selected:
            index = selected[0]
            listbox.delete(index)
            remove_connection(index)
            update_status_totals({})

    def toggle_connection_status():
        selected = listbox.curselection()
        if selected:
            index = selected[0]
            connections[index]["enabled"] = not connections[index]["enabled"]
            selected_ip = connections[index]["ip"]
            last_status[selected_ip] = "UNKNOWN"
            update_listbox_with_status(last_status)
            save_connections(connections)

    root = tk.Tk()
    root.title("Gestore Connessioni")
    root.geometry("790x600")  # Imposta dimensioni della finestra

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
    remove_button.grid(row=2, column=0, pady=10)

    toggle_button = tk.Button(root, text="⏯️ Pausa/Riprendi", command=toggle_connection_status)
    toggle_button.grid(row=2, column=1, padx=10, pady=10)

    global listbox
    listbox = tk.Listbox(root, height=20, width=120)
    listbox.grid(row=3, column=0, columnspan=3, padx=10, pady=10)
    for conn in connections:
        listbox.insert(tk.END, f"{conn['name']} - {conn['ip']}")

    global total_label, paused_label, up_label, down_label
    total_label = tk.Label(root, text="Connessioni totali: 0")
    total_label.grid(row=4, column=0, padx=25, pady=(0, 5), sticky="w")

    paused_label = tk.Label(root, text="Connessioni in pausa: 0", fg="blue")
    paused_label.grid(row=4, column=1, pady=(0, 5), sticky="e")

    up_label = tk.Label(root, text="Connessioni UP: 0", fg="green")
    up_label.grid(row=5, column=0, padx=25, pady=(0, 5), sticky="w")

    down_label = tk.Label(root, text="Connessioni DOWN: 0", fg="red")
    down_label.grid(row=5, column=1, pady=(0, 5), sticky="e")
    
    status_label = tk.Label(root, text="Monitoraggio non attivo")
    status_label.grid(row=6, column=0, pady=5)
    
    update_label = tk.Label(root, text="Ultimo aggiornamento: MAI")
    update_label.grid(row=6, column=1, pady=5)

    start_button = tk.Button(root, text="Inizia Monitoraggio ▶️", command=lambda: start_monitoring(status_label, update_label, start_button, stop_button))
    start_button.grid(row=7, column=0, columnspan=3, pady=10)

    stop_button = tk.Button(root, text="Ferma Monitoraggio ⏸️", command=lambda: stop_monitoring(start_button, stop_button))
    stop_button.grid(row=7, column=0, columnspan=3, pady=10)

    start_button.grid()  # Inizialmente, il pulsante "Inizia" è visibile
    stop_button.grid_remove()  # Nascondi il pulsante "Ferma"

    # Avvia automaticamente il monitoraggio all'avvio del programma
    start_monitoring(status_label, update_label, start_button, stop_button)

    root.mainloop()

if __name__ == "__main__":
    create_gui()
