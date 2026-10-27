# Separate final QA review passes

These are separate model, privacy, crypto, statistical, distributed and regression review passes by the implementing agent, with independently recomputed checks. They are not an external security audit.

## Model review — PASS, with explicit warm-start scope

The retained production means are computed from all three banks with the existing sklearn average-precision protocol. Seeds 42/52/62 score 0.875532822229926, 0.8942499539142802 and 0.9386458723037786; arithmetic mean 0.9028095494826616 and sample SD 0.03241549443748849. Every retained checkpoint reloads to exactly its saved per-bank metrics and NumPy macro mean. An initial QA used Python sum and differed by 1.11e-16; the verifier was corrected to the original NumPy aggregation. No training or checkpoint was changed.

All 176,768 frozen coordinates are bitwise identical to the fixed nonprivate starting checkpoint. The 65,793-coordinate decoder is trained locally, globally clipped, independently noised and securely aggregated. Full state keys/shapes/dtypes remain compatible with CausalTemporalGraphSAGE and the existing evaluator/visualization interface. Training/August fingerprints match the previous study. Loaders expose training/validation only; no September evaluation occurred.

The improvement is a configuration change that includes a stronger *fixed* nonprivate warm start and representation freezing. The three reported seeds measure private-continuation/replay/noise variability, not independent nonprivate pretraining variability. Original seed-specific warm-start searches did not reach the target. This is not a controlled claim that a private optimizer alone beats the baseline, or a claim of end-to-end private pretraining.

## Privacy review — PASS under the same retained assumptions

Mode distributed_dp, SecAgg active, fixed cohort 3, expected_clients=min_noise_contributors=3, production OS entropy, delta=1e-6, exactly one actual private release. C=1.25, dimension=65,793, scale=2^24, C_eff=1.250007644339263, sigma_mean=0.1250007644339263, sigma_share=0.216507674984509, expected aggregate noise L2=32.06287882643689.

Independent conservative calculation: rho=3/(2*0.15^2)=66.66666666666667; epsilon=rho+2*sqrt(rho*ln(1e6))=127.36375184207253. Baseline rho=4*3/(2*1e-5^2), epsilon=60001820912.55525. The accountant source is unchanged; no optimistic aggregate accountant is substituted. The legacy raw parameter field named accounting_sensitivity contains the mean sensitivity; actual encoded-share sensitivity is 2*C_eff. FINALIST_PRIVACY.json and its comparison table report the encoded-share value explicitly, and independent recomputation from that sensitivity and sigma_share gives the same rho. All releases count; one round is actually executed. Actual subset dimension, quantization error, sensitivity and Gaussian sigma are checked in both simulation and Kafka manifests.

The production-only new search/acceptance cost uses spend-before-send SQLite reservations, with each mechanism counted once through the simulation or central ledger; client ledgers describe the same joint release and are not double-counted. Historical private-only cost is added separately. Deterministic research runs, nonprivate warm starts, preprocessing, calibration and public August selection prevent a finite end-to-end bound for the complete artifact bundle. Finite-precision Box-Muller is not exact-DP certified; the ideal-Gaussian/computational-entropy caveat is unchanged.

## Crypto review — PASS within the existing threat model

The X25519/HKDF/ChaCha20/ring mechanism and accountant implementation remain unchanged. Reduced-subset dimensions and public policies bind into schema/base/context. Clients alone create ephemeral private keys and masks. The coordinator parses masked_ring only, requires all three keys and contributions, and receives the noisy secure aggregate. Pairwise ring cancellation, HMAC/SHA, malformed keys, schema/base binding, duplicate/stale rejection, restart reservations, no plaintext fallback and missing-cohort failure remain covered by unchanged and new tests.

Read-only audit of the actual Kafka topics finds three secagg_public_key messages and exactly three masked_client_update payloads, each containing only a 65,793-element masked_ring tensor. Payload SHA matches the authenticated coordinator manifests. No client_update, clean individual state/delta, clean aggregate, noise vector, private key or shared secret is persisted. The post-run wire audit does not claim to reverify erased HMAC secrets; operational processes verified HMACs and the read audit verifies matching payload hashes. Public parameter-name lists in research manifests are not cryptographic private keys.

Excluded adversaries remain active public-key substitution, colluding/Byzantine clients, zero-noise malicious clients and dropout recovery. No stronger threat-model claim is made.

## Statistical review — PASS within the declared continuation-seed scope

Every failed trial is retained. Seed-42 screening, promotion to 52 and then 62, bounded coarse-to-fine plans and the stop rule are saved. Every final seed completes. Source/plan are frozen before production; the m=0.15 nominee receives one fresh entropy sequence per seed. The m=0.1 fallback is not run after success. No September tuning, favorable-noise reruns, final seed cherry-picking or cross-mechanism unaccounted ensembles occur. All round checkpoints survive, and any hypothetical shorter-prefix budget is distinguished from actual screening spend.

The common starting checkpoint was already present in Sia's local Git objects and was selected using August before this optimization. Its pretraining seed is 42, explicitly separated from continuation seeds 42/52/62. This scope change is visible in FINAL_REPORT.md, FINALIST_CONFIG.json and checkpoint provenance; the reported SD cannot be used as evidence of robustness across independent pretraining seeds.

## Distributed review — PASS

Real-data baseline and final trainer parity checks are bitwise identical between simulator and worker for all three banks. Final Kafka acceptance runs three independent bank processes and one coordinator against the actual local broker, with the retained subset/configuration and production entropy. Every returned full checkpoint is byte-identical to the coordinator's checkpoint and passes hash/commit-marker verification. Manifests show all three key/noise contributors, dimension 65,793 and the retained accountant. Dashboard/status privacy and legacy transport tests pass; private status never emits local loss, sample counts, private update norms or vectors.

The task-owned broker is restored to its previous stopped state after the read-only wire audit. CLI event logs are optional; absence of an event sink is not presented as a captured dashboard session.

## Regression review — PASS

139 tests and 8 subtests pass. Exact-ring smoke passes at dimension 242,561, and subset ring tests cover reconstruction/noising/frozen parameters. git diff --check passes. Historical Level-3 evidence is hash-unchanged; dataset fingerprints are unchanged. No datasets are fetched, copied or regenerated. No pushes occur.

A new manifest diagnostic initially broke the nonprivate mock transport by trying to vectorize its mock scalar; the diagnostic is now restricted to private modes, with the existing tests left intact. All computational source hashes remain equal to CONFIRMATION_FREEZE.json through final verification.
