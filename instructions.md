# Teammate setup: model-weight transfers

Use this guide to send and receive existing weight files between Windows and macOS laptops. Kafka runs on Anshul's Windows laptop. Each teammate runs a dashboard on their own laptop. This does not run model training.

## 1. Get these details from Anshul

- **Kafka broker:** the Windows host's reachable address followed by `:9092`.
- **Shared secret:** the same secret on every participating dashboard, at least 32 characters. Share privately; do not put it in Git.
- **Network:** either the same Wi-Fi/LAN, or the same authorized ZeroTier network.
- **Code version:** Anshul must push the receiver fix before teammates clone/update. Everyone should use that version.

If using ZeroTier, install it from https://www.zerotier.com/download/, join the network ID Anshul provides, and wait for him to authorize your device. Use his ZeroTier address for the broker. Official setup: https://docs.zerotier.com/start/.

**Host prerequisite:** Anshul must configure Kafka's published port and advertised listener to use the reachable Windows address, permit TCP 9092 from teammates through Windows Firewall, and create `fcl.weight-files.v1`. The earlier `127.0.0.1:9092` Docker binding only supports local testing. Completing the steps below cannot fix a host that still advertises `localhost`. Keep this broker on the team network; HMAC verifies files but does not encrypt them.

Teammates need Python and Git. They do not need Docker, Java, PyTorch, or training datasets. Python 3.12 is the suggested version for these instructions.

## 2. First-time setup — macOS

Install Python 3.12 from https://www.python.org/downloads/macos/ if needed. Open Terminal and check:

```bash
python3.12 --version
git --version
```

If macOS asks to install Command Line Tools for Git, finish that installation, then continue. Run:

```bash
mkdir -p ~/Projects
cd ~/Projects
git clone https://github.com/siaa1308/Capstone.git
cd Capstone
python3.12 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r streaming/requirements.txt
./.venv/bin/python -c "import confluent_kafka; print('Kafka client:', confluent_kafka.__version__)"
```

If you already cloned the project, use your existing folder instead of cloning again. After saving/committing any local edits, update with `git pull --ff-only` and install the streaming requirements again.

## 3. First-time setup — Windows teammate

Install Python 3.12 from https://www.python.org/downloads/windows/ and Git from https://git-scm.com/downloads/win if needed. Open PowerShell:

```powershell
py -3.12 --version
git --version
New-Item -ItemType Directory -Force "$HOME\Projects" | Out-Null
Set-Location "$HOME\Projects"
git clone https://github.com/siaa1308/Capstone.git
Set-Location Capstone
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r streaming\requirements.txt
.\.venv\Scripts\python.exe -c "import confluent_kafka; print('Kafka client:', confluent_kafka.__version__)"
```

These commands use the virtual environment directly, so PowerShell activation permissions are not needed. If you already have a checkout, use it and update with `git pull --ff-only` after saving/committing local edits.

## 4. Every session — connect and launch

Join the team network first. The commands below prompt for your broker and secret, so you do not need to edit a command. Paste only the secret when prompted; it will be hidden.

### macOS Terminal

```bash
cd ~/Projects/Capstone
export FCL_BROKER="$(./.venv/bin/python -c 'print(input("Kafka broker (host:9092): ").strip())')"
./.venv/bin/python -c 'import os; from confluent_kafka.admin import AdminClient; m=AdminClient({"bootstrap.servers":os.environ["FCL_BROKER"]}).list_topics(timeout=10); t=m.topics.get("fcl.weight-files.v1"); assert t is not None and t.error is None, "Missing/unavailable file-transfer topic"; print("Kafka ready:", os.environ["FCL_BROKER"])'
export FCL_TRANSFER_SECRET="$(./.venv/bin/python -c 'import getpass; print(getpass.getpass("Shared secret: "))')"
./.venv/bin/python -m streaming.app.dashboard
```

### Windows PowerShell

```powershell
Set-Location "$HOME\Projects\Capstone"
$env:FCL_BROKER = Read-Host 'Kafka broker (host:9092)'
.\.venv\Scripts\python.exe -c 'import os; from confluent_kafka.admin import AdminClient; m=AdminClient({"bootstrap.servers":os.environ["FCL_BROKER"]}).list_topics(timeout=10); t=m.topics.get("fcl.weight-files.v1"); assert t is not None and t.error is None, "Missing/unavailable file-transfer topic"; print("Kafka ready:", os.environ["FCL_BROKER"])'
$env:FCL_TRANSFER_SECRET = .\.venv\Scripts\python.exe -c 'import getpass; print(getpass.getpass("Shared secret: "))'
.\.venv\Scripts\python.exe -m streaming.app.dashboard
```

Use your actual checkout path if different. If the connection check fails, resolve it before transferring. A successful check tests Kafka metadata access, not the shared secret or end-to-end delivery.

Open **http://127.0.0.1:8765** in your own browser. Keep Terminal/PowerShell running. Each laptop opens its own dashboard, not the other person's dashboard. Enter the broker again in the dashboard; `FCL_BROKER` above is just for the connectivity check.

## 5. First transfer — Windows to Mac

Agree on a new transfer ID for each attempt, such as `team-small-001`. Enter these values on BOTH dashboards:

| Field | Value |
| --- | --- |
| Kafka broker | The broker address Anshul provided, e.g. `10.0.0.5:9092` |
| Transfer ID | `team-small-001` — replace for every new attempt |
| Sender ID | `windows` |
| Recipient ID | `mac` |

1. Mac teammate selects **Receive weight file**, then **Start transfer**.
2. Windows sender selects **Send weight file**, chooses a small file, then **Start transfer**.
3. Start both within two minutes. The receiver times out after two minutes.
4. Sender should show **Published**. Receiver should show **Verified**.
5. Compare the SHA-256 shown on both dashboards.
6. Receiver clicks **Download verified file** and checks the downloaded hash below.

Sender/recipient IDs describe the direction and must match on both dashboards. The receiver still enters `windows` as Sender ID for this transfer.

**Published confirms broker delivery only. Verified confirms the receiver saved the checked file.** The sender does not receive an automatic delivery receipt yet.

### Check the downloaded file

On macOS, run this and paste the downloaded file's full path when prompted (without surrounding quotes):

```bash
./.venv/bin/python -c 'import hashlib; from pathlib import Path; p=Path(input("Downloaded file path: ").strip()).expanduser(); print(hashlib.sha256(p.read_bytes()).hexdigest())'
```

On Windows, run:

```powershell
Get-FileHash -LiteralPath (Read-Host 'Downloaded file full path, without quotes') -Algorithm SHA256
```

The downloaded hash must match both dashboards and the source file. Downloads use a `.weights` extension; keep track of the original file type separately.

## 6. Repeat with 2 MB, then reverse direction

Generate a 2 MB file on the sending machine, from the repository folder.

macOS:

```bash
./.venv/bin/python -c 'from pathlib import Path; import secrets,hashlib; p=Path("streaming/.local/team-2mb.bin"); p.parent.mkdir(parents=True,exist_ok=True); data=secrets.token_bytes(2_000_000); p.write_bytes(data); print(p.resolve()); print("SHA-256:",hashlib.sha256(data).hexdigest())'
```

Windows:

```powershell
.\.venv\Scripts\python.exe -c 'from pathlib import Path; import secrets,hashlib; p=Path("streaming/.local/team-2mb.bin"); p.parent.mkdir(parents=True,exist_ok=True); data=secrets.token_bytes(2_000_000); p.write_bytes(data); print(p.resolve()); print("SHA-256:",hashlib.sha256(data).hexdigest())'
```

Select that file and repeat section 5 with a new transfer ID, e.g. `team-2mb-001`. Confirm **2,000,000 bytes**, matching hashes, and a verified download.

Then test Mac to Windows: change Sender ID to `mac` and Recipient ID to `windows` on BOTH dashboards. Windows receives first; Mac sends. Use another new transfer ID. Kafka stays on Windows in both directions.

Do not use `streaming.test_local_transfer` for the teammate test: that script starts both endpoints on the same laptop.

## 7. Stop and return later

Press **Ctrl+C** in the dashboard terminal. To launch next time, repeat section 4. History and managed files remain under ignored `streaming/.local/transfers`. Uploaded files are retained; automatic cleanup and interrupted-transfer resume are not implemented.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `python3.12` / `py -3.12` missing | Install Python 3.12, then reopen the terminal. |
| Kafka package installation fails | Confirm the Python version; send Anshul the complete pip error. |
| Connection refused / Kafka check times out | Confirm Docker/Kafka is running, broker address, network authorization, Windows firewall, and advertised listener. `localhost` on the Mac refers to the Mac. |
| Missing file-transfer topic | Ask Anshul to create `fcl.weight-files.v1` on the selected broker. |
| Secret prerequisite fails | Enter the agreed secret again in section 4; it needs at least 32 characters. Restart the dashboard after changing it. |
| Sender Published; receiver Failed | Compare secrets, update to the pushed receiver fix, and retry with a new transfer ID. Send both transfer details to Anshul. |
| Receiver waits without progress | All four fields must match. Confirm both starts occurred within two minutes. |
| Dashboard port in use | Reuse the already running dashboard, or stop it with Ctrl+C before launching again. |
| Another process owns the state directory | Stop the other dashboard using that directory; do not delete its lock/state while it is running. |
| Generic transfer failure | Record both statuses, terminal output, transfer ID, size, and broker; share with Anshul without sharing the secret. |

Only one transfer runs at a time per dashboard; files must be nonempty and no larger than 100 MB. Cancellation is local and does not remove already published Kafka records. Use unique transfer IDs to avoid picking up retained files from earlier attempts.

## Record the result

For each direction, record Windows/macOS versions, Mac CPU type, broker, transfer ID, source size/hash, sender status, receiver status, and downloaded hash. Cross-platform testing is complete when both directions pass for small and 2 MB files. Never include the shared secret in screenshots, logs, or commits.
