# MP_Ping

## Comandi per creare file exe
- `pyinstaller --onefile --windowed --icon=favicon.ico --name="MP_Ping" script.py`
- `pyinstaller --onefile --icon=favicon.ico --name="MP_Ping" script.py`
- Opzione `--windowed` serve per evitare la creazione di una finestra con il terminale
 
## Comandi per controllare il monitoraggio
- `monitor start`: avvia il monitor
- `monitor status`: fornisce info sulle connessioni monitorate

## Comandi per modificare le connessioni
- `conn add`: aggiunge nuova connessione con parametri `--name` e `--ip`
- `conn remove`: rimuove una connessione con parametri `--name` o `--ip` (in OR)
- `conn pause`: mette in pausa una connessione con parametro `--ip`
- `conn resume`: riprende il monitoraggio della connessione con parametro `--ip`
- `conn list`: elenca tutte le connessioni monitorate. Parametro opzionale `--filter` per avere keyword su name o ip

## Configurazioni del progetto
### Server INFO
- IP: 192.168.0.10
- Name: srv-linux
- Percorso base: `/opt/mp_ping`
- Variabili ambiente: `/etc/default/mp_ping`
- Comandi wrapper: `/usr/local/bin`

### Utenti
- Andrea: andrea | A2025c
- Riccardo: riccardo | R2025r
- Erik: erik | E2025c

### Comandi per il servizio linux
- `mp_ping status`: status relativo al servizio systemd
- `mp_ping restart`: riavvio del servizio systemd (se viene modificato l'elenco connessioni con `conn (add|remove|pause|resume)`)

### Comandi per il servizio linux (SOLO con utente multipedia)
- `systemctl daemon-reload`: aggiornamento di tutti i servizi systemd (se modifico il file systemd)
- `systemctl restart mp_ping`: riavvio del servizio systemd (se vengono modificati i file o l'elenco connessioni)
- `systemctl status mp_ping -l`: status relativo al servizio systemd
- `journalctl -u mp_ping -f`: Log in real-time
