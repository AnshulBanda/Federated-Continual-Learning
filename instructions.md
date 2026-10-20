# Capstone teammate guide: Kafka weight-file transfers

Updated: 21 October 2026.

Application update (local implementation; teammates need the updated commit):
- Check connection now checks Kafka metadata/topic and exchanges a fresh signed peer challenge/response.
- Sender progresses from Published to Delivered after a valid receipt confirms the matching file was saved.
- A real local 2 MB integration check passed with both signed peer checks and delivery receipt. Cross-laptop testing of these NEW features remains pending.
- Both participants must update and restart their dashboards for the new peer checks/receipts. Keep using fresh transfer IDs.

This guide covers setup, daily startup, sending, receiving, verification, and troubleshooting on Windows and macOS. Files travel as bytes; the dashboard does not load models or run training.

## 1. Team settings and current results

| Setting | Current value |
| --- | --- |
| Git repository | https://github.com/siaa1308/Capstone.git |
| Branch | Anshul-feat/training-dashboard |
| ZeroTier network ID | 2873fd00f2339de1 |
| Kafka host | Anshul's Windows laptop |
| Host ZeroTier IP | 10.30.127.124 |
| Broker entered on EVERY dashboard | 10.30.127.124:9092 |
| Team Kafka container | capstone-kafka-team |
| Transfer topic | fcl.weight-files.v1 |
| Dashboard on each laptop | http://127.0.0.1:8765 |
| Shared secret | Get privately from Anshul; never put it in this document or Git |

The broker address depends on the host's ZeroTier IP. If that IP changes, Anshul must update the broker configuration and tell everyone the new address.

Recorded progress:
- Local 2,000,000-byte Kafka transfer passed on 15 October.
- Windows-to-first-Mac small-file transfer passed: test004, 2,663 bytes, Published on Windows and Verified on Mac, with matching dashboard SHA-256 hashes.
- Windows-to-second-Mac small-file transfer was reported working in this session.
- Another Windows teammate reached the broker port, but their subsequent issue remains unresolved. A successful Windows-to-Windows file transfer is not yet recorded.
- Teammate 2 MB transfers, reverse-direction transfers, independent downloaded-file hashes, and failure/recovery tests still need recorded results. Do not treat port connectivity as a completed file-transfer test.

IDs such as windows1, mac1, mac2, and windows2 are agreed labels, not passwords or automatic device discovery.

## 2. Who needs what?

Everyone needs:
- Git, Python 3.12, the project branch above, and its streaming requirements.
- ZeroTier installed, joined to the team network, and authorized.
- The same privately shared transfer secret.
- A terminal left running while their dashboard is in use.

Only Anshul's Kafka host needs Docker Desktop and the Kafka container. Other teammates do not need Docker, Java, PyTorch, model training dependencies, or datasets.

Use PowerShell on Windows and Terminal on macOS. Commands below use the virtual environment directly; activation is unnecessary. Substitute your actual project folder if it differs.

## 3. One-time ZeroTier setup

1. Download ZeroTier One: https://www.zerotier.com/download/
2. Install and open it. Windows uses a system-tray icon; macOS uses a menu-bar icon.
3. Choose Join New Network and enter 2873fd00f2339de1.
4. Send your device/node ID to Anshul privately.
5. Anshul opens https://central.zerotier.com/, selects the team network, matches your device ID, and authorizes it under Members / Member Devices.
6. Confirm a Managed IP is assigned. Anshul should label members by person and device.
7. Keep ZeroTier connected during testing. Keep the network private.

Do not create a separate network for each teammate. Joining is not complete until the device is authorized and assigned an address.

Official guide: https://docs.zerotier.com/quickstart/

## 4. One-time project setup

### macOS

Check Python and Git first:

```bash
python3.12 --version
git --version
```

Install Python 3.12 from https://www.python.org/downloads/macos/ if missing. Complete macOS Command Line Tools installation if Git requests it.

For a NEW checkout:

```bash
mkdir -p ~/Projects
cd ~/Projects
git clone --branch Anshul-feat/training-dashboard --single-branch https://github.com/siaa1308/Capstone.git
cd Capstone
python3.12 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r streaming/requirements.txt
./.venv/bin/python -c "import confluent_kafka; print(confluent_kafka.__version__)"
```

### Windows teammate

Install Python 3.12 from https://www.python.org/downloads/windows/ and Git from https://git-scm.com/downloads/win if missing. Open PowerShell.

For a NEW checkout:

```powershell
py -3.12 --version
git --version
New-Item -ItemType Directory -Force "$HOME\Projects" | Out-Null
Set-Location "$HOME\Projects"
git clone --branch Anshul-feat/training-dashboard --single-branch https://github.com/siaa1308/Capstone.git
Set-Location Capstone
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r streaming\requirements.txt
.\.venv\Scripts\python.exe -c "import confluent_kafka; print(confluent_kafka.__version__)"
```

### Existing checkouts

Use your existing project folder. Check for local changes before updating:

```text
git status --short
git branch --show-current
git log -1 --oneline
```

Save/commit your work before switching branches. Do not discard changes to follow this guide. Once your work is safe:

```text
git fetch origin
git switch Anshul-feat/training-dashboard
git pull --ff-only origin Anshul-feat/training-dashboard
```

If the branch is not present locally, use this instead of the switch command:

```text
git switch --track origin/Anshul-feat/training-dashboard
```

Reinstall streaming/requirements.txt using your platform's virtual-environment Python. Everyone should use the version containing the receiver fix that ignores unrelated retained records before checking their signatures.

## 5. HOST ONLY: start Kafka each session

Anshul opens Docker Desktop and waits for its engine, connects ZeroTier, then runs:

```powershell
docker start capstone-kafka-team
docker ps --filter name=capstone-kafka-team --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker exec capstone-kafka-team /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:29092 --create --if-not-exists --topic fcl.weight-files.v1 --partitions 1 --replication-factor 1
docker exec capstone-kafka-team /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:29092 --describe --topic fcl.weight-files.v1
```

Expect PartitionCount: 1, ReplicationFactor: 1, and an assigned leader. The topic-name metrics warning about periods/underscores is not a transfer failure.

Use capstone-kafka-team for team testing. The old capstone-kafka container was bound to 127.0.0.1 and is not the team broker.

If startup fails:

```powershell
docker logs --tail 60 capstone-kafka-team
```

### Initial broker creation / reference configuration

This was the working team configuration from this session. Run it ONLY if capstone-kafka-team does not already exist. The named volume preserves this broker's data. The older container and volumes are not reused or deleted.

Confirm the host still owns 10.30.127.124 first:

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -like '*ZeroTier*' } | Select-Object InterfaceAlias, IPAddress
```

The following command is deliberately one line. Paste the whole line:

```powershell
docker run -d --name capstone-kafka-team --hostname capstone-kafka-team -p 10.30.127.124:9092:9092 -v capstone-kafka-team-data:/var/lib/kafka/data -e KAFKA_NODE_ID=1 -e KAFKA_PROCESS_ROLES=broker,controller -e KAFKA_LISTENERS=INTERNAL://0.0.0.0:29092,EXTERNAL://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093 -e KAFKA_ADVERTISED_LISTENERS=INTERNAL://localhost:29092,EXTERNAL://10.30.127.124:9092 -e KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=INTERNAL:PLAINTEXT,EXTERNAL:PLAINTEXT,CONTROLLER:PLAINTEXT -e KAFKA_INTER_BROKER_LISTENER_NAME=INTERNAL -e KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER -e KAFKA_CONTROLLER_QUORUM_VOTERS=1@localhost:9093 -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 -e KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR=1 -e KAFKA_TRANSACTION_STATE_LOG_MIN_ISR=1 -e KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS=0 -e KAFKA_LOG_DIRS=/var/lib/kafka/data apache/kafka:4.1.2
```

Wait roughly 20 seconds, then run the topic commands above. Internal administration uses localhost:29092 INSIDE the container. Dashboards use 10.30.127.124:9092.

### Host firewall — one-time setup

Open Start, search PowerShell, right-click Run as administrator, and approve the prompt. Run this only if the rule has not already been created:

```powershell
New-NetFirewallRule -DisplayName "Capstone Kafka via ZeroTier" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 9092 -LocalAddress 10.30.127.124 -Profile Any
```

This allows inbound Kafka traffic addressed to the host's ZeroTier IP. Do not disable the firewall. The interface-alias version failed during this session; use the IP-scoped command above.

Reference for the image settings: https://github.com/apache/kafka/blob/4.1.2/docker/examples/README.md

## 6. EVERYONE: check network and Kafka

### macOS port check

```bash
nc -vz -w 5 10.30.127.124 9092
```

Expect succeeded.

### Windows port check — PowerShell

```powershell
Test-NetConnection 10.30.127.124 -Port 9092
```

Expect TcpTestSucceeded: True. If using Command Prompt instead:

```bat
powershell -Command "Test-NetConnection 10.30.127.124 -Port 9092"
```

A successful TCP test proves the port is reachable, not that the topic, secret, or file transfer works.

### Kafka metadata check — macOS, from the project folder

```bash
./.venv/bin/python -c 'from confluent_kafka.admin import AdminClient; m=AdminClient({"bootstrap.servers":"10.30.127.124:9092"}).list_topics(timeout=15); t=m.topics.get("fcl.weight-files.v1"); assert t is not None and t.error is None, "Transfer topic missing or unavailable"; print("Kafka ready")'
```

### Kafka metadata check — Windows PowerShell, from the project folder

```powershell
.\.venv\Scripts\python.exe -c "from confluent_kafka.admin import AdminClient; m=AdminClient({'bootstrap.servers':'10.30.127.124:9092'}).list_topics(timeout=15); t=m.topics.get('fcl.weight-files.v1'); assert t is not None and t.error is None, 'Transfer topic missing or unavailable'; print('Kafka ready')"
```

Expect Kafka ready. If TCP passes but this fails, inspect the topic and advertised listener; do not assume the secret is responsible because this check does not use it.

## 7. EVERYONE: set the shared secret and launch

Anshul's existing secret is stored locally at:

```text
C:\Users\Anshul Banda\Desktop\Capstone\Capstone\streaming\.local\team-connection-details.txt
```

Anshul can open it with:

```powershell
notepad "C:\Users\Anshul Banda\Desktop\Capstone\Capstone\streaming\.local\team-connection-details.txt"
```

Copy ONLY the single secret-value line. Do not copy its heading, explanatory text, quotes, or blank lines. Share it privately. This secret is separate from the ZeroTier network ID. Do not generate a different secret on each laptop.

### macOS

```bash
cd ~/Projects/Capstone
export FCL_TRANSFER_SECRET="$(./.venv/bin/python -c 'import getpass; print(getpass.getpass())')"
```

At Password:, paste the shared secret and press Enter. Input remains hidden. Before launching, check its length and fingerprint:

```bash
./.venv/bin/python -c 'import os,hashlib; s=os.environ.get("FCL_TRANSFER_SECRET",""); print("Length:",len(s)); print("Fingerprint:",hashlib.sha256(s.encode()).hexdigest()[:16])'
./.venv/bin/python -m streaming.app.dashboard
```

### Windows PowerShell

Anshul uses this folder:

```powershell
Set-Location "C:\Users\Anshul Banda\Desktop\Capstone\Capstone"
```

A teammate using the suggested installation folder uses:

```powershell
Set-Location "$HOME\Projects\Capstone"
```

Then run:

```powershell
$env:FCL_TRANSFER_SECRET = .\.venv\Scripts\python.exe -c "import getpass; print(getpass.getpass())"
```

At Password:, paste the shared secret and press Enter. Check it, then launch:

```powershell
.\.venv\Scripts\python.exe -c "import os,hashlib; s=os.environ.get('FCL_TRANSFER_SECRET',''); print('Length:',len(s)); print('Fingerprint:',hashlib.sha256(s.encode()).hexdigest()[:16])"
.\.venv\Scripts\python.exe -m streaming.app.dashboard
```

Compare fingerprints privately: all participants must have the same length and fingerprint. The secret used successfully in this session was 64 characters; the application's minimum is 32. A previous 129-character Windows value was copied incorrectly and did not match the Mac.

Keep using this same terminal: environment variables are local to the shell session. A new terminal needs the secret set again. If changing the secret while a dashboard is running, press Ctrl+C, set it again, and restart. Another terminal's updated value does not change a running dashboard.

Everyone opens http://127.0.0.1:8765 on THEIR OWN laptop. Keep the terminal open. Refresh the page after restarting. The checklist should show Kafka client installed and Transfer secret configured. The secret check confirms local configuration, not that peers have the same secret.

## 8. First small-file transfer — one teammate at a time

Use a small nonempty file, such as questions.txt. Both dashboards must use identical broker, transfer ID, sender ID, and recipient ID. Type IDs manually if copying causes validation errors.

Choose an UNUSED transfer ID. test004 and test005 belong to earlier attempts; do not reuse them.

| Field | Anshul's Windows dashboard | First Mac dashboard |
| --- | --- | --- |
| Action | Send weight file | Receive weight file |
| Kafka broker | 10.30.127.124:9092 | 10.30.127.124:9092 |
| Transfer ID | smallmac1a | smallmac1a |
| Sender ID | windows1 | windows1 |
| Recipient ID | mac1 | mac1 |

1. Finish or cancel any active local transfer on both laptops.
2. Sender chooses the file.
3. Before transferring, BOTH teammates click **Check connection** with the matching IDs and correct send/receive actions selected. The button starts a local peer responder. If the first check times out before the other person clicks, retry. Keep both dashboards running. Expect broker/topic available and Peer ready. The check does not transfer a file or validate model contents. It proves shared-secret membership under the chosen label, not independent device identity.
4. RECEIVER clicks Start transfer first.
5. SENDER clicks Start transfer within two minutes.
6. Scroll down to Transfer history. Transfer started only means the job was submitted.
7. Sender first shows Published, then Delivered after the signed receipt. Receiver shows Verified. Receipt wait is up to two minutes after publication.
8. Compare source/receiver byte counts and dashboard SHA-256 hashes.
9. Receiver clicks Download verified file and independently checks the downloaded hash below.

For another participant, use these values on BOTH ends:

| Test | Transfer ID example | Sender ID | Recipient ID |
| --- | --- | --- | --- |
| Windows to second Mac | smallmac2a | windows1 | mac2 |
| Windows to other Windows | smallwin2a | windows1 | windows2 |
| First Mac to Windows | backmac1a | mac1 | windows1 |
| Second Mac to Windows | backmac2a | mac2 | windows1 |
| Other Windows to host | backwin2a | windows2 | windows1 |

For every retry, choose a new ID on both ends, such as smallmac1b. Each ID must start with a letter or number, be 1–64 characters, and contain only letters, numbers, dots, underscores, or hyphens. No spaces or smart punctuation.

Sender ID describes the sender even on the receiving dashboard. The reverse direction changes sender/recipient on BOTH screens. Kafka stays on Anshul's Windows laptop in every direction. The first Mac need not run a receiver during the second Mac's test.

## 9. What the statuses mean

| Display | Meaning |
| --- | --- |
| Transfer started | Local job was submitted; delivery is not yet proven |
| Published | Kafka acknowledged all chunks; sender waits up to two minutes for a signed receipt. If no valid receipt arrives, it stays Published with an explicit unconfirmed message |
| Delivered | A signed receipt matched this attempt token, participants, file hash, byte count and saved-file claim |
| Verified | Receiver checked HMAC and SHA-256, reconstructed the file, and saved it |
| Failed | Read the detail and terminal output; do not treat the attempt as delivered |
| Interrupted | Application ended before the transfer finished; automatic resume is absent |
| Check connection | Reports broker/topic result separately from signed peer result, with the checked address and time. Rerun after changing settings |

Older versions show receiver verification is not yet confirmed indefinitely. Updated versions wait for a signed receipt. If the receiver is old, closed, or cannot publish its receipt, the file may be Verified there while the sender remains Published and unconfirmed. A failed receipt does not delete the verified file. Receipt retries and automatic recovery are not implemented. Cancellation cannot undo a saved file.

A .txt file is valid for transport testing. Files remain opaque bytes; successful transport does not prove model compatibility or training correctness. New transfers preserve the original safe filename and extension, such as global_model.pt. Legacy transfers or unsupported names use the transfer ID plus .weights.

## 10. Independently verify the downloaded file

The downloaded hash must match the original source AND both dashboard hashes.

### Windows — source or downloaded file

```powershell
Get-FileHash -LiteralPath (Read-Host 'Full file path without surrounding quotes') -Algorithm SHA256
```

### macOS — source or downloaded file

```bash
shasum -a 256 "/full/path/to/file"
```

Replace the quoted path with the actual source/download location. For an example transfer ID smallmac1a, if saved there:

```bash
shasum -a 256 ~/Downloads/smallmac1a.weights
```

The browser may rename duplicate downloads or use another folder. Check the actual saved name rather than assuming it.

## 11. Use actual model checkpoints for ongoing tests

Use existing weight files for normal application acceptance tests from now on. On Anshul's laptop, select this file in the sending dashboard:

```text
C:\Users\Anshul Banda\Desktop\Capstone\Capstone\artifacts\final_evaluation\corrected_fedavg\seed_42\global_model.pt
```

It is 976,865 bytes (two transfer chunks). The local automated checkpoint check passed with signed peer responses, Delivered/Verified, original filename, and matching downloaded bytes/hash. Original checkpoint was unchanged. This does not prove the model can train or run inference; the application only transfers it.

Use a new transfer ID such as checkpointmac1a and follow section 8. The receiver downloads global_model.pt; use its actual browser save path for the hash check. For reverse testing, the teammate may send back that downloaded checkpoint with a NEW transfer ID and swapped participants.

The automated local check now uses this checkpoint by default:

```powershell
.\.venv\Scripts\python.exe -m streaming.test_local_transfer --broker 10.30.127.124:9092
```

To select a different checkpoint:

```powershell
.\.venv\Scripts\python.exe -m streaming.test_local_transfer --broker 10.30.127.124:9092 --file artifacts/final_evaluation/local/seed_42/Key_Bank_causal_temporal_graphsage.pt
```

The automated check runs two dashboards on one laptop. It complements teammate tests, not replaces them. Missing checkpoint or Git LFS pointer is an error; it will not silently use random bytes.

### Optional additional stress test — synthetic 2 MB

These generated bytes are an additional boundary/chunking check, not model weights. Use actual checkpoints for the routine workflow.


Generate a file on the sending laptop from its project folder.

### Windows PowerShell

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; import secrets,hashlib; p=Path('streaming/.local/team-2mb.bin'); p.parent.mkdir(parents=True,exist_ok=True); data=secrets.token_bytes(2_000_000); p.write_bytes(data); print(p.resolve()); print('Bytes:',len(data)); print('SHA-256:',hashlib.sha256(data).hexdigest())"
```

### macOS

```bash
./.venv/bin/python -c 'from pathlib import Path; import secrets,hashlib; p=Path("streaming/.local/team-2mb.bin"); p.parent.mkdir(parents=True,exist_ok=True); data=secrets.token_bytes(2_000_000); p.write_bytes(data); print(p.resolve()); print("Bytes:",len(data)); print("SHA-256:",hashlib.sha256(data).hexdigest())'
```

Choose streaming/.local/team-2mb.bin in the sending dashboard. Use a fresh ID, for example largemac1a. Repeat the receiver-first procedure. Expect exactly 2,000,000 bytes, Delivered on the sender, Verified on the receiver, matching dashboard hashes, and a matching downloaded-file hash.

Do not regenerate the source during a transfer; regeneration creates different bytes. Repeat for each teammate, then reverse direction with new IDs. The local streaming.test_local_transfer script starts both endpoints on ONE laptop and does not replace teammate testing.

## 12. New connection-check and receipt troubleshooting

- **Broker ready, peer unconfirmed:** the broker/topic check passed but no valid peer response arrived. Both people must select their correct send/receive action, enter matching participant IDs and secret, click Check connection, and leave dashboards running. Then retry. A completed check describes that moment only.
- **Check running:** wait for the current check to finish (up to roughly 25 seconds). One check runs at a time per dashboard.
- **Peer listener unavailable:** check Kafka access and retry. Restart the dashboard if its settings cannot be changed while an old listener is stopping.
- **Receiver Verified; sender stays Published:** file is saved, but delivery is unconfirmed at the sender. Update both dashboards; inspect the receiver's receipt-publication detail. Wait up to two minutes. Check hashes before deciding whether to resend; use a new transfer ID for a retry.
- **Sender Delivered:** the current attempt received a valid signed receipt. Shared-secret holders can use team labels; this is not independent sender authentication.
- **Settings changed:** run Check connection again. A peer responder uses the last identity configured by that button until reconfigured or the dashboard is stopped.
- **Old dashboard wording:** restart the updated application and refresh the browser. Everyone needs the same new code version.

### Troubleshooting from this session

| Symptom | Action |
| --- | --- |
| Access is denied when creating firewall rule | Run PowerShell as Administrator; a system32 prompt alone is not proof of elevation |
| Firewall positional-parameter error | Use the one-line command without backticks. A PowerShell backtick is only a continuation at the END of a line |
| Firewall interface not found | Use the LocalAddress rule in section 5; omit the interface-alias filter |
| Broker address rejected | Enter exactly 10.30.127.124:9092; 10.30.127124:9092 is missing a dot |
| ID validation error / garbled 1–64 message | Clear all three ID fields and type simple ASCII IDs manually; invisible spaces can fail validation |
| Python SyntaxError near Shared | Use the corrected PowerShell command in section 7; avoid nested double quotes in Python code |
| Secret checklist unchecked | Set FCL_TRANSFER_SECRET in the SAME terminal before launch; ensure at least 32 characters; restart |
| Receiver ValueError at zero bytes | Compare secret lengths/fingerprints first; confirm current code and matching IDs. The error is generic and does not alone identify the cause |
| Fingerprints differ | Re-enter only the same secret line on both laptops, restart both dashboards, and use a new transfer ID |
| Receiver waits with no progress | Compare all four fields, confirm receiver started first, and send within two minutes |
| Sender Published but receiver Failed | Publication does not prove receipt. Check secret, IDs, receiver version and logs; retain both results |
| Coordinator load in progress: retrying | Kafka can retry while internal coordination initializes. Check final status. If persistent, inspect broker logs and topic readiness |
| TCP test fails | Check ZeroTier authorization/IPs, host awake, Docker engine, team container status and firewall rule |
| TCP succeeds, Kafka check fails | Verify external advertised address and topic. Port access alone is insufficient |
| Missing Python or .venv | Complete section 4 from the correct project folder |
| ModuleNotFoundError: confluent_kafka | Install streaming/requirements.txt with the SAME .venv Python used to launch |
| Port 8765 already in use | Reuse the running local dashboard or stop it before relaunching |
| State directory already owned | Stop the other dashboard owning it; do not delete active lock/state files |
| Old Failed entries remain | History is persistent; judge the current unique transfer ID |
| One Windows teammate still fails | Capture their exact step, terminal error, port result, Git version, and transfer status; this issue remains open |

Only one transfer runs at a time per dashboard. Files must be nonempty and at most 100,000,000 bytes. Receive/send deadlines are two minutes. Cancel is local and cannot retract Kafka records. Reusing IDs can pick up retained messages. Automatic retries, interrupted-transfer resume, and storage cleanup remain unfinished. Peer checks are opt-in through Check connection; rerun them after settings/network changes. New receipt and peer messages use the existing file topic, so no additional topic provisioning is needed.

If a problem persists, collect:
- OS version (and Mac CPU type), branch and git log -1 --oneline.
- Broker and participant labels, unique transfer ID, file size.
- Both transfer statuses and exact errors; relevant terminal output.
- Secret length/fingerprint privately if diagnosing mismatch; NEVER the secret itself.

## 13. Stop and return next session

Everyone: press Ctrl+C in the dashboard terminal. Do not close terminals during an active transfer.

Host may stop the team broker after everyone finishes:

```powershell
docker stop capstone-kafka-team
```

Next session:
1. Host starts Docker Desktop and connects ZeroTier.
2. Host starts capstone-kafka-team using section 5.
3. Everyone connects ZeroTier and checks the port/Kafka using section 6.
4. Everyone sets the shared secret in their current terminal and launches using section 7.
5. Open each local dashboard and choose NEW transfer IDs.

Do not rerun docker run for an existing container, delete Kafka volumes, or generate new credentials simply to restart. Dashboard history and files remain under ignored streaming/.local/transfers. Uploaded files are retained.

## 14. Acceptance record

Complete one row per attempt; keep secrets out of evidence.

| Date | Direction / devices | Transfer ID | Source bytes + SHA-256 | Sender status | Receiver status | Download SHA-256 | Pass / issue |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 20–21 Oct 2026 session | windows1 to mac1 | test004 | 2,663; matching dashboard hashes recorded in chat | Published | Verified | Not independently recorded | Transport passed; download hash pending |
| 20–21 Oct 2026 session | windows1 to mac2 | test005 planned; confirm actual ID | Small file; details to record | Reported working | Reported working | Not independently recorded | User reported success; capture evidence |
| Pending | windows1 to windows2 | New ID | Record | Record | Record | Record | Windows issue unresolved |

For EACH teammate, complete small-file and 2 MB tests in BOTH directions, including independent downloaded hashes. Then separately test cancellation, mismatched credentials, broker/network loss, and restart behavior. Multi-laptop acceptance is not complete until these results are recorded.
