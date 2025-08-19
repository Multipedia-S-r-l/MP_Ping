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
- `conn pause`: mette in pausa una connessione con parametro `--name`
- `conn resume`: riprende il monitoraggio della connessione con parametro `--name`
- `conn list`: elenca tutte le connessioni monitorate. Parametro opzionale `--filter` per avere keyword su name o ip

## Configurazioni del progetto
### Percorso base
`/opt/mp_ping`

### Variabili ambiente
`/etc/default/mp_ping`

### Comandi per il servizio linux
- `systemctl daemon-reload`: aggiornamento di tutti i servizi systemd (se modifico il file systemd)
- `systemctl restart mp_ping`: riavvio del servizio systemd (se vengono modificati i file)
- `systemctl status mp_ping -l`: status relativo al servizio systemd
- `journalctl -u mp_ping -f`: Log in real-time
