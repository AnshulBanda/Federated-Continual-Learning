# Private adaptive ensemble — final integration report

Main merged: `1760f95f19b3411c3cb5ae3bcef356f8f7d23c60`.
Merge checkpoint: `75a3e3a5fe179e2d6b286a2a540ad3c6ce0ed2fc`.
The separate operational commit containing this report is reported with its final
remote SHA after push; a self-referential commit hash is not embedded here.
All work and pushes stay on `philip-dp-secagg-ddp`. No main checkout, main merge,
force-push or main push occurs.

## Reconciliation

Seven conflicts and their responsibility-based resolutions are recorded in
MERGE_RECONCILIATION.json. Sia's final_model.py, ensemble_training.py, monitoring.py
and results.py remain byte-identical to main, as do the frozen three members and
reference metric artifacts. The newest dashboard, local training, final model
views, monitoring/results and reference XAI are retained. Privacy and automatic
transport use the DP branch's masked-only, fail-closed pipeline.

The private ensemble uses Sia's adaptive local ensemble training but replaces
plaintext temporal harmonization with secure equal aggregation because SecAgg
hides individual client directions. Plaintext `aggregate_adaptive` is reachable
only in explicit nonprivate research. It is never used on private bank updates.

## Exact architecture and fixed training

ModuleDict keys `42`, `52`, `62`, each a CausalTemporalGraphSAGE with 57 node
features, 32 edge features, hidden dimension 128, dropout .25, GRUCell(128,128)
account memory and a 512→128→1 decoder. Prediction is the arithmetic mean of
three sigmoid probabilities, with independent member account-memory states.
The actual full state has 727,683 coordinates.

All three members start from Sia's frozen context_harmonized checkpoints in main:

- 42: d650af6959d1da46888f30fb79bbfd888a6ec20743d14d447ea078dc351536f5
- 52: 98b6c782a27013e4b1917669b2a5ae48d3a7e44ce6a9aa0149aef446473ab0e2
- 62: 4cd0854f6740f99a9f9ef7f1ba3360c06b5178846394feb73033da718ac715fe

`GENERATED_CONFIG.json` is the exact collaboration-generated launch config:
training_protocol=adaptive_ensemble; rounds=4; local_epochs=3 per June/July phase;
lr=.001; wd=.0001; batch=1024; negative_ratio=20; risk_context replay=2000;
per_client RNG with Sia's member/round/client seed rule; return_aggregate=true;
equal aggregation; private_subset=ensemble_decoder. Server postprocessing is
FedAvg with lr=1 (beta1=.9, beta2=.99, epsilon=.001 are retained inactive fields).
Chunk size is 524288. All three banks are mandatory in main's public order:
Key_Bank/bank-1, Wells_Fargo/bank-2, JPMorgan_Chase/bank-3. Deployment inputs are
broker/run ID/local dataset/output folder/timeout, plus local role and credentials.

The explicit new subset contains exactly all three decoders: 65,793 coordinates
per actual member, **197,379 total**, verified from real state keys/tensor sizes.
The old `decoder` semantics remain unchanged. All other 530,304 coordinates
(36 tensors) remain frozen. Tests and actual Kafka checkpoints verify this.

## Calibration and privacy

One bounded clean training-only calibration measured 12 whole-bank norms over
four equal-mean rounds using the fixed training settings. No August, September
or test data was loaded by calibration. Its predeclared rule was
`ceil(1.25 * max(norm) / .5) * .5`, minimum .5. C was frozen before production.

| Training-only statistic | L2 norm |
|---|---:|
| min | 2.845771300822 |
| median | 3.954440882478 |
| mean | 3.880589622136 |
| p75 | 4.362726696842 |
| p90 | 4.846948105004 |
| p95 | 5.020723899724 |
| max | 5.181009981531 |

**Frozen C=6.5.** Calibration statistics/C selection are a nonprivate research
disclosure; they are not claimed to be privatized.

For each bank/round the entire concatenated decoder delta receives ONE global
L2 clip, ONE independent production Gaussian-share vector, separate fixed-point
encoding of clipped delta and noise, uint64 ring addition, then SecAgg masking.
There is no independent per-member clip-to-C sensitivity error. The coordinator
recovers only the already-noisy equal aggregate, reconstructs all three decoders,
and combines them with the frozen non-decoder coordinates.

Privacy: distributed_dp; multiplier=.30; n=3; min_noise_contributors=3;
production entropy; scale=16777216; delta=1e-6; four releases. X25519 ephemeral
keys, HKDF-SHA256 and ChaCha20 pair masks are unchanged. Complete cohort only,
no plaintext fallback, durable spend-before-send ledgers and context/duplicate
rejection are preserved.

Old rho = 1*3/(2*.15²) = 66.66666666666667.
New rho = 4*3/(2*.30²) = 66.66666666666667.
Both give **epsilon=127.36375184207253**, delta=1e-6 under conservative
encoded_share_postprocessing accounting. The dimension-dependent quantization
bound is included in mechanism sensitivity/noise; no weaker accountant is used.
The four production cumulative epsilons are 47.015209254, 76.252653859,
102.565217698, 127.363751842.

The successful run reserves four releases. The separate missing-bank test reserves
one coordinator round before key exchange fails; banks spend no positive round.
Composing these five acceptance reservations gives epsilon=151.19473757748446 at
delta=1e-6. That combined scope excludes previous development ledgers; all retained
ledgers/releases compose. It does not change the four-release per-run comparison.

Privacy is conditional on fixed nonprivate warm members, public preprocessing
and the fixed published calibration. The full research workflow is not end-to-end
DP: calibration statistics, August evaluation and decision thresholds are
nonprivate disclosures. Ideal Gaussian accounting and the existing computational,
finite-precision production sampler assumptions remain explicit.

## Single production confirmation and August utility

PRODUCTION_DECLARATION.json fixed all settings, C, hashes, one production run and
round four as the primary endpoint before launch. The real Kafka acceptance run
was that single production-entropy confirmation. No production rerun or utility
search was performed; no September/test transactions were loaded. All four rounds
are reported, and round four is not replaced by a more favorable checkpoint.

**Final macro August PR-AUC: 0.2171404870679732.** Utility fell sharply under the
requested fixed settings. This result is retained honestly; no further optimization
was performed. Precision/recall/F1 use August-selected per-bank thresholds, as
nonprivate research evaluation. Macro metrics are equal means across banks.

| Bank | PR-AUC | Precision | Recall | F1 | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| Key_Bank | 0.161528791 | 0.260869565 | 0.285714286 | 0.272727273 | 0.927944697 |
| Wells_Fargo | 0.272733491 | 1.000000000 | 0.136363636 | 0.240000000 | 0.986791162 |
| JPMorgan_Chase | 0.217159180 | 0.500000000 | 0.125000000 | 0.200000000 | 0.979419041 |
| Macro | 0.217140487 | 0.586956522 | 0.182359307 | 0.237575758 | 0.964718300 |

| Round | Macro August PR-AUC |
|---|---:|
| 0 | 0.885944422 |
| 1 | 0.000766105 |
| 2 | 0.136971807 |
| 3 | 0.100886729 |
| 4 | 0.217140487 |

PRODUCTION_VALIDATION.json includes per-member metrics, mean-probability ensemble
metrics, thresholds, per-bank results, full trajectories and checkpoint hashes.
All four released coordinator ensembles and commit records are retained under
production_confirmation/. PRODUCTION_MODEL.json identifies round four for review;
it is **not promoted over the reference model** because utility is poor.

## Operational/security acceptance

Actual path: Collaboration.start → RunController snapshot → forced-policy runner
→ bank_worker/aggregator wrappers → privacy.transport → actual local Kafka.
KAFKA_PRODUCTION_ACCEPTANCE.json verifies every round: exactly three masked bank
contributions, masked_ring int64 bit payloads of dimension 197379, authenticated
key rosters, complete cohort, exact ring sum reconstruction of the returned noisy
aggregate, unchanged frozen tensors, valid checkpoint commit records, and identical
returned model bytes on all three banks. All four processes exit zero.
No normal `client_update` appears. Secure-coordinator tests fail on individual
model deserialization or plaintext temporal harmonization.

MISSING_BANK_ACCEPTANCE.json shows all three launched roles fail with TimeoutError
before training: no update, aggregate, checkpoint or fallback. Broker
127.0.0.1:19092 was started for acceptance and stopped afterward. No remote
ZeroTier availability or cryptography claim is made; ZeroTier transports the same
Kafka application traffic.

The dashboard/API distinguish the nonprivate Sia reference from operational
Level-3 collaboration and historical single-model DP runs. Actual current-run
reserved epsilon and cumulative local-ledger scope are shown. No losses, local
sample counts, clean norms, keys, mask seeds or update vectors are exposed.

## Tests, XAI and evidence

- Full core suite: **170 passed + 34 subtests**.
- XAI Python discovery: **26 passed**.
- XAI frontend Node suite: **9 passed**.
- Privacy architecture/transport/ensemble subset: **26 passed**, also in core.
- SecAgg smoke: PASS, exact uint64 cancellation over 242561 coordinates.
- Real final 197379-coordinate ring reconstruction: PASS for all four rounds.
- Python compilation, dashboard JavaScript syntax and git diff --check: PASS.

Exact commands and logs are retained alongside this report. Live XAI tests of
both the nonprivate reference and the private round-four ensemble passed with
zero observed prediction mismatch. Both rejected an injected 1.5e-6 mismatch
under the strict 1e-6 guard. Local explanation compatibility is established for
those checked targets, not all future transactions. All guards remain in place.
The legacy sourceless CPython 3.12 engine path retains its separate compatibility
requirements and parity guards; the current source dashboard path ran in 3.13.
Explanations of private transactions do not inherit transaction-level DP.

All **3148 historical evidence files** match their initial SHA256 hashes. Sia's
**90.68% nonprivate frozen reference** and the **0.902810 ± 0.032415 previous
single-model decoder-private August continuation** remain unchanged and are not
relabeled as this new ensemble's performance. The ten production-frozen source
files also match the predeclared hashes. See INTEGRITY.json and REVIEW.md.

Main was not modified or pushed. Only the DP branch receives the merge and
operational commits, with no history rewrite or force-push.

DP branch: https://github.com/siaa1308/Capstone/tree/philip-dp-secagg-ddp
