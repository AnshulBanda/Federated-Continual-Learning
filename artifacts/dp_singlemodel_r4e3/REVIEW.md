# Local repair review

Separate review passes by the implementing agent; no external review or subagent
review is claimed.

1. **Architecture:** one unprefixed CausalTemporalGraphSAGE, exact fixed seed42
   warm weights, decoder65793 coordinates and frozen backbone176768. No private
   ModuleDict or probability averaging. Experiment seeds52/62 reload the same
   seed42 warm checkpoint. Private ensemble activation is rejected at parser,
   runtime, transport and model-selection boundaries.
2. **Training/search:** four rounds, three epochs per phase and three banks are
   unchanged in every candidate. Three training-only calibration tracks and seven
   screens plus four robustness runs respect the bounded plan. Round4, never best
   intermediate round, is the endpoint. Mean.913431321341024, SD.010928024189602,
   worst.904442638911888. Server attenuation is positive and all steps are nonzero.
3. **Privacy mathematics:** four m=.30 releases give rho66.66666666666667,
   epsilon127.36375184207253 at delta1e-6, matching old one-release m=.15. Global
   decoder clipping, quantization sensitivity, independent bank noise and the
   conservative encoded-share accountant are unchanged. Noisy-only FedAvg lr.1
   is postprocessing, not a privacy-budget discount. Research entropy/calibration
   and August disclosures remain explicitly nonprivate.
4. **Crypto/transport:** X25519, HKDF-SHA256, ChaCha20, uint64 ring, full roster,
   context checks, stale/conflicting duplicate rejection and durable ledgers stay.
   No normal client_update occurs. Private coordinator tests forbid individual
   model deserialization and plaintext temporal harmonization. Four real masked
   ring sums plus public server postprocessing reconstruct the returned model.
5. **Operational acceptance:** actual Collaboration/controller/runner workers
   use real Kafka, exactly three masked65793 contributions per round, all four
   rounds, identical verified returns on every bank and unchanged backbone.
   Missing-bank run aborts before training with no fallback. Private-single topics
   isolate other checkout traffic. The initially stopped broker was restored to
   stopped; no other process/container/checkout was changed.
6. **Evidence/leakage:** same canonical dataset, no downloads, copies, regeneration
   or LFS fetch/pull. Calibration reads training only; search/scoring read training
   and August. No canonical September/testing transactions are loaded. All3190
   historical artifact hashes remain unchanged, including both old headline
   results and discarded ensemble evidence. Production source15 hashes match.
7. **Dashboard/reference preservation:** reference ensemble stays nonprivate and
   uses all three original frozen members. Its training UI and scoring/XAI remain.
   Private single selection/loading/scoring is added separately. Private inference
   returns one probability stream without averaging. No inherited reference score
   is displayed as private performance. Sensitive private diagnostics stay off
   the API/wire; scalar diagnostic metadata is local research evidence only.
8. **XAI/regression:** core170 +35subtests, PythonXAI26, frontend9, privacy26 and
   exact-ring smoke pass. Live reference XAI has zero prediction error; private
   single error1.6013934733827284e-8. Both reject1.5e-6 mismatch under unchanged
   1e-6 guard. Legacy bytecode adapter requirements/guards are unchanged.
9. **Git/security:** local experiment branch only, no push to any remote, no main
   switch/merge or changes to existing branch refs. Runtime secrets/private keys,
   masks/noise vectors, ledgers and worker logs are not staged. Only reviewed code,
   scalar research evidence and global released/noisy research checkpoints are
   committed locally. Dataset files and transaction rows are not staged.

Remaining limits: conditional nonprivate warm/calibration scope; ideal-Gaussian
accounting with finite-precision computational sampling; high inherited epsilon;
honest-but-curious noncolluding threat model/shared-team authentication; no
app-configured Kafka TLS; only three research seeds and one production draw;
validation rather than untouched-test evidence; no remote ZeroTier test.
