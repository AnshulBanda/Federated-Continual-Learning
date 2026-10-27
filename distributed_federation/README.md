# Distributed federation components

For the planned browser-operated training workflow, start with the
[federated training and streaming blueprint](../docs/STREAMING_BLUEPRINT.md).
For the implemented process controller, persistent events, developer commands,
tests, and current limitations, see the [backend guide](../streaming/README.md).
**The browser workflow is implemented in the Federated Collaboration tab.**
Use the Windows/macOS dashboard launcher, configure Bank/client or Central
coordinator, compare the same fresh run ID/roster/settings, check local readiness,
and start all banks before central. See streaming/README.md for the current guide.

The browser configuration uses artifacts/dp_level3_secagg/feature_schema.json, a JSON-only preprocessing
contract exported once from the public simulated reference training data. Banks
read only their own training graph at runtime; central reads no bank transactions.
Every round returns the signed aggregate to each bank for verification and atomic
checkpoint saving. The final browser path enforces Level-3 distributed DP and
Secure Aggregation, the approved frozen warm checkpoint, three distinct banks,
equal weights, one release and decoder-only adaptation. See the backend guide
for exact settings, privacy scope and real Kafka acceptance evidence.

Legacy CLI configs without feature_schema retain the older shared-data preparation
behavior. Use the browser-generated configuration for the bank-local workflow.
Do not run legacy configs while claiming that clients need only their own data.

In the final private mode, banks clip and noise their decoder deltas before
fixed-point encoding and pair masking. Kafka carries authenticated key exchange
and masked bank contributions. Central receives no individual clean model update
or clean aggregate; it reconstructs only the noisy equal aggregate after complete
cohort mask cancellation. Missing participants abort with no plaintext fallback.
Explicit lower-level research configurations retain their existing modes.

## Components

- `common/protocol.py`: signed chunk envelopes and hash-verified reconstruction.
- `central/aggregator.py`: broadcast, update validation, aggregation, and checkpoints.
- `client/bank_worker.py`: model receipt, local training, and update publication.
- `common/model_runtime.py`: preprocessing, model validation, training, and FedAvg.
- `common/events.py`: optional structured events for supervised execution.
- `common/checkpoints.py`: checkpoint writes and hash-verified commit markers.
- `common/kafka_io.py`: Kafka producer/consumer helpers.
- `tools/weight_smoke_test.py`: existing central-to-bank byte-transfer test without
  model loading. It verifies bytes in memory and prints success; it does not save
  the received file or return a completion receipt to central.
- `kafka/compose.yaml`: existing Kafka deployment, used as an implementation reference.

The backend integration lives in `streaming/`. Readiness announcements and signed
shared-model returns are available in the browser workflow. Coordinator-side
final recipient receipts, durable update resume, and native macOS acceptance remain
unfinished. A coordinator Completed status proves aggregation/publication, not
receipt by every bank; each bank records its own verified receipt.
See the blueprint for the full scope and acceptance criteria.

## Earlier operational documentation

The seven migration-only setup guides, quickstart, teammate guide, and central
checklist have been removed. Their substantive earlier contents remain in
[Git history](https://github.com/siaa1308/Capstone/tree/1294588780ddef3512910accce3b0fc48ee655f4/distributed_federation).
Those documents mixed VM administration, weight transfer, and model training.

For the existing project context, see the [project README](../README.md).
Research and dataset documentation remain separate from this application work.
