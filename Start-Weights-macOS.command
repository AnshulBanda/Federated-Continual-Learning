#!/bin/bash
cd "$(dirname "$0")" || exit 1
if [ -x ".venv/bin/python" ]; then
    ".venv/bin/python" launch_weights.py "$@"
elif command -v python3.12 >/dev/null 2>&1; then
    python3.12 launch_weights.py "$@"
elif command -v python3 >/dev/null 2>&1; then
    python3 launch_weights.py "$@"
else
    echo "Install Python 3.12 from python.org, then open this launcher again."
    read -r -p "Press Enter to close."
    exit 1
fi
result=$?
if [ "$result" -ne 0 ]; then
    read -r -p "Startup failed. Read the message above, then press Enter to close."
fi
exit "$result"
