# Local single-model r4/e3 utility repair

Branch: `local/dp-singlemodel-r4e3-utility`.
Start: `3ba2fd2b2e19c38bec53b3f302e648efcb16020f`.
All work is local. No branch was pushed, no main checkout was modified, no main
merge occurred, and no LFS pull/fetch or dataset download/copy/regeneration was
performed. The final local commit SHA is reported after committing this file;
it is not embedded in a self-referential tracked document.

## Result

All requested success conditions are met. Same single model across three
continuation trials: **0.913431321341 ± 0.010928024190 macro August PR-AUC**
(sample SD), worst **0.904442638912**. The ONE predeclared production-entropy
Kafka confirmation ends round four at **0.913564631745**.
No favorable-noise reruns or intermediate-round substitutions were used.

The warm model alone scores .9233876194517373 macro August AP. This repair
preserves useful nonprivate warm-start information under private continuation;
it does not claim improvement over that warm baseline or end-to-end DP training.

## Exact architecture and training

ONE CausalTemporalGraphSAGE, node features57, edge features32, hidden128,
dropout.25, GRUCell(128,128), decoder512→128→1. Full state242561 coordinates.
Only decoder65793 coordinates train; 176768 backbone coordinates remain frozen.
There is no ModuleDict, probability ensemble, member averaging or inference model
averaging in the private path. The scorer returns the single probability stream.

Warm path:
`artifacts/research_adaptive_fcl/warm_start/federated/context_harmonized/seed_42/global_model.pt`

Exact SHA256:
`d650af6959d1da46888f30fb79bbfd888a6ec20743d14d447ea078dc351536f5`.
The path/provenance are repository-tracked and checked against Sia's freeze.
Seeds52/62 are continuation/training/noise research seeds ONLY. Every experiment
loads the same seed42 checkpoint. They never become additional private models.

- Exactly three banks, current canonical order: Key_Bank/bank-1,
  Wells_Fargo/bank-2, JPMorgan_Chase/bank-3.
- Exactly four actual communication/release rounds.
- Three local epochs per June and July/replay phase in every round.
- training_protocol=adaptive_single; private_subset=decoder; equal aggregation.
- Local lr=.0003; AdamW; weight_decay=.0001; batch1024; negative_ratio20.
- risk_context replay2000; original per_client RNG rule seed+100*round+index.
- Local optimizer is freshly constructed each client/round; gradient stability
  cap1 is preserved from the existing temporal trainer; no LR schedule added.
- Server: FedAvg on the already-noisy aggregate, learning_rate=.1. No individual
  directions, plaintext temporal harmonization or clean aggregate is used.
- C=.875 in every round; m=.30 in every round; production entropy in confirmation;
  uint64 ring, fixed-point scale16777216; return aggregate=true.

GENERATED_CONFIG.json records the actual operational launch config. The config is
validated before spawn and in the forced-policy child runner. Private ensemble
configs are now rejected at parser, runtime and transport boundaries. Sia's
nonprivate reference ensemble/training UI remain separate and available.

## Training-only clipping calibration

Three bounded training tracks: base lr.0003/replay2000, low lr.0001, and
replay1000. Each uses twelve whole-decoder norms (three clients×four rounds) with
no August/September/testing reads. Base training-only statistics:

| Statistic | L2 |
|---|---:|
| min | 0.573212871520 |
| median | 0.906861686063 |
| mean | 0.878124885063 |
| p75 | 0.965913098602 |
| p90 | 1.137161887115 |
| p95 | 1.244465002243 |
| max | 1.369114521329 |

The predeclared maximum rule gives ceil(1.25×max×4)/4 = 1.75. The candidate
C grid includes that bound and its half (.875), both derived from training-only
norms. August is used to select among candidates, not to estimate these norms.
Calibration and diagnostic metadata are explicitly nonprivate local research
artifacts. CALIBRATION.json also records all tracks and candidate clipping rates.

## Bounded search and explanation

Seven seed42 screens, then continuation seeds52/62 for the two best candidates:
eleven total research runs. All use four rounds, three epochs, one warm model
and m=.30. Research entropy is controlled/deterministic and makes no production
DP claim. All candidates report rounds0–4 and scalar local diagnostics.

| Candidate | Local lr | Replay | C | Server lr | Seed42 round4 AP |
|---|---:|---:|---:|---:|---:|
| half_C | 0.0003 | 2000 | 0.875 | 0.1 | 0.904442639 |
| smaller_replay | 0.0003 | 1000 | 2.0 | 0.1 | 0.889360106 |
| server_0p25 | 0.0003 | 2000 | 1.75 | 0.25 | 0.831333377 |
| low_lr | 0.0001 | 2000 | 1.0 | 0.1 | 0.898681454 |
| server_0p05 | 0.0003 | 2000 | 1.75 | 0.05 | 0.903788907 |
| server_0p1 | 0.0003 | 2000 | 1.75 | 0.1 | 0.890784065 |
| baseline | 0.0003 | 2000 | 1.75 | 1.0 | 0.629894885 |

The baseline has expected unscaled noise L2≈90 and applied steps≈90 each round,
causing poor utility. The selected training-derived smaller C halves that noise;
noisy-only server lr=.1 attenuates both signal and noise. Applied steps are
4.47–4.51 in the finalist trials. This is nonzero private adaptation in every
round, not resetting to the warm model or skipping releases.

Finalist research decoder norms across 36 local updates: min0.590399188,
median1.132680632, mean1.025592521, max1.423229763.
Two of three bank contributions clip in every round: overall clipping rate
**66.666667%**. Research JSON records each client/round
norm and clipping flag, C, multiplier, sigma, expected noise L2 and noisy/applied
aggregate step norms. Production does not expose clean client norms/clipping flags.

At C=.875: sigma_mean=0.175001528868,
sigma_share=0.303111539401, expected raw aggregate noise
L2=44.888148004. FedAvg lr=.1 is postprocessing of that
noisy aggregate. It attenuates released sensitivity and noise together and does
not weaken the accountant. Existing server-optimizer tests and actual ring-sum
reconstruction independently verify the public postprocessing.

No further optimizer-family or privacy-allocation search was necessary once the
bounded search exceeded target robustly. Local lr/replay/weight decay remain the
successful original single-model choices. Utility was restored chiefly by
limiting noisy decoder displacement, not by adding models or weakening privacy.

## Research round trajectories

| Continuation seed | Round0 | Round1 | Round2 | Round3 | Round4 |
|---|---:|---:|---:|---:|---:|
| 42 | 0.923387619 | 0.910424757 | 0.909030939 | 0.902063215 | 0.904442639 |
| 52 | 0.923387619 | 0.918342790 | 0.921857051 | 0.924954165 | 0.925595369 |
| 62 | 0.923387619 | 0.916622261 | 0.919338911 | 0.916808123 | 0.910255956 |

Mean=0.913431321341; sample SD=0.010928024190; worst=0.904442638912.
The comparison finalist (C1.75, server lr.05) also passes, mean.9126420077533477,
sample SD.011606754621954483. The chosen configuration has the larger server rate
and slightly higher three-seed mean under the predeclared preference.

## Privacy and releases

Distributed DP + SecAgg on every bank contribution in all four rounds: decoder
delta → one global L2 clip → independent bank Gaussian share → fixed-point
encoding → X25519/HKDF-SHA256/ChaCha20 pair masking → masked_client_update → Kafka.
Coordinator: complete three masked rings → exact uint64 cancellation → noisy
equal aggregate → FedAvg lr.1 postprocessing → decoder reconstruction with frozen
backbone → verified global-model broadcast.

Total rho = 4×3/(2×.30²) = 66.66666666666667.
Total epsilon = **127.36375184207253**, delta=**1e-6**, conservative
encoded_share_postprocessing accounting. This equals the old one-release m=.15
budget; four releases at m=.15 are forbidden. No release is unprotected.
Quantization sensitivity is retained in sigma calibration. Durable ledgers reserve
before send; restart/duplicate/context/stale checks and no-fallback behavior stay.

The successful run reserves four releases. The separate missing-bank acceptance
conservatively reserves one coordinator round before key exchange fails. Combined
new acceptance scope has five reservations, rho83.33333333333334,
epsilon151.19473757748446 at delta1e-6; older development is outside this figure.
All retained releases compose. The per-deployment four-round bound remains127.36375.

This is incremental privacy conditional on nonprivate warm weights, public schema
and fixed published calibration. Calibration, August metrics/thresholds and
research deterministic-noise runs are nonprivate disclosures. It is not an
end-to-end DP claim. Ideal-Gaussian/finite-precision computational sampler and the
existing honest-but-curious, noncolluding-coordinator assumptions remain.

## ONE production confirmation

PRODUCTION_DECLARATION.json froze all selection decisions/settings/C/server and
fifteen computational source hashes before launch. No production source changed.
One real Kafka run was performed and scored afterward on August only. Its AP
trajectory is 0.923387619 → 0.925261475 → 0.918037097 → 0.913062545 → 0.913564632.
Round four, not the better round-one score, is the primary reported endpoint.

| Bank | PR-AUC | Precision | Recall | F1 | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| Key_Bank | 0.918614948 | 0.782608696 | 0.857142857 | 0.818181818 | 0.998454063 |
| Wells_Fargo | 0.947917519 | 0.403846154 | 0.954545455 | 0.567567568 | 0.999838234 |
| JPMorgan_Chase | 0.874161428 | 0.124031008 | 1.000000000 | 0.220689655 | 0.999932140 |

Macro production metrics: AP0.913564632,
precision0.436828619, recall0.937229437,
F10.535479680, ROC-AUC0.999408145.
Precision/recall/F1 use ordinary August-selected thresholds; PR-AUC is threshold
independent. No transactions were cherry-picked. All four released checkpoints,
manifests/commit markers and final model descriptor are retained locally.

## Operational and regression acceptance

Actual Collaboration → RunController → forced-policy runner → single worker/
coordinator → Kafka path passed all four rounds. Three masked65793 contributions
per round; no clean client_update; no individual-state deserialization in the
secure coordinator; no clean aggregate before bank noise; every bank receives
identical verified global model bytes. Frozen backbone is unchanged in all rounds.
Dedicated fcl.private.single.* topics isolate the other checkout's traffic.
The preexisting DP broker was initially stopped, started for these checks and
stopped afterward. No other checkout/process was modified or stopped.

Missing-bank acceptance: every launched role times out before training, with no
update, aggregate, checkpoint or plaintext fallback. Local Kafka is sufficient;
no remote ZeroTier availability or cryptography test is claimed.

- Core: **170 passed + 35 subtests**.
- XAI Python: **26 passed**.
- Frontend Node: **9 passed**.
- Privacy/SecAgg/single subset: **26 passed**, included in core.
- SecAgg smoke: PASS, exact ring cancellation over242561 coordinates.
- Actual final ring reconstruction: PASS over65793 coordinates in all four rounds.
- Python compilation, JavaScript syntax and git diff --check: PASS.

Live source-dashboard XAI: reference ensemble error0; private single-model
probability error1.6013934733827284e-8. Both reject an injected1.5e-6 mismatch
under the unchanged1e-6 guard. Exactly one model is loaded for private scoring and
XAI. The legacy CPython3.12 bytecode adapter retains its existing separate guards.
Local transaction explanations do not inherit a transaction-level DP guarantee.

## Preservation and limits

All3190 preexisting evidence files match their initial hashes, including Sia's
nonprivate90.68% reference and the historical90.281% single-model DP result.
The discarded private-ensemble experiment remains historical evidence only.
Reference ensemble, ordinary ensemble training UI, monitoring/results and XAI are
preserved; private_single loading/scoring was added without probability averaging.
Old private-ensemble activation is explicitly rejected. No parity guard is weakened.

Canonical September/testing transaction splits were NOT loaded for calibration,
search, production or new scoring/XAI. Historical September metric metadata was
read only for reference integrity/regression checks. No dataset was downloaded,
copied or regenerated. No tests or files in the main checkout were disturbed.

Limits: only three controlled research seeds and one production draw; performance
is validation evidence, not untouched-test or real-bank generalization. The high
inherited epsilon, conditional warm/calibration scope, ideal sampler assumption,
shared-team authentication and lack of app-configured Kafka TLS remain explicit.
Do not delete/roll back ledgers or treat multiple runs as one release.

All successful code, evidence and public released checkpoints are committed
LOCALLY for review. No push to any branch was performed.
