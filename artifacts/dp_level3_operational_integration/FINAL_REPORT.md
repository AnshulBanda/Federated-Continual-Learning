# Operational Level-3 DP integration

XAI/main reconciliation checkpoint:
`294af55519f9817a2b985ade85c3614ae30004f4` (already pushed to the DP branch).
The operational change is the separate commit containing this report. Its final
commit and remote SHA are reported after the push; they are not embedded in a
self-referential tracked file. Only `philip-dp-secagg-ddp` is pushed.

## Enforced configuration

`GENERATED_CONFIG.json` is the exact actual coordinator launch configuration.
Only broker, fresh run ID, local dataset/output folders and timeout are deployment
inputs. Kafka topics are the two collaboration topics. All protected fields must
be explicit, and are checked before spawn and independently in the child.

| Setting | Final value |
|---|---|
| Privacy | distributed_dp; C=1.25; m=0.15; delta=1e-6 |
| Cohort | JPMorgan_Chase/bank-1, Wells_Fargo/bank-2, Key_Bank/bank-3, in that order |
| Noise contributors | expected_clients=3; min_noise_contributors=3 |
| Entropy / fixed point | production; scale=16777216 |
| Secure aggregation | mandatory full cohort; X25519, HKDF-SHA256, ChaCha20, uint64 ring |
| Aggregation / subset | equal; decoder; 65,793 private coordinates |
| Rounds / local epochs | 1 release; 2 epochs per June/July training phase |
| Optimizer | lr=0.0003; weight_decay=0.0001; batch_size=1024; negative_ratio=20 |
| Replay / RNG | risk_context; replay_size=2000; per_client; seed=42 |
| Model | hidden_channels=128; dropout=0.25; frozen non-decoder parameters |
| Server optimizer | fedavg; lr=1; beta1=0.9; beta2=0.99; epsilon=0.001 |
| Return / chunks | return_aggregate=true; max_chunk_bytes=524288 |
| Warm checkpoint | FINALIST_CONFIG.json repository-relative seed-42 frozen warm path |
| Warm SHA256 | d650af6959d1da46888f30fb79bbfd888a6ec20743d14d447ea078dc351536f5 |
| Feature schema | artifacts/dp_level3_secagg/feature_schema.json; retained hash verified |
| Broker / timeout | configured Kafka address, including ZeroTier addresses; 60–3600 seconds |

## Data flows and disclosure boundary

Browser → Collaboration.start → RunController → forced-policy runner →
bank_worker/aggregator wrappers → privacy.transport → Kafka. ZeroTier provides
networking only. The lower-level parser retains explicit research modes none,
option_a, secure_central_dp and distributed_dp.

Bank: receive/validate global model → load approved fixed state → full SecAgg
roster → local risk/context replay and decoder-only adaptation → decoder delta →
global L2 clip → independently sample Gaussian share → separately fixed-point
encode clipped delta and noise and add in ring → pair mask → signed/chunked
masked_client_update → Kafka. Existing gradient stability behavior is unchanged.

Coordinator: public model/schema initialization without reading bank records →
authenticated public-key roster → three masked noisy ring contributions → exact
pair-mask cancellation → noisy equal mean → decoder reconstruction combined with
frozen tensors → verified checkpoint → signed model broadcast. In distributed DP,
noise enters at banks before masking; no clean aggregate is reconstructed at the
coordinator. The test round-trip explicitly fails if the secure coordinator calls
the individual model-state deserializer. Secure `Round.add_update` rejects clean
model tensors. Normal clean-update message types are not accepted by the secure
receive path. No plaintext fallback exists.

One/two-bank and duplicate-bank profiles are rejected before launch. Missing
privacy/policy/warm start, sample weights, all-parameter subsets, wrong training
settings and research entropy are rejected. Missing a live participant times out
before training/key-roster completion and prevents aggregation.

## Verification

| Check | Result |
|---|---|
| Full pytest tests | 154 passed + 28 subtests |
| XAI unittest discovery | 26 passed |
| XAI frontend Node tests | 9 passed |
| Privacy architecture + transport subset | 19 passed (also included in full suite) |
| SecAgg smoke | PASS; exact cancellation, 242561 coordinates |
| Final dashboard JavaScript | node --check PASS |
| Changed Python sources | compile PASS, 9 files |
| git diff --check | PASS |
| Real complete-cohort Kafka | all 4 processes exit 0; three masked_ring[65793] contributions |
| Aggregate return | identical verified checkpoint on central + all 3 banks; all model selections verified |
| Missing-bank Kafka | all 3 launched processes fail with TimeoutError; no training/update/checkpoint/fallback |
| Retained artifacts | 3131 SHA256 matches; zero changes |
| Frozen core sources | 32 SHA256 matches; zero changes |
| XAI tree | 1007 tracked files unchanged from merge checkpoint |

Exact commands and outputs are in CORE_TESTS.txt, XAI_TESTS.txt,
FRONTEND_TESTS.txt, PRIVACY_TESTS.txt and SECAGG_SMOKE.json. The full pytest command
uses CAPSTONE_DATASET_DIR pointing to the existing Capstone prepared dataset and
the existing Capstone/.venv/bin/python. No data download, copy, LFS hydration,
search, retraining of the warm model, or metric evaluation was performed.

KAFKA_ACCEPTANCE.json records the actual run IDs, bounded topic offsets,
authenticated payload types/hashes, public events, checkpoint hashes, status and
ledger accounting. Local Kafka is at 127.0.0.1:19092; the existing stopped broker
was started for acceptance and stopped afterward. Local runtime model/ledger
files are preserved under the ignored runtime root named in that report.

The successful private run has epsilon=127.36375184207253, delta=1e-6, with
encoded_share_postprocessing accounting. The failed attempt conservatively
reserves a central release before key exchange. Composing both acceptance
central reservations gives rho=133.33333333333334, epsilon=219.17197438490723 at
delta=1e-6. This excludes prior development ledgers; all retained releases must
compose in a deployment. Deleting or rolling back ledgers invalidates that scope.

## Retained result and limits

Retained private continuation seed scores are 0.875532822229926 (42),
0.8942499539142802 (52), 0.9386458723037786 (62). Mean ± sample SD remains
**0.902810 ± 0.032415 macro August validation PR-AUC**. These values were read from
unchanged retained evidence, not measured by the operational acceptance.

Privacy is conditional on the shared **nonprivate**, August-selected seed-42 warm
checkpoint. This is not end-to-end DP pretraining or independent pretraining
variance. Accounting retains the conservative encoded-share bound and ideal
Gaussian assumption; finite-precision sampling is not exact-DP certified.
The threat model remains honest-but-curious/noncolluding, with a team-shared
authentication secret. Cross-laptop ZeroTier networking was not tested.

DP model integration is preserved; direct XAI explanations of DP checkpoints remain
guarded pending target-wrapper parity at the existing 1e-6 tolerance. The pinned
sourceless XAI engine requires CPython 3.12; live engine inference was not run in
the Python 3.13 project environment. No guard or tolerance was weakened.

All eight final reviews are recorded in REVIEW.md. No main checkout, merge into
main or push to main occurred. Local origin/main remains 18663536f62e6e3c61ca6a43c3f98651320ec9d2;
remote main was independently observed at f2c873e51ebf95cd07f7e7dd010284fb919749ca.
That external main advance was left untouched.

DP branch: https://github.com/siaa1308/Capstone/tree/philip-dp-secagg-ddp
