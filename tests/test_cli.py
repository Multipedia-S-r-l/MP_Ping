from click.testing import CliRunner
from cli import cli
from unittest.mock import patch

def test_cli_add_remove_list():
    runner = CliRunner()
    with patch('cli.Monitor') as MockMonitor:
        instance = MockMonitor.return_value
        instance.list_connections_with_status.return_value = [
            {'name': 'Test', 'ip': '1.2.3.4', 'enabled': True, 'status': 'UP'}
        ]
        instance.last_status = {'1.2.3.4': 'UP'}
        result = runner.invoke(cli, ['conn', 'add', '--name', 'Test', '--ip', '1.2.3.4'])
        assert 'Aggiunta connessione' in result.output
        result = runner.invoke(cli, ['conn', 'remove', '--ip', '1.2.3.4'])
        assert 'Rimosse' in result.output
        result = runner.invoke(cli, ['conn', 'list'])
        assert 'Test' in result.output
        # verifica presenza dei totali
        assert 'Totali:' in result.output
        assert 'UP=1' in result.output
        assert 'DOWN=0' in result.output
        assert 'Pausa=0' in result.output