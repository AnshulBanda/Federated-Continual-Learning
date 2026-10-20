"""Start the local dashboard with prerequisite checks and a browser window."""
import argparse
import getpass
import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import webbrowser

from .dashboard import server
from .settings import Settings

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE = ROOT / 'streaming' / '.local' / 'transfers'


def prerequisites(state_dir):
    problems = []
    if sys.version_info < (3, 10):
        problems.append('Python 3.10 or newer is required. Python 3.12 is recommended.')
    if importlib.util.find_spec('confluent_kafka') is None:
        problems.append('Kafka client missing. Install streaming/requirements.txt using this Python environment.')
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=state_dir) as probe:
            probe.write(b'check')
    except OSError:
        problems.append('Local application storage is not writable. Choose another --state-dir or check folder permissions.')
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--state-dir', type=Path, default=DEFAULT_STATE)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--check-only', action='store_true', help='Check local prerequisites without prompting, installing or starting services.')
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535.')
    problems = prerequisites(args.state_dir)
    if not args.check_only and importlib.util.find_spec('confluent_kafka') is None:
        print('Kafka client is needed to transfer files. Installation uses streaming/requirements.txt.')
        try:
            install = input('Install it in this Python environment now? [y/N]: ').strip().lower() == 'y'
        except EOFError:
            install = False
        if install:
            try:
                subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', str(ROOT / 'streaming/requirements.txt')], check=True)
                importlib.invalidate_caches()
            except (OSError, subprocess.CalledProcessError):
                print('Installation failed. Check your internet connection and Python version, then launch again.')
                return 1
            problems = prerequisites(args.state_dir)
    if problems:
        for problem in problems:
            print('Needs attention: ' + problem)
        return 1
    saved = Settings(args.state_dir).load()
    if saved['warning']:
        print(saved['warning'])
    print('Local storage and Kafka client: ready.')
    if args.check_only:
        print('Broker and peer availability must be checked in the dashboard. No services were started.')
        return 0
    if len(os.environ.get('FCL_TRANSFER_SECRET', '')) < 32:
        try:
            secret = getpass.getpass('Paste the shared transfer secret (hidden): ')
        except (EOFError, KeyboardInterrupt):
            print('\nLaunch cancelled.')
            return 1
        if len(secret) < 32:
            print('Secret must contain at least 32 characters. Copy only the secret line, then launch again.')
            return 1
        os.environ['FCL_TRANSFER_SECRET'] = secret
    try:
        app = server(args.state_dir, args.port)
    except RuntimeError:
        print('Another dashboard owns this state folder. Use its existing window or stop it before relaunching. No state was deleted.')
        return 1
    except (OSError, sqlite3.Error):
        print(f'Could not open port {args.port} or local storage. Stop the existing dashboard or choose --port and --state-dir explicitly.')
        return 1
    address = f'http://127.0.0.1:{app.server_port}'
    print('Weight dashboard: ' + address)
    print('Keep this window open. Press Ctrl+C to stop. Kafka and ZeroTier must be running separately.')
    if not args.no_browser:
        try:
            if not webbrowser.open(address):
                print('Open the dashboard address above in your browser.')
        except webbrowser.Error:
            print('Open the dashboard address above in your browser.')
    try:
        app.serve_forever()
    except KeyboardInterrupt:
        print('\nStopping dashboard.')
    finally:
        app.transfers.cancelled.set()
        app.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
