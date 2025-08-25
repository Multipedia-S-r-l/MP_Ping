import os
import json
import time
import logging
import portalocker
from datetime import datetime
from zoneinfo import ZoneInfo
from ping3 import ping
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from threading import Lock, Event, Thread
from concurrent.futures import ThreadPoolExecutor, as_completed

class Monitor:
    def __init__(self, config_path=None, status_path=None, interval=None):
        self.config_path = config_path or os.environ.get('MP_PING_CONFIG', '/opt/mp_ping/connections.json')
        self.status_path = status_path or os.environ.get('MP_STATUS_FILE', '/opt/mp_ping/status.json')
        self.interval = interval or int(os.environ.get('MP_PING_INTERVAL', 900))

        # parametri retry per conferma DOWN
        self.retries = int(os.environ.get('MP_PING_RETRIES', 10))
        self.retry_interval = int(os.environ.get('MP_PING_RETRY_INTERVAL', 30))

        self.lock = Lock()
        self.connections = self.load_connections()
        # carica stato iniziale da snapshot se presente
        snapshot = self._read_json_with_lock(self.status_path) or {}
        last = snapshot.get('last_status') if isinstance(snapshot, dict) else None
        if isinstance(last, dict):
            self.last_status = {conn['ip']: last.get(conn['ip']) for conn in self.connections}
        else:
            self.last_status = {conn['ip']: None for conn in self.connections}
        
        self.local_tz = ZoneInfo('Europe/Rome')
        self.down_times = {}
        self.logger = self.setup_logger()

        # controllo del loop e struttura per retry threads
        self.running = Event()
        self.running.set()
        # event per segnalare lo STOP (usato per wait interruptible)
        self.stop_event = Event()

        self.retry_threads = {}     # ip -> Thread
        self.retry_lock = Lock()    # protegge retry_threads


    def _atomic_write_json(self, path: str, data):
        tmp = path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)


    def _read_json_with_lock(self, path, lock_mode='r'):
        """Legge un JSON con portalocker (shared lock). Restituisce None se non esiste o errore."""
        if not os.path.exists(path):
            return None
        try:
            with open(path, lock_mode) as f:
                # lock shared per lettura
                portalocker.lock(f, portalocker.LOCK_SH)
                try:
                    data = json.load(f)
                finally:
                    portalocker.unlock(f)
            return data
        except Exception:
            return None
        

    def _confirm_down_worker(self, name, ip):
        """Worker che esegue self.retries tentativi a intervalli self.retry_interval.
        Se uno dei tentativi torna UP, si cancella la conferma e si riporta lo stato a UP.
        Se tutti falliscono, si invia la mail di DOWN e si imposta lo stato a DOWN.
        """
        try:
            for attempt in range(self.retries):
                if self.stop_event.is_set():
                    break

                # aspetta in modo interrompibile il retry interval
                self.stop_event.wait(self.retry_interval)

                if self.stop_event.is_set():
                    break

                try:
                    resp = ping(ip, timeout=2)
                except Exception as e:
                    self.logger.debug(f"Errore ping in confirm worker per {ip}: {e}")
                    resp = None

                if resp:
                    # recovered during confirmation
                    with self.lock:
                        self.last_status[ip] = 'UP'
                    self.logger.info(f"{name} ({ip}) recuperato durante conferma (attempt {attempt+1}). Nessuna email DOWN inviata.")
                    # rimuovi eventuale down_time se impostato
                    if ip in self.down_times:
                        del self.down_times[ip]
                    break
                else:
                    self.logger.debug(f"Confirm attempt {attempt+1}/{self.retries} per {ip} ancora DOWN.")

            else:
                # eseguito se il loop non ha fatto break: tutti i tentativi falliti -> conferma DOWN
                with self.lock:
                    self.last_status[ip] = 'DOWN'
                # registra down start time
                self.down_times[ip] = datetime.now(self.local_tz)
                # invia email DOWN
                self.logger.info(f"{name} ({ip}) DOWN confermato dopo {self.retries} tentativi.")
                try:
                    text = f"Connessione confermata DOWN dopo {self.retries} tentativi."
                    text += f"\nConnessione DOWN alle {self.down_times[ip].strftime('%H:%M:%S')}"
                    self.send_email_alert(name, ip, 'DOWN', text)
                except Exception as e:
                    self.logger.error(f"Errore invio email DOWN per {ip}: {e}")

        finally:
            # cleanup: rimuovi il thread dalla mappa
            with self.retry_lock:
                try:
                    del self.retry_threads[ip]
                except KeyError:
                    pass


    def setup_logger(self):
        logger = logging.getLogger('mp_ping')
        if logger.handlers:
            return logger
        logger.setLevel(logging.INFO)

        # preferisci path da env var, altrimenti default in /var/log/mp_ping/mp_ping.log
        log_file = os.getenv('MP_LOGFILE', '/var/log/mp_ping/mp_ping.log')
        fmt = '%(asctime)s - %(levelname)s - %(message)s'
        formatter = logging.Formatter(fmt)

        # tenta FileHandler, ma se fallisce (permessi) usa StreamHandler (stdout -> catturato da journald/systemd)
        try:
            fh = logging.FileHandler(log_file)
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except Exception as e:
            # scrivi una riga su stderr/journal per segnalare il problema
            sh = logging.StreamHandler()
            sh.setFormatter(formatter)
            logger.addHandler(sh)
            logger.error(f'Impossibile aprire file di log {log_file}: {e}. Logging su stdout.')
        return logger


    def load_connections(self):
        if not os.path.exists(self.config_path):
            return []
        with open(self.config_path, 'r') as f:
            portalocker.lock(f, portalocker.LOCK_SH)
            data = json.load(f)
            portalocker.unlock(f)
        return data


    def save_connections(self):
        for _ in range(5):
            try:
                with open(self.config_path, 'w') as f:
                    portalocker.lock(f, portalocker.LOCK_EX)
                    json.dump(self.connections, f, indent=4)
                    portalocker.unlock(f)
                return
            except Exception as e:
                self.logger.error(f'Errore salvataggio connessioni: {e}')
                self.stop_event.wait(0.5)
        raise RuntimeError('Impossibile salvare le connessioni dopo 5 tentativi.')


    def add_connection(self, name, ip):
        self.connections.append({'name': name, 'ip': ip, 'enabled': True})
        self.save_connections()
        self.last_status[ip] = 'UNKNOWN'


    def remove_connection(self, name=None, ip=None):
        before = len(self.connections)
        self.connections = [c for c in self.connections if not ((name and c['name'] == name) or (ip and c['ip'] == ip))]
        self.save_connections()
        self.last_status = {c['ip']: self.last_status.get(c['ip'], 'UNKNOWN') for c in self.connections}
        return before - len(self.connections)


    def pause_connection(self, ip):
        for c in self.connections:
            if c['ip'] == ip:
                c['enabled'] = False
        self.save_connections()


    def resume_connection(self, ip):
        for c in self.connections:
            if c['ip'] == ip:
                c['enabled'] = True
        self.save_connections()


    def list_connections_with_status(self, filter_keyword=None):
        """
        Restituisce una lista di dict delle connessioni con campo 'status' unito dallo snapshot.
        Ogni elemento: {'name':..., 'ip':..., 'enabled':..., 'status': ...}
        Il filtro (filter_keyword) cerca case-insensitive su name e substring su ip.
        """
        # leggi config e status usando i path corretti (self.config_path e self.status_path)
        conns = self._read_json_with_lock(self.config_path) or []
        status_snapshot = self._read_json_with_lock(self.status_path) or {}
        last = status_snapshot.get('last_status', {}) if isinstance(status_snapshot, dict) else {}

        def matches(c):
            if not filter_keyword:
                return True
            fk = filter_keyword.lower()
            name = (c.get('name') or '').lower()
            ip = c.get('ip') or ''
            return fk in name or fk in ip

        out = []
        for c in conns:
            if not matches(c):
                continue
            ip = c.get('ip', '')
            s = last.get(ip)
            status = s if s is not None else 'UNKNOWN'
            out.append({
                'name': c.get('name', '<no name>'),
                'ip': ip,
                'enabled': c.get('enabled', True),
                'status': status,
                'raw': c
            })
        return out


    def _ping_one(self, conn):
        """Ping one connection; returns (name, ip, status)."""
        ip = conn.get('ip')
        name = conn.get('name', '<no name>')
        if not conn.get('enabled', True):
            return name, ip, 'UNKNOWN'
        try:
            resp = ping(ip, timeout=2)
            status = 'UP' if resp else 'DOWN'
        except Exception as e:
            self.logger.debug(f"Errore ping {ip}: {e}")
            status = 'DOWN'
        return name, ip, status


    def ping_all(self):
        """
        Esegue ping in parallelo usando un ThreadPoolExecutor.
        Mantiene la logica originale per UP/CHECKING/DOWN e rispetta self.stop_event.
        """
        results = []
        if not self.connections:
            return results

        max_workers = min(20, max(1, len(self.connections)))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(self._ping_one, conn): conn for conn in self.connections}

            for fut in as_completed(future_map):
                # se è stato segnalato stop, interrompi la raccolta
                if self.stop_event.is_set():
                    self.logger.info("Stop richiesto: interrompo raccolta risultati ping.")
                    break

                try:
                    name, ip, observed = fut.result()
                except Exception as e:
                    self.logger.debug(f"Errore ottenendo risultato ping: {e}")
                    continue

                # se disabilitata
                if observed == 'UNKNOWN':
                    with self.lock:
                        self.last_status[ip] = 'UNKNOWN'
                    results.append({'name': name, 'ip': ip, 'status': 'UNKNOWN'})
                    continue

                with self.lock:
                    prev_status = self.last_status.get(ip)

                # Gestione UP
                if observed == 'UP':
                    if prev_status == 'DOWN':
                        up_time = datetime.now(self.local_tz)
                        extra = f"Connessione UP alle {up_time.strftime('%H:%M:%S')}"
                        if ip in self.down_times:
                            down_duration = datetime.now(self.local_tz) - self.down_times[ip]
                            minutes = int(down_duration.total_seconds() / 60)
                            seconds = int(down_duration.total_seconds() % 60)
                            extra += f"\nTempo di DOWN: {minutes} minuti e {seconds} secondi"
                            del self.down_times[ip]
                        with self.lock:
                            self.last_status[ip] = 'UP'
                        try:
                            self.send_email_alert(name, ip, 'UP', extra)
                        except Exception as e:
                            self.logger.error(f"Errore invio email UP per {ip}: {e}")
                    else:
                        with self.lock:
                            self.last_status[ip] = 'UP'
                    with self.retry_lock:
                        if ip in self.retry_threads:
                            pass

                # Gestione DOWN / CHECKING
                else:
                    if prev_status == 'DOWN':
                        with self.lock:
                            self.last_status[ip] = 'DOWN'
                    elif prev_status == 'CHECKING':
                        with self.lock:
                            self.last_status[ip] = 'CHECKING'
                    else:
                        with self.lock:
                            self.last_status[ip] = 'CHECKING'
                        self.logger.info(f"Prima rilevazione DOWN per {name} ({ip}) — avviata procedura di conferma ({self.retries} tentativi ogni {self.retry_interval}s)")
                        # controlla stop prima di schedulare
                        if not self.stop_event.is_set():
                            self.schedule_confirm_down(name, ip)

                # log e raccolta risultati
                with self.lock:
                    current_status = self.last_status.get(ip, 'UNKNOWN')
                results.append({'name': name, 'ip': ip, 'status': current_status})
                self.logger.info(f'{name} ({ip}) {current_status}')

        # opzionale: cancella future rimanenti (se stop_event è stato settato)
        # i thread in esecuzione termineranno in breve (timeout ping)
        return results


    def schedule_confirm_down(self, name, ip):
        """Avvia in background un worker che esegue i tentativi di conferma per l'IP.
        Evita di lanciare più worker contemporanei per lo stesso IP.
        """
        with self.retry_lock:
            if ip in self.retry_threads:
                # già in corso
                self.logger.debug(f"Retry già in corso per {ip}, skip schedule.")
                return
            thread = Thread(target=self._confirm_down_worker, args=(name, ip), daemon=True)
            self.retry_threads[ip] = thread
            thread.start()


    def send_email_alert(self, name, ip, status, text=""):
        sender_email = os.environ.get('MP_PING_EMAIL')
        sender_password = os.environ.get('MP_PING_EMAIL_PASSWORD')
        recipient_email = os.environ.get('MP_PING_EMAIL_TO')
        smtp_server = os.environ.get('MP_PING_SMTP_SERVER')
        smtp_port = int(os.environ.get('MP_PING_SMTP_PORT', 465))
        sender_name = os.environ.get('MP_PING_EMAIL_NAME', 'Multipedia Ping')
        if not all([sender_email, sender_password, recipient_email, smtp_server]):
            self.logger.error('Variabili ambiente SMTP mancanti, impossibile inviare email')
            return
        subject = f"Connessione {status}: {name} ({ip})"
        body = f"L'indirizzo IP {ip} per la connessione {name} è ora {status}.\n\n{text}"
        msg = MIMEMultipart()
        msg['From'] = f"{sender_name} <{sender_email}>"
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        try:
            with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, recipient_email, msg.as_string())
            self.logger.info(f'Email inviata a {recipient_email}')
        except Exception as e:
            self.logger.error(f'Errore invio email: {e}')


    def status(self):
        return self.last_status.copy()


    def dump_status(self):
        """Scrive lo stato corrente last_status su self.status_path (atomico)."""
        try:
            # costruisci struttura exportabile
            export = {
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'last_status': self.last_status,  # dizionario ip -> stato
            }
            # usa locking per evitare race con altri processi che leggono
            # notare: portalocker su write non è strettamente necessario qui se usiamo replace atomico,
            # ma lo usiamo solo per coerenza se altri leggono con portalocker.
            self._atomic_write_json(self.status_path, export)
        except Exception as e:
            # logga ma non fallire il ciclo
            self.logger.error(f"Errore dump_status: {e}")


    def stop(self):
        """Ferma il loop del monitor in modo pulito."""
        try:
            # segnala STOP ai loop e worker
            self.stop_event.set()
            # mantieni compatibilità: clear dell'event 'running'
            try:
                self.running.clear()
            except Exception:
                pass

            # aspetta che i worker finiscano, ma non sommare timeout per ciascuno
            # invece aspettiamo un timeout totale (es. 10 secondi) per tutti i worker
            timeout_total = 10.0
            deadline = time.time() + timeout_total
            with self.retry_lock:
                threads = list(self.retry_threads.values())
            for t in threads:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                # join con timeout limitato (non sommiamo i timeout)
                t.join(timeout=min(1.0, remaining))
            # dopo l'attesa, logga se ci sono ancora thread vivi
            with self.retry_lock:
                still = [ip for ip in self.retry_threads.keys()]
            if still:
                self.logger.warning(f"Stop: worker ancora attivi dopo {timeout_total}s: {still}")
            self.logger.info("Monitor stop requested.")
        except Exception:
            pass



    # chiamare dump_status dopo ogni ciclo di ping, es.: in run_monitor_loop():
    def run_monitor_loop(self):
        while not self.stop_event.is_set():
            # ricarica conf se implementato...
            try:
                self.ping_all()
            except Exception as e:
                self.logger.exception(f"Errore in ping_all: {e}")
            # dopo il ciclo di ping scriviamo lo stato
            self.dump_status()
            # attendi l'intervallo ma esci immediatamente se arriva stop_event
            self.stop_event.wait(self.interval)