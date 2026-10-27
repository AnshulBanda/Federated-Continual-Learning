# Independent QA reasoning and evidence

Each review below is a separate pass over the final design, not a claim of an
external cryptographic audit. The detailed threat model is in
`docs/PRIVACY_ARCHITECTURE.md`.

| Review | Finding and resolution | Evidence |
|---|---|---|
| Model | Old full-stream worker and accepted replay trainer differed. Worker now calls the shared adaptive local trainer. Per-client RNG is explicit; global-RNG reference remains distinct. Existing callbacks and stricter data validation were preserved. | Exact parameter equivalence test; Sia model/replay/threshold tests; real-model experiments. |
| Crypto | Float masks risk numerical leakage. Chosen exact uint64 ring with fresh X25519 round keys, context-separated HKDF, ChaCha20 pair pads. Server has public rosters but never client private/pairwise keys. | 242,561-coordinate exact cancellation test, shared-secret symmetry/separation, malformed/null key/context/substitution tests, actual signed Kafka exchange. |
| DP math | Rounding changes the clipped radius, and rounded distributed shares are not exactly a continuous aggregate Gaussian. Added sqrt(d)/(2s) sensitivity inflation and conservative n/(2m²) per-release DDP bound. | Independent epsilon/variance tests and rounding error bound; documented postprocessing proof. |
| Distributed systems | A coordinator crash after collecting all shares could precede the budget reservation. Moved reservation before broadcast. Run reservation rejects resampling/restart; failed sends and timeouts remain spent. | Durable duplicate/restart ledger tests; incomplete cohort tests; duplicate signed Kafka chunks in full state machine; real Kafka two-round checkpoint return. |
| Utility | A single seed/round may exceed 0.85 while multiseed fixed-final utility does not. No model-seed cherry-picking; complete validation-only results are retained. Best intermediate validation is descriptive and charged full scheduled releases. | Experiment manifests, seed-level/final/frontier files; August-only loader; no September dataset scoring. |
| Regression | Copying Sia's older base file initially removed Anshul's cancellation and strict validation additions. Restored the transport base model implementation (identical math) before experiments/tests. | Streaming/dashboard/recovery/receipt suite; XAI source unchanged; both graph HTML tools run on August. |

## Attack and failure audit

- Central receives only integer masked contributions in secure modes. Raw floating
  model payloads are rejected by the secure round parser. Central-DP clean means
  exist transiently inside the finalization function; no serializer or status
  callback receives them. DDP has noise before any central unmasking.
- Retained wrong-run traffic is ignored; current-run HMAC failures are rejected.
  Current-round/schema/base/cohort/roster must match. Duplicate identical chunks
  and completed-message retries never count twice. Conflicting public-key and
  contribution replacements fail.
- All cohort members must provide valid keys and updates. No partial average,
  extra participant, client substitution or plaintext fallback is implemented.
- X25519 secrets cannot be derived from server-known HMAC secrets. Different runs
  and rounds have independent ephemeral keys and KDF domains. Clients validate
  their own roster key. A malicious coordinator that forges MACs/substitutes peer
  keys is outside the stated HBC threat model.
- Failed publish returns a fatal exception after a durable reservation. A process
  restart cannot reuse the same run ID, including after partial rounds. A new run
  gets fresh keys and entropy, with previous ledger reservations composed.
- Deleting/rolling back the local ledger or selecting another output directory
  defeats local budget history. Back up/access-control ledgers operationally.
  No remote tamperproof ledger/monotonic hardware counter is claimed.
- A malicious zero-noise bank is not detected. All configured banks are assumed
  protocol-following noise contributors. Incomplete cohorts fail closed; collusion
  and Byzantine robustness are not claimed.
- Nonprivate sample-weighted legacy mode necessarily reveals public sample counts.
  Private profiles disallow it and emit no sample counts, losses, per-bank norms,
  replay contents, Gaussian vectors, keys or mask seeds. Bank identities, cohort,
  round timing, payload sizes, public keys and released model hashes are visible.
- Safetensors prevents unsafe tensor deserialization. Existing trusted checkpoint
  loading was tightened to weights-only loading with inert pathlib metadata;
  arbitrary pickle execution is not required for external existing checkpoints.
- Finite-precision Box-Muller is not an exact Gaussian sampler with a machine-level
  zCDP certificate. Mathematical budget statements require the ideal Gaussian
  model; no exact production DP claim is made. See the architecture's sampler caveat.
- Public feature encoders, calibration, validation and disclosed nonprivate
  references limit the scope of end-to-end privacy. No finite total DP guarantee
  is claimed for this entire research artifact collection.
