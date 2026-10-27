# Privacy audit by model and release scope

The **Reference Sia ensemble** is the frozen nonprivate three-member model. Its
90.68% exploratory September macro PR-AUC makes no DP claim. Ordinary bank-local
adaptation, local validation, explanations and opaque file transfers do not become
private merely because the application also supports private federation.

The **Operational federated collaboration** is a new Level-3 distributed-DP
ensemble continuation. It has separate configuration, ledger, validation evidence
and release scope. Its performance must not be replaced by either the reference
90.68% or the historical single-model decoder-private 90.281% August result.

| Control | Operational private ensemble | Reference/research scope |
|---|---|---|
| Initialization | Three frozen Sia checkpoints, hash verified | Same nonprivate warm members |
| Local training | Adaptive ensemble, 4 rounds, 3 epochs per phase, risk-context replay 2000, lr=.001 | Reference/ordinary local training is nonprivate |
| Private subset | All three decoders, 197379 actual coordinates; other tensors frozen | Full model adaptation may be used explicitly |
| Bank update clipping | One global concatenated-vector L2 clip, C=6.5 | Optimizer gradient clipping alone is not DP |
| Noise | Independent bank Gaussian shares, m=.30, production entropy, before masking | None in reference models |
| Accounting | Conservative encoded-share postprocessing; 4 releases, epsilon=127.363751842, delta=1e-6 | No DP guarantee for reference checkpoints |
| Secure aggregation | X25519/HKDF-SHA256/ChaCha20, exact uint64 ring, complete 3-bank cohort | Plaintext temporal harmonization allowed only in explicit nonprivate research |
| Kafka payload | Signed/chunked masked_ring contribution only, no losses/counts | Manual file transfers preserve arbitrary input bytes |
| Failure | Missing bank/context mismatch/duplicate conflicts abort; no plaintext fallback | No private guarantee for arbitrary research modes |
| Authentication | Existing team-shared HMAC secret | Not independent institutional identity |
| Network | ZeroTier may transport Kafka; app does not configure Kafka TLS | Network encryption is separate from model privacy |

## Private data flow

Each bank receives the entire global ensemble, completes authenticated ephemeral
key exchange, trains its three decoder members, computes one concatenated bank
delta, globally clips it and adds independent noise before masking. The retained
mechanism separately rounds the clipped delta and Gaussian share into fixed-point
ring values. It does not independently clip each member to C.

The coordinator receives authenticated public-key messages and masked bank
contributions. It sums all three in the uint64 ring and recovers only the noisy
equal aggregate. It never deserializes individual clean bank ensemble states,
recovers separate member deltas or reconstructs a clean aggregate in distributed
DP mode. It does not call `aggregate_adaptive` in the private path. The private
ensemble uses Sia's adaptive local ensemble training but replaces plaintext
temporal harmonization with secure equal aggregation because SecAgg hides
individual client directions.

## Sensitivity, accounting and scope

The privacy unit is an entire participating bank under the retained replace-one
adjacency. All three production noise contributors are mandatory. With four
releases and multiplier .30, rho = 4*3/(2*.30^2) = 66.66666666666667, equal to the
old one-release, multiplier-.15 mechanism. The fixed-point sensitivity includes
the dimension-dependent rounding bound. Conservative encoded-share accounting
retains the ideal Gaussian assumption; finite-precision sampling is not exact-DP
certified.

Each participant's durable ledger reserves before publication; the coordinator
reserves before broadcasting a round. A failed key exchange can therefore charge
a reservation even without a released aggregate. The API reports current-run
reserved spending and cumulative local-ledger scope. Across retained ledgers,
all releases compose. Deleting/rolling back a ledger invalidates that scope.

The guarantee covers incremental private continuation conditional on the
**nonprivate frozen warm ensemble and public preprocessing contract**. It is not
end-to-end DP pretraining. Training-only C calibration is a nonprivate research
disclosure, and so are validation metrics/threshold selection. Their releases
are not claimed to be covered by the model-release accountant.

## Evidence and explanations

The previous single-model DP evidence remains unchanged. New ensemble evidence,
calibration, production declaration, actual Kafka acceptance and August-only
validation are retained separately in
[artifacts/dp_level3_ensemble](../artifacts/dp_level3_ensemble/).

Transaction explanations contain scores, fields and attributions. They stay in
the local workspace and are not published through automatic federation. A strict
1e-6 prediction-parity guard remains required. An explanation of a private model
on a private transaction does not inherit a transaction-level DP guarantee.

The threat model remains honest-but-curious with a noncolluding coordinator.
This work does not add malicious-client proofs, dropout recovery, independent
institutional authentication, or app-configured Kafka TLS. Local Kafka acceptance
exercises application traffic that ZeroTier transports; it does not test remote
ZeroTier availability or cryptography.
