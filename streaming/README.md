# Current integrated dashboard

The dashboard now uses the final three-member adaptive ensemble for training, validation replay and local explanations. Start with the [current project README](../README.md), [implementation guide](../docs/IMPLEMENTATION_GUIDE.md) and [final review checklist](../docs/FINAL_REVIEW.md).

The material below is preserved development history. Statements about single-model training, sample-weighted federation, missing browser integration or an unchanged model connection describe older versions and are superseded by the current guides. Transfer protocol details remain useful where unchanged.

---

# Model-weight transfer dashboard

Current work focuses on moving weight files, not running model training. The existing
training supervisor remains available separately; the dashboard never calls it.

## Client Overview and Local Data & Training

Overview saves a bank label for this laptop and shows connection-check results,
the explicitly selected local checkpoint version/hash, last completed local training
time, and the latest completed local validation metrics. If there is no local run,
it displays the bank's saved frozen September 2025 research results, clearly labeled.
The FedAvg seed-42 reference checkpoint is separate from the selected local model.

To demonstrate the local client workflow:
1. Save the bank on Overview.
2. Open Local Data & Training. Connect the prepared dataset root (the included
   data/final_temporal_dataset is the default). This is a folder connection;
   arbitrary CSV upload and raw-to-graph conversion are not implemented.
3. Click Check data quality. Checks cover required files/features, label joins,
   unique IDs, endpoints, finite features, both label classes and chronological
   training/validation separation. Missing feature values are counted and imputed
   by the training-only encoder; entirely missing columns are rejected.
4. Choose 1-25 epochs and click Train locally. A separate CPU process runs the
   existing causal Temporal GraphSAGE model with validation-only evaluation.
   Progress, loss, validation PR-AUC, worker logs and history are shown. A one-epoch
   run checks operation but is not expected to match the final research model.
5. Click Use this model on a completed run. Hash verification precedes selection;
   Overview then shows its version. This registers a checkpoint for later scoring
   integration; it does not start a transaction monitoring service.

Raw data stays on this laptop. This tab never calls Kafka or shared feature fitting.
Only the selected bank's training and validation files are read. September test
files and frozen research artifacts are not modified. The dataset fingerprint is
checked again after training; changing data during a run invalidates the result.
Training does not resume automatically after interruption. Cancellation is observed
between training/scoring batches and job phases; data loading/checks may delay it.
Closing the dashboard requests cancellation and terminates its child if necessary.
A worker-held OS lock prevents another training worker in the same state folder.

Jobs/checkpoints, selected models and logs persist below the ignored dashboard
state directory's local-training/. On reload, the bank's recent dataset path and
history remain available. Dependencies are the root requirements.txt, installed in
the same Python environment as the dashboard. Windows/macOS use the existing launcher;
this client training workflow has been verified on Windows, not natively on macOS.

## Federated Collaboration tab

The tab supervises one real bank worker or coordinator per laptop. The same
broker, fresh run ID, bank roster, rounds, epochs, timeout and privately shared
secret must be used across participants. The default roster is Key Bank (bank-1),
Wells Fargo (bank-2), JPMorgan Chase (bank-3). Dataset paths stay local.

1. Save the client bank on Overview. In Federated Collaboration choose Bank/client
   on bank laptops or Central coordinator on the coordinator laptop.
2. Configure the matching team setup. Coordinator clicks Prepare topics once;
   fcl.collaboration.global.v1 and fcl.collaboration.updates.v1 each require one
   partition. Broker provisioning/ZeroTier/firewall setup remain external.
3. Everyone clicks Check local readiness. This confirms local dependencies and
   broker/topic access, not remote readiness. Compare the displayed schema hash.
4. Enter the same secret (32+ characters), start bank workers, then start central.
   The password field is cleared on start. Secrets are inherited only in process
   environment and never saved in the setup, database, or API responses.
5. Central broadcasts a common seeded model. Banks train their own transaction
   graph, send signed updates, and wait for the signed aggregate. Central waits for
   every configured bank, validates update schema/base/hash/tensors, performs
   sample-weighted FedAvg, atomically saves, and publishes the aggregate.
6. Each bank verifies the aggregate, loads it, and atomically saves weights and a
   manifest/commit record. Use shared model selects a hash-verified checkpoint for
   Overview and later scoring integration. It does not evaluate that model.

The fixed JSON encoder contract was exported from the public simulated reference
training data with scripts/export_federation_schema.py. Workers never fit schemas
on other banks' data. Central needs the schema file, not bank transactions. Banks
load only their own training split; validation/test data and paper artifacts are
not touched by federation. A configuration/schema mismatch cannot pass the tensor
and signed metadata checks. Retained traffic for other run IDs is ignored before
HMAC validation; every accepted current-run message still requires valid HMAC.

The participant table shows only locally observed evidence. Banks do not infer
other banks are online. Coordinator update verified means an actual validated
update, not a shared-model delivery receipt. Coordinator Completed means aggregation
and broker publication completed. Bank Completed includes verified shared-model
receipt for every configured round. The coordinator has no final recipient receipt
collector yet; check bank dashboards to confirm all deliveries.

Stop after this round and Cancel local run affect only this laptop. Stop is
acknowledged at the next round boundary; a final round can finish Completed first.
Cancellation is checked between training batches, publication/wait phases and
checkpoint boundaries. Already published messages cannot be retracted. Keep the
same state folder to retain runs/events/checkpoints. Workers retain their OS lock
if the dashboard restarts; dashboard controls reconnect to persistent run state.
There is no interrupted-round resume: coordinate a NEW run ID after a failed run.

Manual Weight transfers are linked and summarized in this tab, with their actual
Published/Delivered/Verified statuses. These manual files do not start federation.
Tab 2 locally selected checkpoints are not automatically imported: all federation
participants start from the same initialization and fixed encoder contract.
This sample-weighted temporal training workflow is separate from the paper's
frozen equal-client continual/replay model; its reported scores do not apply here.

Acceptance check (real PyTorch, actual prepared training data, real Kafka, local
processes for all three banks and central):

```powershell
.\.venv\Scripts\python.exe -m streaming.test_federation --broker 10.30.127.124:9092
```

The check validates two rounds, three accepted updates per round, byte-identical
returned checkpoints on all banks, and shared-model selection. Evidence stays under
ignored streaming/.local/accept-*. It is a same-machine transport/training check;
Windows/macOS cross-laptop networking still requires teammate acceptance.

## Launch with saved setup

Open Start-Weights-Windows.cmd on Windows. On macOS, run chmod +x Start-Weights-macOS.command once, then open it (or use bash Start-Weights-macOS.command). Native macOS verification is pending.

The root launch_weights.py bootstraps a missing project .venv. The app launcher checks local storage and Kafka dependencies, offers installation if needed, prompts for the shared secret, and opens the browser after binding the server. --check-only performs local checks without prompts/install/server startup; --no-browser suppresses browser opening. Existing dashboard locks or occupied ports produce an actionable error rather than replacing running processes.

Save setup persists only broker, mode, sender and recipient in the current state directory's settings.json. Writes are atomic; invalid or corrupted settings fall back to manual entry with a warning. Secrets, transfer IDs and file selections are excluded. The settings API has the same session/origin protection as other mutations. Fresh transfer IDs are generated on every page load. Saved settings do not prove connectivity: use Check connection each session.

The launcher does not manage Docker, ZeroTier membership or host firewall rules. See instructions.md for team startup and prerequisites.

## Launch locally

From the repository root in PowerShell, with your virtual environment active:

```powershell
python -m streaming.app.dashboard
```

Open http://127.0.0.1:8765. The dashboard and history work using only Python's standard
library. No package download is necessary to inspect the UI. Keep the terminal running.
Use `--port 8766 --state-dir streaming/.local/other` for a separate local instance.
Only one dashboard may own a given state directory.

## Enable actual transfers later

```powershell
python -m pip install -r streaming/requirements.txt
$env:FCL_TRANSFER_SECRET = '<shared random secret of at least 32 characters>'
python -m streaming.app.dashboard
```

Use the same securely shared secret on both machines; do not commit it. PyTorch,
safetensors and training datasets are not required. Provision the Kafka topic
`fcl.weight-files.v1` on a reachable broker, with retention suitable for your files.
Both machines must reach its advertised listeners. Broker provisioning remains a host task. The Check connection button checks metadata/topic access and a signed peer challenge/response. Both participants select their action and matching IDs, click it, and leave their dashboards running; retry the first check if the other responder was not yet started.

Choose send or receive, enter the same transfer ID, sender and recipient on both
sides, and select a file on the sender. Use a unique transfer ID per file. Start the
receiver and sender within two minutes of each other. Published means Kafka delivery;
Verified means the receiver checked HMAC and SHA-256 and saved the file. Updated receivers publish a signed receipt after saving. Updated senders wait up to two minutes after publication and report Delivered only when attempt token, participants, hash and byte count match. A timeout leaves Published explicitly unconfirmed; receipt failure does not remove a verified file. Resend receipt and Check delivery again recover the original signed receipt without retransmitting file chunks. Both participants need the updated code. New transfers preserve a safe original filename and extension in history and browser downloads. Original names are signed metadata, never storage paths. Legacy transfers or unsupported names fall back to the transfer ID with a `.weights` extension.

Files are opaque bytes, limited to 100 MB. They are never deserialized or trained.
Signatures establish shared-secret membership, not independent sender identity or
encryption. Recipient IDs filter delivery logically; they are not Kafka ACLs.

History and files persist under ignored `streaming/.local/transfers`. Uploads are
retained locally, including uploads from failed starts; automatic storage cleanup is
pending. Refreshing the browser does not restart transfers. Interrupted jobs are
marked after application restart; unfinished attempts offer explicit full-file retry with a new shared ID; partial-byte resume is not implemented. Cancel is
local, retains prior evidence, and cannot retract broker messages. Receivers use a
fresh group and replay retained messages to find the requested ID. Late or replayed
files are possible when IDs are reused. No exactly-once delivery claim is made.

The loopback API enforces Host checks and a session token plus same-origin checks
for mutations. It is a local prototype, not an internet-facing service. One local
transfer runs at a time. Receiving is bounded to two minutes; the sender also has a
two-minute deadline. The checklist reports local prerequisites. Check connection separately reports the checked broker/topic and a fresh signed peer response. It is a point-in-time check, not a guarantee of later delivery. Peer responders use the last identity chosen by Check connection until reconfigured or shutdown. Authentication proves shared-secret membership, not independent device identity.

## Explicit retries and restart recovery

History offers Retry with new ID for Failed, Cancelled, Interrupted and unconfirmed Published attempts that have recovery metadata. Coordinate the SAME fresh ID on both dashboards and start receiver first. Retry creates a linked history row and reuses the retained upload only if its hash matches the original. Receiver retries pin an already observed signed hash. Original history is preserved, and locally reused participant/transfer IDs are rejected.

After broker acknowledgment, sender stores its attempt token and publication evidence. Check delivery again reads the original retained signed receipt; Verified receivers can Resend receipt after revalidating the saved file. No file chunks are resent by these recovery actions. Receipt failure preserves Verified files and unconfirmed publication. One local operation runs at a time.

Startup marks active work Interrupted. If an atomic receiver file exists at the final path, it is promoted back to Verified only when its size and hash match recorded signed metadata. Receipt tasks interrupted after verification retain the download. Nothing automatically retries at startup; byte-level partial resume and automatic file retries are deferred. Legacy jobs without broker/upload/hash/token metadata use the manual new-transfer workflow.

```powershell
.\.venv\Scripts\python.exe -m streaming.test_recovery --broker 10.30.127.124:9092
```

This real-Kafka checkpoint check injects initial failure and lost receipt, restarts both local application instances between phases, verifies full retry from the frozen upload and signed receipt recovery without resending chunks, and compares final downloaded bytes/hash. Original checkpoint remains unchanged. Multi-laptop and OS power-loss acceptance remain pending.

## Real local checkpoint transfer check

Start Docker Desktop and wait until its engine is running. Reuse the existing
local Kafka container and provision the topic (these commands are for the local
`capstone-kafka` setup):

```powershell
docker start capstone-kafka
docker exec capstone-kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists --topic fcl.weight-files.v1 --partitions 1 --replication-factor 1
.\.venv\Scripts\python.exe -m streaming.test_local_transfer
```

Run from the repository root after installing `streaming/requirements.txt` in
that virtual environment. If the Kafka container does not exist, create it once:

```powershell
docker run -d --name capstone-kafka -p 127.0.0.1:9092:9092 apache/kafka:4.1.2
```

Then provision the topic and run the check above. For a different broker, pass
`--broker host:port`. The script checks Kafka metadata, starts two temporary local
dashboard instances on free ports, reads the existing `artifacts/final_evaluation/corrected_fedavg/seed_42/global_model.pt` checkpoint by default, uploads and transfers its signed chunks through real Kafka, downloads the
verified result, and compares the bytes, hashes, and dashboard byte counts.
It uses a temporary shared secret without changing your saved configuration.
Existing dashboard instances can remain open.

The script also checks signed peer challenges in both directions and requires sender Delivered. A successful run prints `PASS` and saves source, downloaded file, transfer history,
and `result.json` under ignored `streaming/.local/local-checkpoint-*` (or `local-synthetic-*`). It stops its own
dashboards afterward and leaves Kafka running. Failure exits with a nonzero code;
local state remains available for diagnosis. Each run uses a unique transfer ID.
This verifies local transport only; teammate networking and failure recovery
still require separate checks.

To use another existing checkpoint, pass `--file path/to/model.pt`. The source is never loaded as a model or modified; the test compares its final SHA-256 again. Missing/empty files and Git LFS pointers fail rather than silently generating dummy bytes. Use `--synthetic` only for a separate 2 MB random-byte stress check.

The checkpoint-backed check passed on 21 October: 976,865 bytes in two chunks, signed peer checks in both directions, sender Delivered, receiver Verified, original filename retained, and byte-identical downloaded checkpoint. Cross-laptop verification of this version remains pending.

```powershell
.\.venv\Scripts\python.exe -m streaming.test_local_transfer --broker 10.30.127.124:9092
.\.venv\Scripts\python.exe -m streaming.test_local_transfer --broker 10.30.127.124:9092 --file artifacts/final_evaluation/local/seed_42/Key_Bank_causal_temporal_graphsage.pt
```

## Validation

```powershell
python -m unittest discover -s tests/streaming -v
```

Transfer tests use Kafka doubles for signed, duplicate and out-of-order chunks,
wrong signatures, cancellation, durable history and HTTP session protection. The receipt/peer implementation passed a real local Kafka 2 MB integration run on 21 October 2026, including verified downloaded bytes. Cross-laptop validation of these new features and large-file performance remain pending. Earlier small-file Windows-to-Mac transfers used the previous implementation.

---

# Training dashboard backend â€” first implementation

This directory provides a process controller and persistent status for the existing
federation pipeline. It does not yet provide a browser dashboard, Docker packaging,
platform launchers, remote readiness/control messages, or automatic training resume.

## Implemented

- `RunController.start` launches only the central or bank entry point in a child
  Python process with an allowlisted configuration snapshot. Secrets remain in the
  environment; they are not copied into configuration snapshots or SQLite events.
- An OS lock held by the child prevents simultaneous supervised jobs sharing a
  state directory, including when the parent launcher exits. Use one fixed state
  directory per laptop. Existing direct CLI processes do not participate in this lock.
- SQLite records role, configuration, run outcome, and ordered events. Status
  queries mark orphaned Running records Interrupted only after obtaining the lock.
- Existing aggregator and worker CLIs delegate to callable `run` functions.
  Structured events report initialization, model loading, epoch completion, update
  publication/validation, aggregation, and checkpoint completion. FedAvg and local
  optimizer logic are unchanged.
- Checkpoints use temporary writes, file flush/fsync, atomic replacement, and a
  hash-verified commit marker written after both weights and manifest. Existing or
  partially written rounds cannot be silently overwritten. Filesystem/power-loss
  guarantees still depend on the host; this is not a database/filesystem transaction.

`update_published` means broker delivery, not central acceptance. `update_validated`
currently describes validation in the live aggregator; accepted update payloads are
not yet persisted for resume. A bank's Completed process means it published its
configured updates; only central `round_completed` means an aggregate was saved.

## Developer usage

Use the existing federation dependencies and a valid configuration/dataset. Supply
the same secret environment variables as the existing CLI. The default state folder
is `streaming/.local/`, ignored by Git. Configuration snapshots contain local paths
and other non-secret settings; treat this folder as local application data.

From the repository root:

```powershell
python -m streaming.app.controller start --role central --config distributed_federation/config.json
python -m streaming.app.controller start --role bank --client-id bank-1 --config distributed_federation/config.json
python -m streaming.app.controller status
python -m streaming.app.controller events --run 1 --after 0
```

Run central and bank commands on their respective laptops. These are temporary
developer entry points; the planned launchers/UI will remove routine terminal use.
The `start` command waits for its child so failures retain a useful exit code;
Python API callers receive a `Popen` handle immediately. Starting a process is not
a readiness confirmation. Events return up to 500 entries; use the last event ID
as `--after` to read subsequent entries. The run argument is the local SQLite record
ID, distinct from the federation configuration's `run_id`.

An already used `(run_id, actor)` cannot be started again in the same state store.
Use a new run ID for a new experiment. Do not erase state to simulate recovery or
reuse output directories. Snapshotting configuration does not freeze dataset or
initial-checkpoint contents: keep them unchanged during a run.

## Validation

```powershell
python -m unittest discover -s tests/streaming -v
```

The standard-library test suite covers cross-process locks, config snapshotting,
durable events, process outcomes, checkpoint corruption and partial-write handling,
and the real aggregator/worker loops with three banks over two rounds. That round
trip uses signed/chunked messages, duplicated deliveries, and the existing FedAvg
function with deterministic scalar doubles and an in-memory broker. Unequal counts
verify weighting; a missing-bank test verifies aggregation does not proceed.

These tests do not execute PyTorch training, tensor compatibility checks, actual
Kafka, or multi-laptop networking. A real dependency-backed integration run remains
an acceptance gate, along with preprocessing equivalence and platform checks.

## Local stop and cancel controls

```powershell
python -m streaming.app.controller stop --run 1
python -m streaming.app.controller cancel --run 1
```

Use the same `--state-dir` as the running process (a global option before the
command). The run number is the local SQLite record ID. Requests are persistent
and idempotent; cancel supersedes stop. Terminal or orphaned runs reject controls.
A request is not an acknowledgment: status stays Running until the worker reaches
a safe boundary and records Stopped or Cancelled. A run that finishes before
observing a request can still be Completed.

Stop finishes the current local round and prevents the next round. Central saves
the aggregate; a bank finishes publishing its update, which does not prove central
acceptance. Cancel is checked while waiting for messages, between training batches,
before aggregation/checkpoint writing, and between publication attempts. Checkpoint
writes already in progress finish atomically at their existing boundaries. Loading,
a batch, aggregation, and the existing broker flush (up to 30 seconds) can delay
acknowledgment. Already queued/published messages cannot be retracted.

These controls affect only the selected supervised process on this laptop. They do
not broadcast commands to other machines. Other participants can keep running or
time out; never display them as stopped based on a local acknowledgment. Authenticated
remote coordination and explicit recovery are still pending. Completed checkpoints
are retained; a stopped/cancelled run cannot simply be restarted with the same ID.

The tests also cover durable request precedence, terminal rejection, acknowledged
outcomes and lock release, publication backpressure cancellation, cancellation while
waiting without aggregation, and three banks stopping after one saved round.

## Next implementation steps

1. Persist frozen initial models and bank updates before committing Kafka offsets;
   implement receipts/outbox and checkpoint reconciliation.
2. Implement explicit resume with original round/seed/configuration identity,
   authenticated readiness, and cooperative stop/cancel handling. Current entry
   points must not be advertised as resumable.
3. Add the local API/dashboard over the controller and event store, then package
   ML dependencies and validate Windows/macOS launchers and real Kafka transport.
