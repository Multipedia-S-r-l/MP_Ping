#!/usr/bin/env python3

import click
import signal
import sys
from monitor import Monitor
import json
import os

def _read_status_file(status_path):
    if not os.path.exists(status_path):
        click.echo(f"Status file non trovato: {status_path}")
        return None
    try:
        with open(status_path, 'r') as f:
            data = json.load(f)
        return data
    except Exception as e:
        click.echo(f"Errore leggendo {status_path}: {e}")
        return None

def _get_status_icon(status):
    if status == 'UP':
        return '🟢'
    elif status == 'DOWN':
        return '🔴'
    elif status == 'UNKNOWN':
        return '❓'
    else:
        return '❔'

@click.group()
def cli():
    pass

@cli.group()
def monitor():
    """Comandi per il monitoraggio."""
    pass

@monitor.command()
@click.option('--config', default=None, help='Path file connessioni JSON')
@click.option('--interval', default=None, type=int, help='Intervallo ping in secondi')
def start(config, interval):
    """Avvia il monitor come daemon."""
    monitor = Monitor(config_path=config, interval=interval)
    def handle_sigterm(signum, frame):
        click.echo('Ricevuto SIGTERM, arresto monitor...')
        try:
            monitor.stop()
        except Exception:
            pass
    def handle_sigint(signum, frame):
        click.echo('Ricevuto SIGINT, arresto monitor...')
        try:
            monitor.stop()
        except Exception:
            pass
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigint)
    click.echo('Monitor avviato. Premi Ctrl+C per uscire.')
    try:
        monitor.run_monitor_loop()
    except KeyboardInterrupt:
        click.echo('Interrotto da tastiera.')

@monitor.command()
def status():
    """Mostra lo stato corrente delle connessioni."""
    monitor = Monitor()
    data = _read_status_file(monitor.status_path)
    if not data:
        click.echo("Nessun dato di stato disponibile.")
        return
    ts = data.get('timestamp')
    last = data.get('last_status', {})
    click.echo(f"\n\nStatus snapshot: {ts}\n")
    for ip, st in last.items():
        status_icon = _get_status_icon(st)
        click.echo(f"{status_icon} {ip:<15}\t{st}")
    # conteggi
    up_count = sum(1 for st in last.values() if st == 'UP')
    down_count = sum(1 for st in last.values() if st == 'DOWN')
    # connessioni in pausa lette dalla configurazione
    paused_count = sum(1 for c in monitor.connections if not c.get('enabled', True))
    click.echo(f"\nTotali: UP={up_count} | DOWN={down_count} | Pausa={paused_count}\n")

@cli.group()
def conn():
    """Gestione connessioni."""
    pass

@conn.command()
@click.option('--name', required=True, help='Nome connessione')
@click.option('--ip', required=True, help='Indirizzo IP')
def add(name, ip):
    monitor = Monitor()
    monitor.add_connection(name, ip)
    click.echo(f'Aggiunta connessione {name} ({ip})')

@conn.command()
@click.option('--name', default=None, help='Nome connessione')
@click.option('--ip', default=None, help='Indirizzo IP')
def remove(name, ip):
    monitor = Monitor()
    removed = monitor.remove_connection(name, ip)
    click.echo(f'Rimosse {removed} connessioni')

@conn.command()
@click.option('--name', required=True, help='Nome connessione')
def pause(name):
    monitor = Monitor()
    monitor.pause_connection(name)
    click.echo(f'Connessione {name} in pausa')

@conn.command()
@click.option('--name', required=True, help='Nome connessione')
def resume(name):
    monitor = Monitor()
    monitor.resume_connection(name)
    click.echo(f'Connessione {name} riattivata')

@conn.command()
@click.option('--filter', 'filter_keyword', default=None, help='Filtro per nome o IP')
def list(filter_keyword):
    """Lista connessioni con stato (usa snapshot scritto dal daemon)."""
    monitor = Monitor()
    conns = monitor.list_connections_with_status(filter_keyword)
    if not conns:
        click.echo("Nessuna connessione trovata (o status non disponibile).")
        return

    # stampa ordinata (name, ip, status) con padding semplice
    max_name = max((len(c['name']) for c in conns), default=20)
    max_ip = max((len(c['ip']) for c in conns), default=15)

    click.echo("\n")
    for c in conns:
        enabled_icon = '▶️' if c['enabled'] else '⏸️'
        st = c['status']
        status_icon = _get_status_icon(st)
        click.echo(f"{enabled_icon} {status_icon} {c['name']:<{max_name}} | {c['ip']:<{max_ip}} | {st}")
    # conteggi
    up_count = sum(1 for c in conns if c['status'] == 'UP')
    down_count = sum(1 for c in conns if c['status'] == 'DOWN')
    paused_count = sum(1 for c in conns if not c.get('enabled', True))
    click.echo(f"\nTotali: UP={up_count} | DOWN={down_count} | Pausa={paused_count}\n")
    
if __name__ == '__main__':
    cli() 