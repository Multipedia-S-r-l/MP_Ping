#!/usr/bin/env python3

import click
import signal
import sys
from monitor import Monitor

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
        click.echo('Ricevuto SIGTERM, uscita...')
        sys.exit(0)
    signal.signal(signal.SIGTERM, handle_sigterm)
    click.echo('Monitor avviato. Premi Ctrl+C per uscire.')
    try:
        monitor.run_monitor_loop()
    except KeyboardInterrupt:
        click.echo('Interrotto da tastiera.')

@monitor.command()
def status():
    """Mostra lo stato corrente delle connessioni."""
    monitor = Monitor()
    status = monitor.status()
    for ip, st in status.items():
        click.echo(f'{ip}: {st}')

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
    monitor = Monitor()
    conns = monitor.list_connections(filter_keyword)
    for c in conns:
        status = monitor.last_status.get(c['ip'], 'UNKNOWN')
        click.echo(f"{'🟢' if c.get('enabled', True) else '⏸️'} {c['name']} | {c['ip']} | {status}")

if __name__ == '__main__':
    cli() 