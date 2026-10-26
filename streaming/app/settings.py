"""Validated non-secret dashboard preferences, scoped to the local state directory."""
import json
import os
import threading
import uuid
from pathlib import Path
from .transfers import ID

FIELDS = {'broker', 'mode', 'sender', 'recipient'}


def validate_settings(data):
    if not isinstance(data, dict) or set(data) - FIELDS:
        raise ValueError('Save only broker, action, sender and recipient settings. Secrets are never saved here.')
    values = {key: str(data.get(key, '')).strip() for key in FIELDS}
    if values['mode'] not in ('send', 'receive'):
        raise ValueError('Choose send or receive.')
    broker = values['broker']
    if len(broker) > 250 or any(c.isspace() for c in broker) or ':' not in broker:
        raise ValueError('Enter a Kafka broker address as host:port.')
    host, port = broker.rsplit(':', 1)
    if not host or not port.isascii() or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError('Enter a Kafka broker address with a port from 1 to 65535.')
    for key in ('sender', 'recipient'):
        if not ID.fullmatch(values[key]):
            raise ValueError('Participant IDs must start with a letter or number and use 1-64 letters, numbers, dots, underscores or hyphens.')
    if values['sender'] == values['recipient']:
        raise ValueError('Use different sender and recipient IDs.')
    return values


class Settings:
    def __init__(self, root):
        self.path = Path(root) / 'settings.json'
        self.lock = threading.Lock()

    def load(self):
        with self.lock:
            try:
                if self.path.stat().st_size > 8192:
                    raise ValueError()
                return {'settings': validate_settings(json.loads(self.path.read_text(encoding='utf-8'))), 'warning': None}
            except FileNotFoundError:
                return {'settings': {}, 'warning': None}
            except (ValueError, OSError, UnicodeError):
                return {'settings': {}, 'warning': 'Saved settings could not be read. Enter and save your settings again. Transfers and history are unchanged.'}

    def save(self, data):
        values = validate_settings(data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(uuid.uuid4().hex + '.tmp')
        with self.lock:
            try:
                with temp.open('x', encoding='utf-8') as output:
                    json.dump(values, output, indent=2)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temp, self.path)
            finally:
                temp.unlink(missing_ok=True)
        return {'settings': values, 'warning': None}
