import os
import json
import time
import logging
import portalocker
from datetime import datetime
from ping3 import ping
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from threading import Lock, Event, Thread

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
        
        self.down_times = {}
        self.logger = self.setup_logger()

        # controllo del loop e struttura per retry threads
        self.running = Event()
        self.running.set()
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
                # aspetta il retry interval
                time.sleep(self.retry_interval)

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
                self.down_times[ip] = datetime.now()
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
                time.sleep(0.5)
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


    def pause_connection(self, name):
        for c in self.connections:
            if c['name'] == name:
                c['enabled'] = False
        self.save_connections()


    def resume_connection(self, name):
        for c in self.connections:
            if c['name'] == name:
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


    def ping_all(self):
        """
        Esegue un ping su tutte le connessioni configurate.
        Quando viene rilevato un primo DOWN, non invia subito la mail: entra in fase di CHECKING
        e lancia un worker che esegue self.retries tentativi distanziati di self.retry_interval secondi.
        Solo se tutti i tentativi falliscono viene inviata la mail di DOWN.
        """
        results = []
        for conn in self.connections:
            if not conn.get('enabled', True):
                # connessioni in pausa non riportano stato
                with self.lock:
                    self.last_status[conn['ip']] = 'UNKNOWN'
                continue

            ip = conn['ip']
            name = conn['name']

            try:
                response = ping(ip, timeout=2)
            except Exception as e:
                # in caso di eccezione ping3, trattiamo come failure
                self.logger.debug(f'Errore ping {ip}: {e}')
                response = None

            # stato rilevato in questo ciclo
            observed = 'UP' if response else 'DOWN'

            with self.lock:
                prev_status = self.last_status.get(ip)

            # Se osservato UP
            if observed == 'UP':
                # se prima era DOWN (o UNKNOWN), invia UP immediatamente (se è una transizione DOWN->UP)
                # manteniamo comportamento precedente: invia notifica UP al passaggio da DOWN->UP
                if prev_status == 'DOWN':
                    # calcola durata DOWN se presente
                    extra = ""
                    if ip in self.down_times:
                        down_duration = datetime.now() - self.down_times[ip]
                        minutes = int(down_duration.total_seconds() / 60)
                        seconds = int(down_duration.total_seconds() % 60)
                        extra = f"Tempo di DOWN: {minutes} minuti e {seconds} secondi"
                        del self.down_times[ip]
                    # setta stato
                    with self.lock:
                        self.last_status[ip] = 'UP'
                    # invia notifica UP
                    try:
                        self.send_email_alert(name, ip, 'UP', extra)
                    except Exception as e:
                        self.logger.error(f"Errore invio email UP per {ip}: {e}")
                else:
                    # semplicemente aggiorna a UP
                    with self.lock:
                        self.last_status[ip] = 'UP'
                # se esiste un worker di conferma in corso, segnaliamo che è recuperato
                with self.retry_lock:
                    if ip in self.retry_threads:
                        # lasciamo che il worker termini al prossimo controllo (worker verifica last_status)
                        # oppure possiamo rimuovere subito la traccia così non verrà duplicato un nuovo worker
                        # (ma lasciamo il worker leggere last_status e terminare)
                        pass

            # Se osservato DOWN
            else:
                # se precedente stato era DOWN -> è già DOWN, mantieni stato e (se non è stata inviata mail, probabilmente l'abbiamo già inviata)
                if prev_status == 'DOWN':
                    with self.lock:
                        self.last_status[ip] = 'DOWN'
                # se precedente era CHECKING (già in conferma) -> mantieni CHECKING (o DOWN se già confermato)
                elif prev_status == 'CHECKING':
                    # mantieni lo stato (il worker deciderà)
                    with self.lock:
                        self.last_status[ip] = 'CHECKING'
                else:
                    # prima era UP o UNKNOWN: avvia la conferma DOWN
                    with self.lock:
                        self.last_status[ip] = 'CHECKING'
                    self.logger.info(f"Prima rilevazione DOWN per {name} ({ip}) — avviata procedura di conferma ({self.retries} tentativi ogni {self.retry_interval}s)")
                    self.schedule_confirm_down(name, ip)

            # log e raccolta risultati
            with self.lock:
                current_status = self.last_status.get(ip, 'UNKNOWN')
            results.append({'name': name, 'ip': ip, 'status': current_status})
            self.logger.info(f'{name} ({ip}) {current_status}')
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
            self.running.clear()
            self.logger.info("Monitor stop requested.")
        except Exception:
            pass


    # chiamare dump_status dopo ogni ciclo di ping, es.: in run_monitor_loop():
    def run_monitor_loop(self):
        while self.running.is_set():
            # ricarica conf se implementato...
            try:
                self.ping_all()
            except Exception as e:
                self.logger.exception(f"Errore in ping_all: {e}")
            # dopo il ciclo di ping scriviamo lo stato
            self.dump_status()
            time.sleep(self.interval)