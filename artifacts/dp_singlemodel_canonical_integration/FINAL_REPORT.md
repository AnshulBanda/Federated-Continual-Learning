# Canonical DP integration — ready for human verification

Canonical branch: philip-dp-secagg-ddp.
Main used: 1760f95f19b3411c3cb5ae3bcef356f8f7d23c60.
Successful local repair: f1e7c5ddc0673efd7e7b7c62cccce03daef879e1.

The canonical branch was fast-forwarded from 3ba2fd2 to the successful repair.
There were no conflicts and no computational code changes. The integration
commit adds only audit evidence and four explicit negative regression subtests
for nonprivate mode, C=6.5, server lr=1 and ensemble initialization. The final
commit/remote SHA and ahead/behind counts are verified after push and reported
in the task response, avoiding self-referential tracked Git records.

## Exact private configuration

One CausalTemporalGraphSAGE, seed-42 frozen warm checkpoint
SHA256 d650af6959d1da46888f30fb79bbfd888a6ec20743d14d447ea078dc351536f5.
No private ModuleDict or probability averaging. Seeds52/62 remain separate
research continuation seeds. Decoder65793 coordinates adapt; backbone176768
coordinates remain frozen.

training_protocol=adaptive_single; three banks; four real communication/DP
releases; three local epochs per phase; lr=.0003; wd=.0001; batch1024;
negative_ratio20; risk_context replay2000; equal aggregation; private_subset=decoder.
Privacy is distributed_dp, C=.875, m=.30, delta1e-6, production entropy,
expected_clients=min_noise_contributors=3; fixed-point scale16777216; mandatory
full-cohort SecAgg. Server is noisy-only FedAvg with lr=.1. Return aggregate=true.
The actual full config remains in ../dp_singlemodel_r4e3/GENERATED_CONFIG.json.

Four-release rho=66.66666666666667, epsilon127.36375184207253 at delta1e-6,
using the unchanged conservative encoded-share accountant. The guarantee remains
conditional on nonprivate warm weights, public preprocessing and fixed public
calibration. Research calibration/validation disclosures are not privatized.
All reserved runs/releases compose; deleting/rolling back ledgers invalidates scope.

## Independently traced path

Browser fedAction → POST /api/collaboration/start → Collaboration.start → explicit
pinned generated config → RunController validation/allowlisted snapshot → runner
with forced --operational-final validation → bank_worker/aggregator wrappers →
privacy.transport → unchanged common/kafka_io.py → configured Kafka broker.

Bank: receive global single model → complete ephemeral key roster → adaptive
local training → decoder delta → one global L2 clip → independent production
Gaussian share → fixed point → X25519/HKDF-SHA256/ChaCha20 pair mask → signed,
chunked masked_client_update. Coordinator accepts exactly three masked rings,
cancels pair masks, recovers only the noisy equal aggregate, applies FedAvg lr.1,
reconstructs the decoder with frozen backbone, saves and returns the model.
No clean individual state or clean aggregate is reconstructed in private mode.
Plaintext temporal harmonization remains nonprivate research only.

common/kafka_io.py is byte-for-byte identical to origin/main. No new transport
change was made. Bootstrap broker, acknowledgments, idempotence, chunking and
control checks remain compatible. ZeroTier remains networking only; no OS or
ZeroTier configuration was changed and no remote-network test is claimed.

Saved setup fields, coordinator/bank roles, broker/ZeroTier IP input, topic
preparation/readiness, team-secret input, start/stop/cancel, status/events,
returned checkpoint selection, monitoring/results, reference model and XAI
remain available. Live HTTP checks verify saved profiles, roles, the unchanged
ZeroTier broker value and both privacy scopes. Mode-specific private.single topics
from the validated local repair are prepared through the same UI controls.

## Kafka acceptance and production evidence

The user explicitly prohibited rerunning production noise unless computational
behavior changed. The repair tree was preserved exactly by fast-forward, all15
frozen production source hashes match, and no computational implementation changed.
Therefore **no new production-noise draw or confirmation was performed**.

The actual retained run single-r4e3-confirmation-20261027 remains the full
Collaboration/controller/runner/Kafka acceptance. Its evidence was revalidated:
all four rounds, three HMAC-verified masked65793 contributions per round, no
client_update, original exact ring-sum reconstruction, 16 verified actor
checkpoints, identical returned bytes and unchanged backbone. Public checkpoint
copies in runtime and retained artifacts match. See
PRODUCTION_ACCEPTANCE_REVALIDATION.json and the original full wire/event report.
Secure transport tests also forbid individual-state deserialization and private
plaintext harmonization.

Retained checkpoints were re-scored under the canonical branch without training
or sampling noise. The entire round/per-bank August history reproduces exactly:
research .913431321341 ± .010928024190, production .913564631745 macro August AP.
REVALIDATED_PRODUCTION_VALIDATION.json records the fresh deterministic scoring.
All3190 historical artifact hashes and all measured repair evidence remain intact.

A FRESH actual missing-bank run was executed through the operational launcher,
with two banks and central configured for three. All launched roles fail with
TimeoutError before training; no update, aggregate, checkpoint or fallback occurs.
The new coordinator conservatively reserves one round (epsilon47.015209254).
ACCEPTANCE_ACCOUNTING.json records this alongside prior acceptance reservations;
no new private Gaussian share was generated. The initially stopped broker was
started for this check and restored to stopped afterward.

## Fresh verification

- Full pytest: 170 passed +39subtests.
- XAI unittest discovery: 26 passed.
- Frontend Node: 9 passed.
- Privacy/SecAgg/single-model subset: 26 passed (included in full suite).
- SecAgg smoke: PASS, exact uint64 ring cancellation over242561 coordinates.
- Python compilation: PASS for128 active Python sources.
- Dashboard JavaScript syntax: PASS.
- git diff --check: PASS.
- Live dashboard API/profile/roles/ZeroTier value/privacy-scope checks: PASS.
- Live reference and private single-model XAI: PASS. Reference error0;
  single-model probability error1.6013934733827284e-8, strict tolerance1e-6.
  Both reject an injected1.5e-6 mismatch. No guard was weakened.

The dashboard clearly shows Level-3 Distributed DP + Secure Aggregation for
private collaboration and labels the Sia reference ensemble nonprivate. Sia's
90.68% nonprivate frozen three-member reference and normal training/scoring/XAI
remain intact. The historical90.281% result and failed private-ensemble evidence
are preserved under their original meanings, not relabeled as current results.

Only philip-dp-secagg-ddp is pushed. Main is neither modified nor pushed, and
there is no merge into main. The remote DP branch is for HUMAN verification
before any eventual main integration. Origin/main ancestry and final ahead/behind
counts are verified after the push.
