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

## Backup automatici dello status
Crea snapshot atomici di `status.json` e rimuove i backup più vecchi della retention configurata (30 giorni).

### File coinvolti:
- `systemd/mp_status_backup.service`: esegue `mp_status_backup.py` in modalità oneshot con utente `multipedia` e gruppo `mp_users`
- `systemd/mp_status_backup.timer`: pianifica l'esecuzione alle 08:30, 13:30, 18:30
- Script:
  - Percorso: `/usr/local/bin/mp_status_backup.py`
  - Lettura sicura di `status.json` tramite `portalocker` (se disponibile); in fallback procede senza lock mostrando un warning.
  - I backup vengono scritti con nome `status_YYYYMMDD_HHMMSS.json` e permessi `0640`.
- Variabili di configurazione (file `/etc/default/mp_status_backup`):
  - `MP_STATUS_FILE` (default `/opt/mp_ping/status.json`)
  - `MP_BACKUP_DIR` (default `/var/backups/mp_ping`)
  - `MP_BACKUP_RETENTION_DAYS` (default `30`)
  - `MP_OWNER` (default `multipedia`)
  - `MP_GROUP` (default `mp_users`)

### Comandi utili:
- Verifica timer: `systemctl status mp_status_backup.timer` e `systemctl list-timers mp_status_backup*`
- Abilita e avvia timer: `systemctl enable --now mp_status_backup.timer`
- Esecuzione immediata snapshot: `systemctl start mp_status_backup.service`
- Log ultimi run: `journalctl -u mp_status_backup.service -n 100 --no-pager`
- Directory backup: `/var/backups/mp_ping`

### Note:
- Dopo modifiche ai file `.service`/`.timer`: `systemctl daemon-reload` e poi `systemctl restart mp_status_backup.timer` (utente `multipedia`).
- Assicurarsi che il venv sia in `/opt/mp_ping/.venv` e includa `portalocker`.