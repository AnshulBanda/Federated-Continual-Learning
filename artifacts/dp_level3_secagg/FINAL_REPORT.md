# Final AML privacy architecture and experiment report

26 October 2026 · Local integration only · Nothing pushed

**Implementation is complete for the stated research threat model. The retained three-seed Level 3 configurations did not establish macro August PR-AUC ≥ 0.85.** The highest fixed-final result is 0.8325 ± 0.0554, and the frozen best-August checkpoint follow-up is 0.8293 ± 0.0998. Random-initialization Level 3 reaches 0.5662 ± 0.3046. The initial screen’s descriptive best-intermediate mean was 0.8630 ± 0.0500, but its seed-42 intermediate checkpoint was not retained; the single frozen follow-up did not confirm a deliverable passing set. That positive screening result is preserved, not hidden.

This is a bounded empirical result, **not a mathematical proof that every possible configuration is incapable of reaching 0.85**. Useful observed configurations have very large, effectively vacuous epsilon bounds. The accountant is conservative for encoded Gaussian shares and assumes the ideal Gaussian mechanism; the finite-precision sampler is not exact-DP certified. The complete research bundle contains nonprivate references/calibration and has no finite end-to-end DP guarantee.

## A. Source reconciliation

| Ref | Audited SHA | Merge base with transport | Transport-only / ref-only commits |
|---|---|---|---|
| origin/main | `339146e5f759ae9d4c5ef2ae2b4790695dece3b1` | `e74b50e53ff2da933654ddb6c32d6f6bedc4ea43` | 8	1 |
| origin/sia | `f9bf0f24d3cbc5d8c17bc2ecb537417098f1d14e` | `1294588780ddef3512910accce3b0fc48ee655f4` | 13	2 |
| origin/shuchika | `ed047ba419f8e9f371eb97204b06b614790af0ae` | `ed047ba419f8e9f371eb97204b06b614790af0ae` | 24	0 |
| philip-dp-option-a | `a3ec8e384db426a28a0cd9b3e4fb6a51c8380611` | `a3ec8e384db426a28a0cd9b3e4fb6a51c8380611` | 14	0 |
| origin/Anshul-docs/streaming-dashboard-blueprint | `dc208d0254a7c7dd1eff0f79684759f2d3e7403c` | `dc208d0254a7c7dd1eff0f79684759f2d3e7403c` | 30	0 |
| origin/Anshul-feat/modelSharing | `a3ec8e384db426a28a0cd9b3e4fb6a51c8380611` | `a3ec8e384db426a28a0cd9b3e4fb6a51c8380611` | 14	0 |
| origin/Anshul-feat/training-dashboard | `b60b024bdc754575fb5bfb325e5b342f0322095d` | `b60b024bdc754575fb5bfb325e5b342f0322095d` | 5	0 |
| origin/Anshul-feat/verified-weight-delivery | `a432d42a72b5f00c02feacbfa0a46f3c449fe290` | `a432d42a72b5f00c02feacbfa0a46f3c449fe290` | 0	0 |

Chosen base: `origin/Anshul-feat/verified-weight-delivery` at `a432d42a72b5f00c02feacbfa0a46f3c449fe290`. It is five commits ahead of the training-dashboard branch and fourteen ahead of modelSharing. Main’s additional merge commit does not add a different relevant tree. Shuchika is an ancestor and visualization files are identical. Sia’s research additions were imported selectively while retaining Anshul’s stricter base-model validation and cancellation callbacks; there was no merge that discarded the newer transport.

New branch: `philip-dp-secagg-ddp`. Worktree: `/Users/pj/Desktop/college/capstone/Capstone-DP-SecAgg`. Original checkout remains clean on `anshul-dashboard-main`, HEAD `b60b024bdc754575fb5bfb325e5b342f0322095d`. Option A remains at `a3ec8e384db426a28a0cd9b3e4fb6a51c8380611`; no tracked DP modules or untracked Option A files were present. Initial status/HEAD/diff/untracked manifest were saved read-only at `/Users/pj/Desktop/college/capstone/privacy-audit-20261026`. No source was taken from philip-v2; no source branch was overwritten.

[source_manifest.json](/Users/pj/Desktop/college/capstone/Capstone-DP-SecAgg/artifacts/dp_level3_secagg/source_manifest.json) records all changed-file and ancestry evidence. Existing seed-specific starting checkpoints match Sia’s blobs byte-for-byte, and all decompressed training/August fingerprints match Sia’s recorded development data. Reference runtime was torch 2.8.0; this host uses 2.14.0. Exact research scores therefore need not match old frozen numbers.

## B. Final model path

`CausalTemporalGraphSAGE`: 57 node inputs, 32 edge inputs, hidden width 128, dropout 0.25, **242,561 floating parameters**. The worker calls the same `adaptive_continual_federated.train_client` as the simulator. June/July boundary is July 1 midnight. June receives three epochs, then July receives three epochs with 2,000 chronological risk/account-context replay events. AdamW lr 0.001, decay 0.0001, negative ratio 20, batch size 1,024, TBPTT 2, no distillation. Replay and optimizer/temporal state are never federated.

Secure-compatible runs use equal client weights and explicit per-client RNG (`seed + round*100 + client_index`). A regression requires bit-identical worker/reference local parameters for matched inputs and that RNG policy. Sia’s accepted warm reference uses a process-global dropout stream; it is measured separately and is **not claimed to be trajectory-equivalent** to independent workers. Four warm rounds and sixteen scratch rounds were completed for seeds 42/52/62.

Warm initialization: `/Users/pj/Desktop/college/capstone/Capstone/artifacts/final_evaluation/corrected_fedavg/seed_{42,52,62}/global_model.pt`. Scratch initialization is independently seeded random weights. Every run records exact configuration, checkpoint hash, per-bank metrics, full round history and final checkpoint. [seed_results.csv](/Users/pj/Desktop/college/capstone/Capstone-DP-SecAgg/artifacts/dp_level3_secagg/seed_results.csv) lists every retained selected checkpoint. Highest-utility warm configurations are in [best_utility_configs](/Users/pj/Desktop/college/capstone/Capstone-DP-SecAgg/artifacts/dp_level3_secagg/best_utility_configs).

## C. XAI/visualization

Shuchika’s source provides account-level and combined bank graph HTML visualizations using transactions and ground-truth labels. There is no SHAP, integrated gradients, feature attribution, or model explanation endpoint in the audited source. Both generators ran on August into `visualization/`; their source is unchanged. All three follow-up checkpoints reload strictly and exactly reproduce saved August AP; an additional fixed-final private checkpoint also reproduces its saved AP exactly. Prediction/model state keys, shapes and dtypes are preserved.

## D. Transport

Topics: `fcl.global-model` (one partition in local acceptance), `fcl.client-updates` (three partitions). Messages: `global_model`, `secagg_public_key`, `secagg_ready`, `masked_client_update`, `aggregated_model`; ordinary modes retain `client_update`. The previous readiness-only message is no longer required to complete a secure round; a complete validated key roster establishes participation. Existing signed chunk envelopes retain run/round/client/schema/base/payload SHA and HMAC-SHA256. Safetensors transports model floats or a single int64 `masked_ring` bit representation. The coordinator saves hash-verified checkpoint/manifest/commit-marker pairs and returns byte-identical aggregate weights to each bank.

Three real local Kafka acceptance runs completed two rounds each: Level 3, Level 2, and a final Level 3 regression after schema/trainer reconciliation. Each used three independent bank processes and one coordinator on `127.0.0.1:19092`, Kafka 3.9.1. The task-owned broker was stopped afterward. Existing dashboard/recovery/receipt tests pass; private status exposes only mode, SecAgg flag, cohort, round/phase, multiplier, epsilon and delta. Private messages/events omit sample counts, local loss and identifiable update norms.

## E. Secure aggregation

Every client creates an ephemeral X25519 key pair per round. Authenticated public hellos bind the run, round, complete sorted cohort, schema, base hash, dimension and encoding domain. The server broadcasts the validated public roster; clients verify their own key and every peer. X25519 ECDH produces client-only pair secrets. HKDF-SHA256 binds those contexts and ordered pair IDs; ChaCha20 expands them to uint64 ring pads. Lower-sorted client adds, higher-sorted subtracts. Summing all three contributions cancels masks **exactly in Z/(2^64)**. The central server does not possess client private keys or mask seeds. Public rosters/context hashes are retained for audit, never secrets.

Fixed-point scale is 2^24. Nearest rounding has L2 error `e = sqrt(d)/(2s)`, so `C_eff = C + e` and mean sensitivity is `2*C_eff/n`, not an unadjusted `2C/n` claim. Numeric range guards reject configurations that cannot uniquely decode within the conservative clipped-plus-12-sigma range; extreme Gaussian tails wrap as postprocessing, never by hidden truncation. Exact ring cancellation is tested on the real dimension. Missing clients, wrong contexts, malformed keys, conflicting duplicates or stale bases abort without a plaintext fallback.

Threat model: honest-but-curious coordinator; authenticated, noncolluding, protocol-following fixed cohort; all banks supply noise. HMAC keys are unrelated to mask secrets. Active server public-key substitution, collusion, Byzantine/zero-noise clients and dropout recovery are excluded. HMAC alone is not protection from an actively malicious server that knows MAC secrets. There is no Bonawitz-grade claim. Timing/metadata side channels are not privatized.

## F. Level 2 aggregate DP

After global L2 clipping and ring SecAgg, the server transiently sees the clean aggregate, then adds Gaussian noise `sigma_mean = m * 2*C_eff/n`. Under the ideal Gaussian model, replace-one client adjacency gives `rho_1=1/(2m²)`, `rho_total=r/(2m²)`, `epsilon=rho+2*sqrt(rho*ln(1/delta))`. Central DP protects recipients under trusted server noise generation; it does not hide that clean aggregate from the coordinator. The clean aggregate is not persisted or emitted.

## G. Level 3 distributed DP

Each client adds an independent Gaussian share before masking, with `sigma_share = 2*C_eff*m/sqrt(n) = sqrt(n)*sigma_mean`. Therefore `Var(sum(z_i)/n)=n*sigma_share²/n²=sigma_mean²` before rounding. Gaussian shares remain after pair masks cancel, so the coordinator receives only a noisy aggregate. All three noise contributors are required.

The released rounded-share sum is not exactly a continuous Gaussian. The implemented conservative bound follows the changed client’s own share: its sensitivity is at most `2*C_eff`, so `rho_1=n/(2m²)`. Rounding integer translations and adding other independent shares/modulo reduction are postprocessing (in the ideal Gaussian model). Thus `rho_total=r*n/(2m²)`. The more optimistic ideal aggregate bound `r/(2m²)` is not falsely certified for this encoding. Monte Carlo tests cover production and research samplers, independence, mean, share/aggregate variance, Gaussian reference agreement and exact mask cancellation. OS entropy is never persisted; deterministic research noise is forbidden by the operational private pipeline.

Finite-precision Box-Muller is not a vetted exact Gaussian sampler. These epsilon values are explicitly ideal-Gaussian mechanism bounds, not a machine-level information-theoretic certificate. A hardened exact sampler/tighter discrete-convolution proof would be required for stronger claims.

## H. Privacy modes

`none`: no clipping/DP, ordinary aggregation; legacy explicit sample weighting remains available. `option_a`: clipped local delta plus full per-client Gaussian noise, ordinary transmission, equal mean. `secure_central_dp`: clipped/quantized masked updates, central aggregate noise. `distributed_dp`: clipped/quantized updates plus encoded independent noise shares, then masks. Private modes reject unequal weighting and duplicate bank datasets. Option A is a labeled reimplementation of that baseline mechanism, since no preserved DP modules existed locally.

## I. Clipping calibration

All 36 norms came from training-only updates under the current per-client replay trainer: min 2.21142, median 3.36019, mean 3.85768, p75 5.27932, p90 5.94684, p95 6.09247, max 6.42654. C was frozen at **6.5** by rounding the observed maximum upward to a half unit. Per-bank/per-round rows and quantiles are in [clipping_calibration.json](/Users/pj/Desktop/college/capstone/Capstone-DP-SecAgg/artifacts/dp_level3_secagg/clipping_calibration.json). The historical 6.2954 was not reused. Calibration is nonprivate; freezing it does not retroactively privatize its derivation.

## J. Completed privacy/utility search

37 real-model runs completed: 220 simulated federated rounds, including 136 private rounds, plus six real Kafka acceptance rounds. Every model seed is retained. Selection never loaded September. The training/August fingerprints match Sia exactly. Delta is 1e-6. Initial screening used fixed-final checkpoints; one separately frozen follow-up used Sia’s best-August checkpoint rule with exactly one fresh noise sequence per seed and full four-round accounting. No failed result was discarded. The fixed noise multiplier sweep spans 1e-5 to 0.1; 0.1 clearly degraded and remained single-seed.

All per-seed C/n/sensitivity/multiplier/sigma/share sigma/noise L2/noise-to-baseline-update ratio/epsilon/delta/releases/AP/F1/precision/recall/ROC-AUC/per-bank AP are in [seed_results.csv](/Users/pj/Desktop/college/capstone/Capstone-DP-SecAgg/artifacts/dp_level3_secagg/seed_results.csv). Noise/update ratio uses the matched nonprivate training-update median, rather than disclosing private update norms. The table below lists every aggregate configuration; AP is equal-bank sklearn average precision and ± is sample SD across model seeds (one production-noise sequence each), not a confidence interval.

# Validation/privacy frontier

Initial screening uses fixed final checkpoints; the separately frozen follow-up retains the best-August checkpoint, labeled explicitly. ± is sample standard deviation across model seeds, with one independent production noise sequence per seed. Best intermediate August AP is descriptive; all rounds are charged. Epsilon is per seed/pipeline, not the entire search. See `seed_results.csv` for every metric, bank and mechanism parameter.

| Track | Mode / selection | m | Seeds | Selected macro AP ± SD | Best intermediate AP ± SD | Epsilon/pipeline |
|---|---|---:|---|---:|---:|---:|
| scratch | distributed_dp / final | 0.001 | 42,52,62 | 0.5662 ± 0.3046 | 0.6882 ± 0.1601 | 2.40364e+07 |
| scratch | none / final | 0 | 42,52,62 | 0.4841 ± 0.2827 | 0.7620 ± 0.0692 | infinite |
| warm | distributed_dp / best_validation | 1e-05 | 42,52,62 | 0.8293 ± 0.0998 | 0.8293 ± 0.0998 | 6.00018e+10 |
| warm | distributed_dp / final | 1e-05 | 42,52,62 | 0.8325 ± 0.0554 | 0.8630 ± 0.0500 | 6.00018e+10 |
| warm | distributed_dp / final | 0.0001 | 42,52,62 | 0.5931 ± 0.3319 | 0.8449 ± 0.0684 | 6.00182e+08 |
| warm | distributed_dp / final | 0.001 | 42,52,62 | 0.7609 ± 0.1223 | 0.8085 ± 0.0834 | 6.01821e+06 |
| warm | distributed_dp / final | 0.01 | 42,52,62 | 0.5886 ± 0.2275 | 0.7506 ± 0.1418 | 61820.9 |
| warm | distributed_dp / final | 0.1 | 42 | 0.0031 (single seed) | 0.1495 (single seed) | 782.091 |
| warm | none / final | 0 | 42,52,62 | 0.7032 ± 0.2601 | 0.8242 ± 0.0676 | infinite |
| warm | option_a / final | 0.001 | 42,52,62 | 0.7027 ± 0.1792 | 0.8293 ± 0.0278 | 2.01051e+06 |
| warm | research_reference / final | 0 | 42,52,62 | 0.6735 ± 0.3099 | 0.8056 ± 0.1368 | infinite |
| warm | secure_central_dp / final | 0 | 42,52,62 | 0.7016 ± 0.2590 | 0.8241 ± 0.0675 | infinite |
| warm | secure_central_dp / final | 0.001 | 42,52,62 | 0.6006 ± 0.2704 | 0.8405 ± 0.0643 | 2.01051e+06 |

Private subset composition: rho=3.6190918e+11, epsilon=3.6191365e+11, delta=1e-6. The whole nonprivate research bundle is not DP.

A bounded negative result does not prove impossibility for every other multiplier or training configuration. No seed, noise realization or September result is selected to manufacture a passing mean.


### Full metric comparison

| Track / mode / selection / m | PR-AUC | Precision | Recall | F1 | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| scratch / distributed_dp / final / 0.001 | 0.5662 ± 0.3046 | 0.2929 ± 0.1267 | 0.7643 ± 0.0956 | 0.3774 ± 0.1305 | 0.9983 ± 0.0014 |
| scratch / none / final / 0 | 0.4841 ± 0.2827 | 0.2612 ± 0.1254 | 0.7337 ± 0.1176 | 0.3406 ± 0.1356 | 0.9964 ± 0.0033 |
| warm / distributed_dp / best_validation / 1e-05 | 0.8293 ± 0.0998 | 0.4166 ± 0.0350 | 0.9091 ± 0.0487 | 0.5137 ± 0.0376 | 0.9996 ± 0.0003 |
| warm / distributed_dp / final / 1e-05 | 0.8325 ± 0.0554 | 0.3982 ± 0.0221 | 0.8949 ± 0.0242 | 0.4951 ± 0.0231 | 0.9993 ± 0.0005 |
| warm / distributed_dp / final / 0.0001 | 0.5931 ± 0.3319 | 0.2944 ± 0.1547 | 0.7407 ± 0.2101 | 0.3791 ± 0.1714 | 0.9947 ± 0.0072 |
| warm / distributed_dp / final / 0.001 | 0.7609 ± 0.1223 | 0.3925 ± 0.0389 | 0.8827 ± 0.0473 | 0.4885 ± 0.0410 | 0.9993 ± 0.0003 |
| warm / distributed_dp / final / 0.01 | 0.5886 ± 0.2275 | 0.3047 ± 0.0951 | 0.6994 ± 0.1837 | 0.3749 ± 0.1227 | 0.9816 ± 0.0286 |
| warm / distributed_dp / final / 0.1 | 0.0031 (one seed) | 0.0044 (one seed) | 0.3902 (one seed) | 0.0087 (one seed) | 0.7374 (one seed) |
| warm / none / final / 0 | 0.7032 ± 0.2601 | 0.3519 ± 0.1154 | 0.8880 ± 0.0315 | 0.4541 ± 0.1029 | 0.9989 ± 0.0007 |
| warm / option_a / final / 0.001 | 0.7027 ± 0.1792 | 0.3493 ± 0.0568 | 0.8663 ± 0.0271 | 0.4423 ± 0.0644 | 0.9987 ± 0.0006 |
| warm / research_reference / final / 0 | 0.6735 ± 0.3099 | 0.3335 ± 0.1234 | 0.8400 ± 0.0758 | 0.4303 ± 0.1198 | 0.9980 ± 0.0014 |
| warm / secure_central_dp / final / 0 | 0.7016 ± 0.2590 | 0.3519 ± 0.1154 | 0.8880 ± 0.0315 | 0.4541 ± 0.1029 | 0.9989 ± 0.0008 |
| warm / secure_central_dp / final / 0.001 | 0.6006 ± 0.2704 | 0.3095 ± 0.1221 | 0.7833 ± 0.1459 | 0.3994 ± 0.1233 | 0.9954 ± 0.0049 |

## K. Primary result

**No retained, three-seed Level 3 configuration established validation macro PR-AUC ≥0.85.** Highest fixed-final utility: 0.8325 ± 0.0554, C=6.5, n=3, m=1e-5, four rounds, per-seed epsilon 6.00018e+10, delta 1e-6. The frozen best-August follow-up is 0.8293 ± 0.0998 with the same per-run budget. The initial descriptive best-round screen was 0.8630 ±0.0500; its incomplete checkpoint set and failed fresh confirmation prevent presenting it as a reproducible deliverable target achievement.

The failure is empirical: seed/round instability remains substantial, especially seed 62, and increasing noise reduces useful ranking. Even low-noise configurations have vacuous privacy bounds. This experiment cannot establish a universal impossibility theorem, and no privacy formula, test split or seed was manipulated to claim one.

### Strongest tested privacy above lower utility thresholds

| Minimum mean validation AP | Selected multiplier / protocol | Observed mean AP | Epsilon/pipeline |
|---:|---|---:|---:|
| 0.85 | none | — | — |
| 0.8 | 1e-05 / best_validation | 0.8293 | 6.00018e+10 |
| 0.7 | 0.001 / final | 0.7609 | 6.01821e+06 |
| 0.6 | 0.001 / final | 0.7609 | 6.01821e+06 |
| 0.5 | 0.01 / final | 0.5886 | 61820.9 |

No point should be marketed as both strong practical DP and ≥0.85 utility. All warm points are conditional on a preexisting nonprivate model. The scratch Level 3 run gives 0.5662 ± 0.3046 at m=0.001, sixteen rounds and per-seed epsilon 2.40364e+07.

## L. Level comparison

| Level | Exact semantics | Macro validation AP |
|---|---|---:|
| No privacy | Warm 4 rounds, per-client context replay, equal mean, m=0 | 0.7032 ± 0.2601 |
| Option A | Warm 4 rounds, per-client context replay, equal mean, m=0.001 | 0.7027 ± 0.1792 |
| SecAgg only | Warm 4 rounds, per-client context replay, equal mean, m=0 | 0.7016 ± 0.2590 |
| SecAgg + central aggregate DP | Warm 4 rounds, per-client context replay, equal mean, m=0.001 | 0.6006 ± 0.2704 |
| SecAgg + distributed DP | Warm 4 rounds, per-client context replay, equal mean, m=0.001 | 0.7609 ± 0.1223 |

Central and distributed runs have matching target aggregate Gaussian variance, but independently sampled noise; observed differences are not evidence that one noise placement is inherently more accurate. Option A at the same m has sqrt(n) larger aggregate noise standard deviation and releases each individually noised update. Research reference uses global RNG and temporal harmonization and is explicitly not an identical secure-compatible comparison.

## M. Temporal harmonization resolution

Only the non-secure research reference sees individual directions. Secure-compatible aggregation is an equal mean. Local risk/account-context replay remains. No individual clean update is revealed to retain harmonization, and no general MPC/HE extension was added.

## N. Warm-start and end-to-end privacy caveats

Warm-start DP applies only to incremental releases conditional on a fixed starting checkpoint; that checkpoint already encodes training data nonprivately. Scratch starts from independent random model weights but still conditions on fixed public preprocessing/C and public August validation. The reference feature encoder was originally fitted on the same training data, and calibration/validation/threshold selection are not DP. Therefore this artifact is not end-to-end DP raw-transaction training. Releasing all private model seeds/candidates composes: private-only rho=3.61909e+11, epsilon=3.61914e+11 at delta=1e-6. The entire research bundle also contains nonprivate disclosures and has no finite DP bound. Per-run epsilon is not the total cost.

## O. Security tests

X25519 pair agreement/separation and null/malformed key rejection; run/round/schema/base/cohort/roster binding; HMAC tamper rejection; exact 242,561-coordinate uint64 cancellation; safetensors/chunk roundtrip; masked-only central parsing; duplicate key/update rejection; complete cohort enforcement; no plaintext fallback; durable restart/spend guards; share independence and production/research sampling; mean/variance/KS reference checks; clipping/sensitivity/error bounds; accountant/composition independent calculations; non-sensitive status; no optimizer/replay/temporal-state federation. A test is not a cryptographic proof: confidentiality also relies on the stated standard primitive assumptions and excluded adversaries.

## P. Model/streaming regression results

...................................................................... [ 55%]
........................................................           [100%]
126 passed, 8 subtests passed in 7.69s

Additional evidence: [secagg_smoke.json](/Users/pj/Desktop/college/capstone/Capstone-DP-SecAgg/artifacts/dp_level3_secagg/secagg_smoke.json), [checkpoint_reload_qa.json](/Users/pj/Desktop/college/capstone/Capstone-DP-SecAgg/artifacts/dp_level3_secagg/checkpoint_reload_qa.json), three `kafka_acceptance/*/result.json` PASS records and generated August graph HTML. All follow-up selected checkpoints reload to exactly their saved macro August AP. Existing streaming/dashboard/receipt/recovery/model tests pass. No source visualization code was modified.

## Q. Independent QA reviews

Six separate reasoning passes covered model, crypto, DP math, distributed systems, utility and regression. Defects repaired included old trainer mismatch, lost upstream callbacks/strict checks during source reconciliation, late budget reservation after receiving shares, weak source/schema binding, unsafe numeric ranges, misleading fixed-final/best-round comparison and long-lived source-snapshot labeling. [SECURITY_QA.md](/Users/pj/Desktop/college/capstone/Capstone-DP-SecAgg/artifacts/dp_level3_secagg/SECURITY_QA.md) records evidence, attacks, fixes and residual assumptions. These are independent review passes, not a claimed external security audit. [LOADED_SOURCE_PROVENANCE.json](/Users/pj/Desktop/college/capstone/Capstone-DP-SecAgg/artifacts/dp_level3_secagg/LOADED_SOURCE_PROVENANCE.json) preserves the computational sources actually loaded by earlier long-lived processes; original screening result/freeze hashes remain unchanged.

## R. Every created/modified path

Every path, including source imports, tests, configs, docs, checkpoints and evidence, is listed in [FILES_CHANGED.txt](/Users/pj/Desktop/college/capstone/Capstone-DP-SecAgg/artifacts/dp_level3_secagg/FILES_CHANGED.txt). Transient local ledgers/logs/reservations are retained locally and ignored; no .env, private key, pair secret, mask seed or noise realization is committed. No dataset was downloaded, fetched with LFS, copied or regenerated.

## S. Artifact paths

Artifact root: `/Users/pj/Desktop/college/capstone/Capstone-DP-SecAgg/artifacts/dp_level3_secagg`. Key files: source_manifest.json; checkpoint_provenance.json; development_data_fingerprint.json; environment.json; clipping_calibration.json; SEARCH_DESIGN.json; VALIDATION_SELECTION_FOLLOWUP.json; validation_selection_freeze.json; seed_results.csv; aggregate_results.json; privacy_utility_frontier.json; FRONTIER.md; SECURITY_QA.md; test_report.txt; checkpoint_reload_qa.json; source_snapshot.tar.gz; loaded_source_groups/; experiment_source/; experiments/; kafka_acceptance/; visualization/; best_utility_configs/.

## T. Exact reproduction commands

# Reproduction

Run in `/Users/pj/Desktop/college/capstone/Capstone-DP-SecAgg`.
The existing interpreter is `/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python`.
Use an otherwise equivalent environment from `environment.json` on another host.
All output directories must be new; examples intentionally use `reproduce_*` paths.
The dataset remains at `/Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset`.
Do not fetch LFS, copy the dataset, or score September during selection.

## Tests

```sh
CAPSTONE_DATASET_DIR=/Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset /Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python -m pytest tests -q
/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python scripts/secagg_smoke.py
git diff --check
```

## Nonprivate reference and baseline

```sh
/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python scripts/run_private_federation.py --dataset /Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset --output artifacts/dp_level3_secagg/reproduce_reference --mode none --reference --multipliers 0 --seeds 42 52 62 --rounds 4
/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python scripts/run_private_federation.py --dataset /Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset --output artifacts/dp_level3_secagg/reproduce_baseline --mode none --multipliers 0 --seeds 42 52 62 --rounds 4
```

## Level 2 and SecAgg-only

```sh
/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python scripts/run_private_federation.py --dataset /Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset --output artifacts/dp_level3_secagg/reproduce_level2 --mode secure_central_dp --clip 6.5 --multipliers 0 0.001 --seeds 42 52 62 --rounds 4
```

## Level 3 and old-mechanism Option A comparison

```sh
/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python scripts/run_private_federation.py --dataset /Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset --output artifacts/dp_level3_secagg/reproduce_level3 --mode distributed_dp --clip 6.5 --multipliers 0.00001 0.0001 0.001 0.01 --seeds 42 52 62 --rounds 4
/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python scripts/run_private_federation.py --dataset /Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset --output artifacts/dp_level3_secagg/reproduce_option_a --mode option_a --clip 6.5 --multipliers 0.001 --seeds 42 52 62 --rounds 4
```

For the independent-initialization track, add `--track scratch --rounds 16`.
A private scratch run uses `--mode distributed_dp --multipliers 0.001`; the baseline
uses `--mode none --multipliers 0`. Noise realization is intentionally unreproducible
from a public seed. Model initialization and local training are reproducible;
new private runs should have statistically comparable distributions, not identical
private noise. Reload the saved checkpoints for exact saved-result verification.

## Real local Kafka acceptance

The acceptance evidence used `apache/kafka:3.9.1`, digest
`sha256:4ceccc577f03f51f6af8dbfda55194d0d892f4fa7913ffbded567ce3895622ed`,
on `127.0.0.1:19092`. This is a real local broker, three bank processes and one
coordinator. Topics are `fcl.global-model` (one partition) and `fcl.client-updates`
(three partitions). The harness creates the topics and generates HMAC secrets in
memory; no `.env` is written. With that broker running:

```sh
/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python scripts/kafka_private_acceptance.py --config configs/privacy_distributed_dp.json --rounds 2 --output artifacts/dp_level3_secagg/reproduce_kafka_ddp
/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python scripts/kafka_private_acceptance.py --config configs/privacy_secure_central_dp.json --rounds 2 --output artifacts/dp_level3_secagg/reproduce_kafka_central
```

The normal distributed CLI is unchanged:

```sh
python -m distributed_federation.central.aggregator --config configs/privacy_distributed_dp.json
python -m distributed_federation.client.bank_worker --config configs/privacy_distributed_dp.json --client-id bank-1
```

Run workers 2 and 3 separately with their IDs and corresponding client secret.
Set `FCL_CENTRAL_SECRET` in all processes, `FCL_CLIENT_SECRET` in each bank and
`FCL_CLIENT_SECRET_BANK_1`, `_BANK_2`, `_BANK_3` in the coordinator. Use independent
random secrets, a fresh run ID and a retained output/ledger root. The harness is
the reproducible alternative that handles this without writing secrets.

## August checkpoint reload/evaluation

```sh
/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python scripts/evaluate_private_federation.py --dataset /Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset --checkpoint artifacts/dp_level3_secagg/experiments/warm_distributed_dp_m0.001_s42/global_model.pt --output artifacts/dp_level3_secagg/reproduce_evaluation.json
```

The evaluator also accepts a returned `.safetensors` checkpoint. Model validation
warms temporal state on training before scoring August. There is deliberately no
September/test option. Graph checks used `--split validation` and new output paths
under `artifacts/dp_level3_secagg/visualization`.

## Restart the task-owned local broker

The broker was stopped after QA. On this host, restart it before a Kafka rerun:

```sh
docker start capstone-dp-kafka-20261026
```

The already frozen checkpoint-selection follow-up can be reproduced in a NEW output directory with:

```sh
/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python scripts/run_private_federation.py --dataset /Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset --output artifacts/dp_level3_secagg/reproduce_selected_validation --mode distributed_dp --clip 6.5 --multipliers 0.00001 --seeds 42 52 62 --rounds 4 --selection best_validation
```

This samples fresh private noise. Do not repeat runs to select a favorable noise sequence. The completed frozen follow-up is negative and remains so in the report.


## U. Final Git state

Branch `philip-dp-secagg-ddp`; tested source commit `a274e885ca833c130fa1700adf4ef35436760a80`. Local implementation commits: `1d7060829235b2c0b6e371f64169c0faf120b57a` and `a274e885ca833c130fa1700adf4ef35436760a80`; evidence is saved in a subsequent local commit. The exact final HEAD, commit list and final `git status --short` are recorded after that commit in [FINAL_GIT_STATE.json](/Users/pj/Desktop/college/capstone/Capstone-DP-SecAgg/artifacts/dp_level3_secagg/FINAL_GIT_STATE.json). It is ignored to avoid a self-referential Git hash. The chat also reports the final HEAD. Nothing was pushed. Original checkout remains unchanged.

## V. Presentation-safe claim

“The three-bank AML prototype keeps raw transactions local and integrates the current temporal GraphSAGE replay trainer with verified Kafka delivery. Client-only ephemeral X25519 pairwise masks hide individual contributions from an honest-but-curious, noncolluding fixed cohort coordinator. Level 2 adds aggregate Gaussian noise at the server; Level 3 adds independent client noise shares before exact ring secure aggregation, so the coordinator receives only a noisy aggregate. Missing participants fail closed. Conservative encoded-mechanism accounting and checkpoint/preprocessing caveats are reported explicitly. The completed validation study did not establish a retained three-seed configuration meeting 0.85 macro PR-AUC, and useful-utility settings had weak privacy bounds.”

Primary references: [X25519 primitive documentation](https://cryptography.io/en/46.0.5/hazmat/primitives/asymmetric/x25519/), [Bun and Steinke zCDP](https://arxiv.org/abs/1605.02065), [Kairouz et al. discrete distributed Gaussian analysis](https://proceedings.mlr.press/v139/kairouz21a.html). The latter’s tighter theorem is not claimed as implemented.

## Complete tested mechanism parameters and per-bank AP

Values describe the released mean; Option A additionally releases individual noised models, so its accountant uses full client sensitivity. None/reference mode C and sensitivity are not applied. All delta values are 1e-6. Epsilon is per seed/pipeline under the stated Gaussian-model assumptions.

| Track / mode / selection / m | C | n | S_mean | sigma_mean | sigma_share | Noise L2 | Noise/update | Releases | Epsilon | JPM AP | WF AP | Key AP |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| scratch / distributed_dp / final / 0.001 | 6.5 | 3 | 4.33334 | 0.00433334 | 0.00750557 | 2.13419 | 0.831816 | 16 | 2.40364e+07 | 0.5965 | 0.4964 | 0.6057 |
| scratch / none / final / 0.0 | — | 3 | — | 0 | 0 | 0 | 0 | 16 | infinite | 0.4825 | 0.4179 | 0.5520 |
| warm / distributed_dp / best_validation / 1e-05 | 6.5 | 3 | 4.33334 | 4.33334e-05 | 7.50557e-05 | 0.0213419 | 0.00910634 | 4 | 6.00018e+10 | 0.7504 | 0.8722 | 0.8652 |
| warm / distributed_dp / final / 0.0001 | 6.5 | 3 | 4.33334 | 0.000433334 | 0.000750557 | 0.213419 | 0.0910634 | 4 | 6.00182e+08 | 0.6068 | 0.6236 | 0.5488 |
| warm / distributed_dp / final / 0.001 | 6.5 | 3 | 4.33334 | 0.00433334 | 0.00750557 | 2.13419 | 0.910634 | 4 | 6.01821e+06 | 0.6551 | 0.8074 | 0.8202 |
| warm / distributed_dp / final / 0.01 | 6.5 | 3 | 4.33334 | 0.0433334 | 0.0750557 | 21.3419 | 9.10634 | 4 | 61820.9 | 0.6879 | 0.4803 | 0.5975 |
| warm / distributed_dp / final / 0.1 | 6.5 | 3 | 4.33334 | 0.433334 | 0.750557 | 213.419 | 91.0634 | 4 | 782.091 | 0.0024 | 0.0014 | 0.0053 |
| warm / distributed_dp / final / 1e-05 | 6.5 | 3 | 4.33334 | 4.33334e-05 | 7.50557e-05 | 0.0213419 | 0.00910634 | 4 | 6.00018e+10 | 0.7616 | 0.9226 | 0.8134 |
| warm / none / final / 0.0 | — | 3 | — | 0 | 0 | 0 | 0 | 4 | infinite | 0.6780 | 0.7222 | 0.7094 |
| warm / option_a / final / 0.001 | 6.5 | 3 | 4.33333 | 0.00750555 | 0.013 | 3.69652 | 1.57726 | 4 | 2.01051e+06 | 0.6876 | 0.7382 | 0.6822 |
| warm / research_reference / final / 0.0 | — | 3 | — | 0 | 0 | 0 | 0 | 4 | infinite | 0.6572 | 0.7153 | 0.6480 |
| warm / secure_central_dp / final / 0.0 | 6.5 | 3 | 4.33334 | 0 | 0 | 0 | 0 | 4 | infinite | 0.6764 | 0.7200 | 0.7084 |
| warm / secure_central_dp / final / 0.001 | 6.5 | 3 | 4.33334 | 0.00433334 | 0.00750557 | 2.13419 | 0.910634 | 4 | 2.01051e+06 | 0.6603 | 0.5391 | 0.6025 |
