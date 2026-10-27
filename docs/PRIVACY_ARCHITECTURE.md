# Fixed-cohort privacy integration

## Scope and configurations

The implementation integrates the current Sia adaptive **local** trainer with
Anshul's verified Kafka delivery, checkpoint pairs and returned aggregate path.
`configs/privacy_{none,option_a,secure_central_dp,distributed_dp}.json` are the
four explicit configurations. All private profiles use equal client weights.
Legacy nonprivate dashboard runs can retain `aggregation: samples`; this is
rejected in private modes. A deployment must use a fresh `run_id` and retain all
budget ledgers. Do not commit local SQLite files or secret environment variables.

All private configurations use the existing three banks, 128 hidden channels,
242,561 floating parameters, 3 June epochs plus 3 July/replay epochs per round,
2,000 replay events, batch size 1,024, AdamW at 0.001, decay 0.0001, negative
ratio 20, temporal backpropagation windows of two batches, and no distillation.
Only model parameters are federated. Replay, optimizer and temporal memory stay
local; causal memory is reconstructed from earlier events during evaluation.

`privacy.mode` behavior:

| Mode | Client contribution | Coordinator |
|---|---|---|
| `none` | Full local model, no clipping/noise | Explicit equal or sample mean |
| `option_a` | Globally clipped delta plus full client Gaussian | Ordinary equal mean of noised models |
| `secure_central_dp` | Clipped, quantized delta, pairwise masked | Decode secure equal mean; add Gaussian |
| `distributed_dp` | Clipped, quantized delta plus rounded Gaussian share, masked | Decode noisy secure equal mean |

Setting the secure-central multiplier to zero provides SecAgg-only, with **no
finite DP guarantee**. Zero distributed noise is similarly not DP. The Option A
branch contained no tracked DP implementation in this audit, and the original
checkout had no untracked Option A files; the comparison baseline is reimplemented
and labeled as such, rather than attributed to nonexistent preserved modules.

## Local trainer and RNG reconciliation

`model_runtime.train_local` calls `adaptive_continual_federated.train_client`.
There is no second local optimization implementation. The regression test starts
both paths from identical model weights, data, round, seed, replay and training
settings and requires bit-for-bit equality of every parameter. The worker uses
`seed + round*100 + client_index`, as the simulator does. June ends at July 1
midnight relative to each bank's timestamp origin. Risk/context replay uses only
completed June labels and June model scores: positives, hard negatives, strictly
earlier account context, and uniform coverage.

Sia supports both `global` and `per_client` RNG. The accepted warm reference uses
one process-global dropout stream across all banks. Independent worker processes
cannot silently reproduce this stream. The distributed profile explicitly uses
Sia's `per_client` policy; tests compare to the corresponding simulator policy.
The global-RNG temporal-harmonized reference is measured separately. This is a
material experimental distinction; no claim of trajectory equivalence to Sia's
accepted global-RNG multiseed reference is made.

## Temporal harmonization

The reference caps temporal update norms at twice the median, computes pairwise
inner products, and partially removes conflicting peer directions before an equal
mean. This requires individual directions. It is available only as a non-secure
research reference. Secure runs retain local context replay and use an equal
mean. There is no hidden server-side harmonization, MPC, or plaintext exception.
The tail guard and ensemble are not enabled in the private pipeline.

## Threat model and authentication

Assume an honest-but-curious coordinator, a fixed authenticated cohort of three
noncolluding banks, all participating in every completed round, and protocol-
following noise generation. Endpoint processes, local ledgers, OS entropy and the
frozen feature contract are trusted. There is no malicious-server, collusion,
Byzantine, dropout recovery, zero-noise-cheater detection or Bonawitz-grade claim.

SHA-256 identifies schema, base model and payload. Existing HMAC-SHA256 covers
all envelope metadata and chunk content, including secure context and roster
hashes. Safetensors safely serializes tensors; it does not encrypt them. HMAC
secrets authenticate bank/coordinator traffic; they do **not** derive masking
secrets. The coordinator knows the bank HMAC secrets, so these MACs cannot protect
against active coordinator public-key substitution. That adversary is excluded;
adding client identity signatures/pinned keys would be needed to extend the model.
Kafka ACLs/TLS are operational concerns beyond these payload protections.

## Secure aggregation protocol

For each run/round/base/schema/cohort context, each bank generates a fresh X25519
private key in its own process. A `secagg_public_key` message carries only its
public key and the complete context. The coordinator validates identity, context,
key length/low-order keys and uniqueness, then broadcasts `secagg_ready` with the
complete roster. Every bank checks its own public key and complete peer set.

Each pair derives the same X25519 ECDH secret. HKDF-SHA256 separates keys by run,
round, ordered pair, sorted cohort, model/schema SHA, base SHA, flattened dimension
and encoding version. ChaCha20 expands the derived key to uniformly pseudorandom
64-bit words. The lower-sorted client adds each pair pad; the higher subtracts it.
All arithmetic is in Z/(2^64). Pair pads cancel **exactly**, independent of payload
size or accumulation order. Server-held messages are individually masked ring
vectors, not floats with approximate cancellation. Under PRG/ECDH assumptions the
server cannot recover individual vectors from them; with all three clients it can
recover only their sum. This is a computational confidentiality statement.

`masked_client_update` has one safetensors int64 tensor, `masked_ring`; int64
carries the exact uint64 bit pattern. Floating/model payloads are rejected. The
real 242,561-coordinate payload and signed chunk serialization are tested. No
private key, shared secret, PRG key/seed or Gaussian vector is written to a ledger,
checkpoint, status event or dashboard. Public rosters may be retained for audit.

Missing key/update participants time out and abort. There is no plaintext fallback.
Wrong runs/rounds/schemas/bases/cohorts and roster hashes are rejected. Exact chunk
retries are idempotent; conflicting duplicates fail. Once complete, each sender
counts once. A durable run reservation before key exchange prevents restarting a
run with new ephemeral keys. Each coordinator round is reserved before broadcast,
covering crashes after receiving all shares. Failed sends consume a conservative
reservation. Restart uses a new run ID and composes prior reservations; there is
no unsafe attempt to recover ephemeral private keys. Ledger deletion, backup
rollback or moving output roots can invalidate cumulative accounting and is not
prevented by this local implementation.

## Encoding and sensitivity

Let d be the number of floating coordinates and s=2^24. First clip the entire
client delta in float64 to L2 norm C, then deterministically round each coordinate
to the nearest integer at scale s. If q is the decoded vector:

    ||q - clip(delta)||_2 <= e = sqrt(d)/(2s)
    ||q||_2 <= C_eff = C + e
    S_mean <= 2 C_eff / n

This explicitly includes quantization in replace-one participating-client
sensitivity. The unquantized ideal is 2C/n; it is **not** used as an exact bound
for the rounded payload. At d=242,561 the error bound is approximately 1.468e-5.
Mean deterministic rounding error is at most e. Gaussian-share rounding adds at
most e to the mean error relative to its continuous counterpart. Noise is never
clipped or data-dependently truncated. Modular wrapping is a postprocessing map
and does not worsen DP. Useful decoding assumes the signed sum fits in int64;
with these settings that limit is billions of standard deviations away. The implementation rejects configurations whose conservative clipped-sum plus
12-sigma-per-client range reaches 2^62 ring units. A union bound on ideal
Gaussian tail wrapping is at most 2*n*d*Phi(-12), below 3e-27 here.
The encoder handles large finite tails by modulo conversion, not rejection.

## Level 2: secure central Gaussian DP

With equal weights, the coordinator transiently decodes the clipped secure sum
and computes the mean, then adds independent Gaussian noise of standard deviation

    sigma_mean = m * (2 C_eff/n).

The released model/update has rho_1=1/(2m^2) zCDP in the ideal Gaussian model.
After r releases, rho=r/(2m^2), and

    epsilon = rho + 2 sqrt(rho ln(1/delta)).

The coordinator sees the clean aggregate **before** central noise. SecAgg hides
individual updates from it, while central DP protects model recipients only if
the coordinator is trusted to add and protect the required noise. The clean
aggregate is local transient computation, never persisted or emitted.

## Level 3: distributed Gaussian shares and conservative accounting

Each bank independently generates a continuous Gaussian vector with

    sigma_share = 2 C_eff m / sqrt(n) = sqrt(n) sigma_mean.

Before quantization, independence gives

    Var((sum_i z_i)/n) = n sigma_share^2/n^2 = sigma_mean^2.

Each share is rounded to the ring, added to its quantized clipped signal, then
pairwise masked. The coordinator sees only the noisy sum. The rounded-share sum
is **not exactly a continuous Gaussian**. It is not scientifically valid simply
to copy the ideal rho_1=1/(2m^2) bound onto this encoded mechanism.

The implemented defensible bound is deliberately conservative. For a replaced
bank, its quantized signal changes by at most 2C_eff. Its own continuous Gaussian
share has standard deviation 2C_eff m/sqrt(n), hence rho_1=n/(2m^2). Integer
translation commutes with rounding: q+round(z)=round(q+z). Thus its encoded
contribution is postprocessing of that Gaussian mechanism. Adding the other
independent contributions and reducing modulo the ring is further postprocessing.
Adaptive composition gives rho_total=r*n/(2m^2). Secure transcripts reveal only
that sum under the cryptographic assumptions. This is a valid upper bound,
not a claim that the aggregate actually incurs all of that loss. A sharper bound
would need a proved convolution/discrete-Gaussian analysis; it is not asserted.
The ideal aggregate bound is reported only as an uncertified comparison.

All three banks are configured as expected/minimum noise contributors. Insufficient
cohorts fail closed. No robustness to colluding or deliberately noiseless banks
is claimed. Monte Carlo tests check zero mean, client/round independence, intended
share variance, aggregate variance, and agreement with a direct Gaussian reference
within statistical/quantization tolerance. These tests verify implementation
behavior, not a proof of DP by empirical sampling.

Production sampling uses OS CSPRNG uniforms with Box-Muller, and masking uses
cryptography==46.0.5 X25519/HKDF/ChaCha20. Research deterministic Gaussian sampling
exists solely for tests; a published fixed noise seed gives **no operational DP**.
Finite-precision Box-Muller is not a vetted exact Gaussian sampler. Formal zCDP
formulae describe the ideal Gaussian mechanism and its encoding postprocessing;
this capstone implementation does not claim an exact machine-level information-
theoretic guarantee or production-certified Gaussian sampling. A hardened exact
sampler is required before making that stronger claim.

## Accounting, starting checkpoints and experimental disclosures

A run's ledger counts every reserved round, including failed sends, before any
noise can be resampled. Cross-run cumulative accounting is also exposed from the
retained central ledger. Reporting a selected checkpoint does not erase earlier
round releases. Reusing the same data for candidate models/seeds composes their
privacy cost; per-configuration epsilon is **not** the total search cost.
The frontier report includes the sum across all private experiment releases.
Nonprivate references/calibration are openly nonprivate research disclosures, so
this entire research artifact collection has no finite end-to-end DP guarantee.

Warm runs start from Sia's nonprivately trained seed-specific frozen models.
Private continuation protects incremental releases conditional on those fixed
models; it cannot retroactively privatize their training. Scratch runs start
from independent random model weights. Even there, the public encoder contract,
training-only clipping calibration and August selection/metrics are nonprivate.
Any end-to-end client-update claim is conditional on these being genuinely fixed
public auxiliary information and validation data being public. The local IBM
reference contract was originally fitted on training data. This project has not
privatized preprocessing, calibration, validation, threshold selection or the
research search itself. Do not market the artifact as end-to-end private raw-
transaction training.

## Utility and visualization discipline

August macro average precision (equal mean across banks) is primary. September
is not loaded by the experiment runner or graph smoke checks. No ensemble is used.
Fixed final-round metrics are primary; best August round is additionally shown,
with the full scheduled release count charged. Model seeds 42,52,62 are retained;
production Gaussian entropy is independent and not persisted for replay.

Shuchika's actual code contains local account and combined bank graph HTML
visualizations driven by transactions and ground-truth labels. It does not load
models and does not implement SHAP, integrated gradients or feature attribution.
Both visualizers were run on August into a new artifact directory. Their source
was left unchanged. Model/checkpoint shape compatibility and safetensors reload
are tested independently. Private status events expose mode, round, cohort,
phase and budget; no individual update norms, sample counts or losses are emitted
by private transport paths.

References: [Bun & Steinke, zCDP](https://arxiv.org/abs/1605.02065),
[Kairouz, Liu & Steinke, distributed discrete Gaussian](https://arxiv.org/abs/2102.06387),
[cryptography X25519](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/x25519/).
The second paper explains why discrete/ring Gaussian analysis needs explicit care;
its tighter theorem is not claimed as implemented here.

Round completion timing and other transport metadata are not privatized. Privacy
claims concern the released update/model conditional on the fixed public setup,
not all endpoint or timing side channels. The research bundle includes elapsed
times and nonprivate diagnostics and is explicitly not a private publication.

The initial sweep uses fixed-final checkpoints. A separately documented, frozen
follow-up implements Sia's accepted best-August checkpoint rule, retains the exact
selected model and still charges the complete four-round schedule. Its selection
rule and single confirmation (no noise-seed retries) are in
`VALIDATION_SELECTION_FOLLOWUP.json`; screening results are not relabeled.
