"""Bootstrap the project virtual environment, then run the local app launcher."""
from pathlib import Path
import subprocess
import sys
import venv


def main():
    root = Path(__file__).resolve().parent
    if sys.version_info < (3, 10):
        print('Install Python 3.12 and relaunch. Python 3.10 or newer is required.')
        return 1
    target = root / '.venv' / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    if not target.is_file():
        if '--check-only' in sys.argv:
            print('Project environment missing. Run the launcher normally to create .venv.')
            return 1
        print('First launch: creating the project .venv environment...')
        try:
            venv.EnvBuilder(with_pip=True).create(root / '.venv')
        except (OSError, subprocess.SubprocessError):
            print('Could not create .venv. Check folder permissions and install Python with venv/pip support.')
            return 1
    try:
        return subprocess.call([str(target), '-m', 'streaming.app.launcher', *sys.argv[1:]], cwd=root)
    except OSError:
        print('Could not run the project Python environment. Check .venv and your Python installation.')
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
