import os
import tempfile
from monitor import Monitor
from unittest.mock import patch

def test_add_and_remove_connection():
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        config_path = tf.name
    try:
        monitor = Monitor(config_path=config_path)
        monitor.add_connection('Test', '1.2.3.4')
        assert any(c['ip'] == '1.2.3.4' for c in monitor.connections)
        monitor.remove_connection(ip='1.2.3.4')
        assert not any(c['ip'] == '1.2.3.4' for c in monitor.connections)
    finally:
        os.remove(config_path)

def test_ping_all_mock():
    with tempfile.NamedTemporaryFile(delete=False) as tf:
        config_path = tf.name
    try:
        monitor = Monitor(config_path=config_path)
        monitor.add_connection('Test', '1.2.3.4')
        with patch('monitor.ping', return_value=True):
            results = monitor.ping_all()
            assert results[0]['status'] == 'UP'
    finally:
        os.remove(config_path) 