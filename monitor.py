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
from threading import Lock

class Monitor:
    def __init__(self, config_path=None, interval=None):
        self.config_path = config_path or os.environ.get('MP_PING_CONFIG', '/opt/mp_ping/connections.json')
        self.interval = interval or int(os.environ.get('MP_PING_INTERVAL', 900))
        self.lock = Lock()
        self.connections = self.load_connections()
        self.last_status = {conn['ip']: None for conn in self.connections}
        self.down_times = {}
        self.logger = self.setup_logger()

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

    def list_connections(self, filter_keyword=None):
        if not filter_keyword:
            return self.connections
        return [c for c in self.connections if filter_keyword.lower() in c['name'].lower() or filter_keyword in c['ip']]

    def ping_all(self):
        results = []
        for conn in self.connections:
            if not conn.get('enabled', True):
                self.last_status[conn['ip']] = 'UNKNOWN'
                continue
            ip = conn['ip']
            name = conn['name']
            response = ping(ip, timeout=2)
            current_status = 'UP' if response else 'DOWN'
            prev_status = self.last_status.get(ip)
            if prev_status is not None and prev_status != current_status:
                if current_status == 'DOWN':
                    self.down_times[ip] = datetime.now()
                    self.send_email_alert(name, ip, current_status, f"Connessione DOWN alle {self.down_times[ip].strftime('%H:%M:%S')}")
                elif current_status == 'UP' and ip in self.down_times:
                    down_duration = datetime.now() - self.down_times[ip]
                    minutes = int(down_duration.total_seconds() / 60)
                    seconds = int(down_duration.total_seconds() % 60)
                    self.send_email_alert(name, ip, current_status, f"Tempo di DOWN: {minutes} minuti e {seconds} secondi")
                    del self.down_times[ip]
            self.last_status[ip] = current_status
            results.append({'name': name, 'ip': ip, 'status': current_status})
            self.logger.info(f'{name} ({ip}) {current_status}')
        return results

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

    def run_monitor_loop(self):
        while True:
            self.ping_all()
            time.sleep(self.interval) 