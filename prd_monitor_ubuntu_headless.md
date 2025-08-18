**Product Requirements Document (PRD)**

**Titolo:** Refactoring del Monitor Ping Clienti per Ubuntu Headless

**Versione:** 1.0\
**Data:** 07 Agosto 2025\
**Autore:** Andrea Cappone (ChatGPT o4-mini)

---

## 1. Contesto e Obiettivi

### 1.1 Contesto

Attualmente il progetto è un'applicazione Python che:

- Monitora la raggiungibilità di una lista di client (ping ogni 15 minuti).
- Utilizza una GUI Tkinter per configurazione e controllo.
- Salva lo stato e la configurazione in un file JSON locale.

Su Windows, viene convertito in `.exe` ma richiede avvio manuale come amministratore. Ora si migra su Ubuntu Server 24 (headless), senza GUI.

### 1.2 Obiettivi del Refactoring

- **Headless:** eliminare dipendenze da Tkinter, rendere l’app in esecuzione daemon tramite `systemd`.
- **CLI-first:** tutte le operazioni (start/stop/status, gestione connessioni) via linea di comando.
- **Affidabilità:** avvio automatico al boot, restart on-failure.
- **Modularità:** separare core (monitoring) dal front-end CLI.
- **Sicurezza:** continuare a usare locking per il JSON, logging strutturato.

---

## 2. Stakeholder e Utenti

- **Product Owner:** definisce requisiti e priorità.
- **Sviluppatore Junior:** esegue il refactoring e scrive il nuovo codice.
- **Amministratore di Sistema:** configura il servizio su Ubuntu.

---

## 3. Casi d’Uso (Use Cases)

| #   | Use Case                         | Attore       | Scopo                              |
| --- | -------------------------------- | ------------ | ---------------------------------- |
| UC1 | Avviare il monitor               | SysAdmin/CLI | Eseguire il ciclo di ping continuo |
| UC2 | Interrompere il monitor          | SysAdmin/CLI | Fermare pulito il daemon           |
| UC3 | Verificare stato                 | SysAdmin/CLI | Stampare ultimo stato di ogni host |
| UC4 | Aggiungere una connessione       | SysAdmin/CLI | Inserire nuovo host nel JSON       |
| UC5 | Rimuovere una connessione        | SysAdmin/CLI | Eliminare host dal JSON            |
| UC6 | Mettere in pausa una connessione | SysAdmin/CLI | Disabilitare temporaneamente host  |
| UC7 | Riprendere una connessione       | SysAdmin/CLI | Riabilitare host disabilitato      |
| UC8 | Cercare connessioni              | SysAdmin/CLI | Filtrare host per nome/IP          |

---

## 4. Requisiti Funzionali

1. **Core Monitoring**

   - Ping di tutti gli host ogni 15 minuti (configurabile).
   - Notifica via email in caso di stato cambiato (UP→DOWN o DOWN→UP).
   - Log su file in formato `INFO/ERROR` con timestamp.

2. **CLI Management**

   - Comando `monitor start [--interval N]`
   - Comando `monitor stop`
   - Comando `monitor status`
   - Comando `conn add --name NAME --ip IP`
   - Comando `conn remove --name NAME` o `--ip IP`
   - Comando `conn pause --name NAME` / `conn resume --name NAME`
   - Comando `conn list [--filter KEYWORD]`

3. **Persistenza**

   - File JSON con schema:

   ```json
   [
     {"name": "Server A", "ip": "192.168.1.10", "enabled": true},
     ...
   ]
   ```

   - Locking tramite `portalocker` per lettura/scrittura concorrente.

4. **Configurazione**

   - Parametri letti da environment o flag:
     - `--config PATH` (default `/opt/mp_ping/connections.json`)
     - `--interval SECONDS`
     - Variabili SMTP per invio email.

---

## 5. Requisiti Non-Funzionali

- **Portabilità:** Python 3.10+, compatibile Ubuntu 24 LTS.
- **Affidabilità:** `systemd` con `Restart=on-failure`.
- **Sicurezza:** file JSON protetto da permessi Unix (utente dedicato).
- **Manutenibilità:** codice modulare, docstring e test unitari.
- **Performance:** ciclo di ping non deve sovraccaricare CPU (<5% utilizzo).

---

## 6. Architettura Tecnica

1. **Modulo **``

   - Classe `Monitor`: carica/salva JSON, loop ping, send\_email, stop/start.

2. **Script CLI **``

   - Basato su `click` (o `argparse`).
   - Organizzazione in comandi (`@click.group`, `@click.command`).

3. **Systemd Unit**

   - File `/etc/systemd/system/mp_ping.service`
   - `ExecStart=/usr/bin/python3 /opt/mp_ping/cli.py monitor start`

4. **Logging**

   - `logging` su `/var/log/mp_ping.log`.
   - Rotazione con `logrotate` settato da SysAdmin.

5. **Pip/Requirements**

   - `ping3`
   - `portalocker`
   - `click`
   - `python-dotenv` (opzionale)

---

## 7. Testing & Quality

- **Unit tests** per:

  - Parsing/serializzazione JSON.
  - Stato `Monitor.ping_all()` con mock di `ping3`.
  - Comandi CLI (usando `click.testing.CliRunner`).

- **Integration tests**:

  - Simulare file JSON e correre ciclo di monitoring.
  - Verifica restart via `systemd-run --user ...`.

- **Code Coverage:** > 80%.

- **Linting:** `flake8`, `black`.

---

## 8. Milestones e Timeline

| Fase                | Durata Stimata | Data Inizio | Data Fine  |
| ------------------- | -------------- | ----------- | ---------- |
| Analisi & PRD       | 1 giorno       | 07/08/2025  | 07/08/2025 |
| Refactoring Core    | 2 giorni       | 08/08/2025  | 10/08/2025 |
| Implementazione CLI | 1 giorno       | 11/08/2025  | 11/08/2025 |
| Systemd & Deploy    | 1 giorno       | 12/08/2025  | 12/08/2025 |
| Testing & QA        | 2 giorni       | 13/08/2025  | 15/08/2025 |
| Review & Release    | 1 giorno       | 16/08/2025  | 16/08/2025 |

---

## 9. Criteri di Accettazione

- Il servizio parte automaticamente al boot e risponde ai comandi CLI.
- `monitor status` restituisce lo stato aggiornato.
- Gestione delle connessioni via CLI funziona senza errori.
- Logging generato e rotato correttamente.
- Test coverage >= 80%, linting OK.

---

*Fine del Documento.*

