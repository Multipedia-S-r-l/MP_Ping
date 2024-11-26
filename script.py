import json
import os
import threading
import time
import smtplib
import portalocker
import ipaddress
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
update_interval = 15 * 60  # 15 minuti in secondi
completed_pings = 0  # Contatore globale per tenere traccia dei ping completati
lock = threading.Lock()  # Blocco per evitare condizioni di race quando si modifica il contatore
down_times = {}

def load_connections():
    try:
        if os.path.exists(CONNECTIONS_FILE):
            with open(CONNECTIONS_FILE, "r") as file:
                return json.load(file)
    except Exception as e:
        messagebox.showerror(f"Errore durante il caricamento delle connessioni: {e}")
        exit
    return []

def save_connections(connections):
    for attempt in range(5):  # Prova 5 volte
        try:
            with open(CONNECTIONS_FILE, "w") as file:
                # Blocca il file per impedirne l'accesso simultaneo
                portalocker.lock(file, portalocker.LOCK_EX)
                json.dump(connections, file, indent=4)
                # Rilascia il blocco
                portalocker.unlock(file)
            return
        except Exception as e:
            print(f"Errore al tentativo {attempt + 1}: {e}")
            time.sleep(0.5)  # Aspetta mezzo secondo prima di riprovare
    messagebox.showerror("Impossibile salvare le connessioni dopo 5 tentativi.")
    exit

connections = load_connections()
last_status = {conn["ip"]: None for conn in connections}

def add_connection(name, ip):
    connections.append({"name": name, "ip": ip, "enabled": True})
    connections.sort(key=sort_key)  # Ordina dopo l'aggiunta
    save_connections(connections)
    last_status[ip] = "UNKNOWN"
    update_listbox_with_status(last_status)

def remove_connection(index):
    selected_ip = connections[index]["ip"]
    del last_status[selected_ip]
    del connections[index]
    save_connections(connections)

def sort_key(connection):
    # Rimuove la parte fino al primo trattino incluso per determinare la chiave di ordinamento
    name = connection["name"]
    return name.split("-", 1)[-1].strip()  # Prende tutto dopo il primo trattino


def send_email_alert(name, ip, status, text=""):
    # Configura l'invio di email qui
    print(f"ALERT: {name} ({ip}) è ora {status}")

    sender_email = "postmaster@multipedia.it"  # Inserisci la tua email
    sender_password = "pm-MP@22"  # Inserisci la tua password (assicurati di tenerla al sicuro)
    recipient_email = "ticket@multipedia.it"  # Inserisci l'email del destinatario
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
        if response:
            # print(f"{ip} OK")
            break
        print(f"{ip} nuovo tentativo a breve...")
        time.sleep(0.5)  # Pausa tra i tentativi per evitare sovraccarico

    # print(f"{ip} Ping response: {response}")
    current_status = "UP" if response else "DOWN"

    if last_status[ip] is not None and last_status[ip] != current_status:
        if current_status == "DOWN":
            # Memorizza l'orario di inizio del "DOWN"
            down_times[ip] = datetime.now()
            print(f"{down_times[ip].strftime("%H:%M:%S")} \tIP: {ip} | Last: {last_status[ip]} | Current: {current_status}")
            send_email_alert(name, ip, current_status, f"Connessione DOWN alle {down_times[ip].strftime("%H:%M:%S")}")
        elif current_status == "UP" and ip in down_times:
            # Calcola il tempo di "DOWN" e invia l'email con la durata
            down_duration = datetime.now() - down_times[ip]
            down_minutes = int(down_duration.total_seconds() / 60)
            down_seconds = int(down_duration.total_seconds() % 60)
            send_email_alert(name, ip, current_status, f"Tempo di DOWN: {down_minutes} minuti e {down_seconds} secondi")
            del down_times[ip]  # Rimuovi il record di "DOWN" dopo aver notificato

    with lock:
        last_status[ip] = current_status
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

def is_valid_ip(ip):
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False
    
def is_ip_duplicate(ip, index_to_ignore=None):
    # index_to_ignore: L'indice da ignorare (utile per le modifiche).
    for index, conn in enumerate(connections):
        if conn["ip"] == ip and index != index_to_ignore:
            return True
    return False

# Creazione dell'interfaccia GUI
def create_gui():
    def add_connection_gui():
        name = name_entry.get()
        ip = ip_entry.get()
        if not name or not ip:
            messagebox.showwarning("Attenzione", "Inserisci un nome e un indirizzo IP!")
            return
        if not is_valid_ip(ip):
            messagebox.showwarning("Attenzione", "Inserisci un indirizzo IP valido!")
            return
        if is_ip_duplicate(ip):
            messagebox.showwarning("Attenzione", "L'indirizzo IP è già presente!")
            return
        add_connection(name, ip)
        listbox.insert(tk.END, f"🔝 ❓ {name} | {ip}")
        name_entry.delete(0, tk.END)
        ip_entry.delete(0, tk.END)
        update_status_totals({})

    def remove_selected_connection():
        selected = listbox.curselection()
        if selected:
            index = selected[0]
            listbox.delete(index)
            remove_connection(index)
            update_status_totals({})
        else:
            messagebox.showwarning("Attenzione", "Nessuna connessione selezionata!")

    def toggle_connection_status():
        selected = listbox.curselection()
        if selected:
            index = selected[0]
            connections[index]["enabled"] = not connections[index]["enabled"]
            selected_ip = connections[index]["ip"]
            last_status[selected_ip] = "UNKNOWN"
            update_listbox_with_status(last_status)
            save_connections(connections)
        else:
            messagebox.showwarning("Attenzione", "Nessuna connessione selezionata!")

    def change_selected_connection():
        selected = listbox.curselection()
        if selected:
            index = selected[0]
            conn = connections[index]

            # Crea una finestra modale per modificare i dati
            edit_window = tk.Toplevel(root)
            edit_window.title("Modifica Connessione")
            edit_window.geometry("420x160")
            edit_window.transient(root)  # Imposta la finestra come figlia della finestra principale
            edit_window.grab_set()  # Blocca l'interazione con la finestra principale

            # Campi di input
            tk.Label(edit_window, text="Nome").grid(row=0, column=0, padx=10, pady=(20,10))
            name_entry = tk.Entry(edit_window, width=50)
            name_entry.insert(0, conn["name"])  # Prepopola con il valore corrente
            name_entry.grid(row=0, column=1, padx=10, pady=(20,10))

            tk.Label(edit_window, text="Indirizzo IP").grid(row=1, column=0, padx=10, pady=10)
            ip_entry = tk.Entry(edit_window, width=50)
            ip_entry.insert(0, conn["ip"])  # Prepopola con il valore corrente
            ip_entry.grid(row=1, column=1, padx=10, pady=10)

            # Funzione per salvare i cambiamenti
            def confirm_edit():
                new_name = name_entry.get()
                new_ip = ip_entry.get()
                if not new_name or not new_ip:
                    messagebox.showwarning("Attenzione", "Inserisci un nome e un indirizzo IP!")
                    return
                if not is_valid_ip(new_ip):
                    messagebox.showwarning("Attenzione", "Inserisci un indirizzo IP valido!")
                    return
                if is_ip_duplicate(new_ip, index):
                    messagebox.showwarning("Attenzione", "L'indirizzo IP è già presente!")
                    return
                remove_connection(index)
                add_connection(new_name, new_ip)
                edit_window.destroy()  # Chiudi la finestra

            # Bottoni
            tk.Button(edit_window, text="Conferma", command=confirm_edit).grid(row=2, column=0, padx=10, pady=20)
            tk.Button(edit_window, text="Annulla", command=edit_window.destroy).grid(row=2, column=1, padx=10, pady=20)
        else:
            messagebox.showwarning("Attenzione", "Nessuna connessione selezionata!")

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
    remove_button.grid(row=2, column=0, padx=25, pady=10, sticky="w")

    toggle_button = tk.Button(root, text="⏯️ Pausa/Riprendi", command=toggle_connection_status)
    toggle_button.grid(row=2, column=1, padx=10, pady=10)

    toggle_button = tk.Button(root, text="✏️ Modifica", command=change_selected_connection)
    toggle_button.grid(row=2, column=2, padx=10, pady=10)

    global listbox
    listbox = tk.Listbox(root, height=20, width=120)
    listbox.grid(row=3, column=0, columnspan=3, padx=10, pady=10)
    for conn in connections:
        listbox.insert(tk.END, f"❓ {conn['name']} | {conn['ip']}")

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
