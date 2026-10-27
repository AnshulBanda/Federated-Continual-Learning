# Nine separate final review passes

These are separate inspection/verification passes by the implementing agent, not
claims of external human review. No subagents were used.

1. **Latest-main preservation — PASS.** Merged 1760f95 into the DP branch with
   seven conflicts resolved by the specified model/privacy responsibilities.
   final_model.py, ensemble_training.py, monitoring.py and results.py match main.
   Frozen reference members, their provenance and metric artifacts match main.
   Latest dashboard layout, review tabs and explanation workflow are preserved.
   Older documentation that globally denied DP was scoped or reconciled.
2. **Ensemble/model correctness — PASS.** Actual ModuleDict keys 42/52/62 load
   exact frozen checkpoint values and hashes. Real decoder keys/tensor sizes
   resolve to 197379 private coordinates; the full model has 727683. The legacy
   decoder subset was not broadened. All four actual returned ensembles preserve
   all 36 frozen tensors, change all three decoders and score by mean probability.
   Local training uses Sia's member/round/client RNG rule, risk-context replay,
   3 epochs per phase, lr=.001, wd=.0001, batch1024 and negative ratio20.
3. **Privacy mathematics — PASS within conditional scope.** One global clip
   covers the complete bank ensemble delta. A test with member norms 3,4,12
   distinguishes global clipping from the invalid per-member-C interpretation.
   Four releases at m=.30 have rho=66.66666666666667, exactly the old one-release
   m=.15 rho, epsilon=127.363751842 at delta=1e-6. Encoded-share conservatism and
   quantization sensitivity are retained. Training-only C=6.5 was fixed before
   the single production run; calibration/validation are nonprivate research
   disclosures. Warm models, public schema and published calibration are fixed
   conditions, so the full research workflow is not claimed to be end-to-end DP.
4. **Secure Aggregation — PASS.** Existing X25519/HKDF-SHA256/ChaCha20 algorithms
   and uint64 ring encoding are unchanged. Roster/context/schema/base checks,
   duplicate/conflict rejection and complete-cohort checks remain. No dropout or
   plaintext fallback was added. Exact cancellation smoke passes; the sum of the
   three actual masked rings reconstructs the returned noisy aggregate in every
   production round. Individual clean bank values are never reconstructed.
5. **Kafka/ZeroTier operational flow — PASS.** Actual Collaboration.start,
   allowlisted controller snapshot, forced-policy runner and privacy transport
   subprocesses use the real broker. For each of four rounds, three HMAC-verified
   masked-only bank payloads have dimension197379 and all banks receive identical
   verified checkpoints. No client_update appears. Missing-bank acceptance fails
   before training on every launched role. The coordinator reserves one failed
   round; this is composed with the four successful reservations in separate
   evidence. Broker stopped afterward. No remote ZeroTier test is claimed.
6. **XAI regression — PASS for checked targets.** Python26 and frontend9 pass.
   Real reference and private-round4 explanations both have zero observed
   prediction mismatch. A 1.5e-6 mismatch is rejected under the 1e-6 guard.
   Reference functionality remains; legacy CPython3.12 engine guards/asset hashes
   remain. Local attribution of private transaction fields has no DP guarantee.
7. **Dashboard truthfulness — PASS.** Reference Sia ensemble remains explicitly
   nonprivate, 90.68% exploratory September. Operational collaboration has a
   separate Level-3 scope with ledger-backed current epsilon and composition.
   Historical single-model DP runs have a separate label. Fixed four-round and
   three-epoch controls and three mandatory banks prevent accidental downgrade.
   Private diagnostics are suppressed in the trainer and filtered in the API;
   no loss, sample counts, norms, private keys, mask seeds or vectors appear.
   Main's Overview chooses reference scores only for the reference model;
   private selected versions do not inherit the reference headline.
8. **Metric/evidence integrity — PASS, utility poor.** One predeclared production
   confirmation only. Round four was fixed as the primary endpoint before launch;
   no September data, utility search, seed shopping or favorable-noise reruns.
   Final macro August AP=.2171404870679732; the poor result and all trajectories
   are retained. All 3148 older evidence files match initial hashes. Both old
   headline results retain their original meanings. Ten frozen production source
   files match the predeclared hashes. Released aggregates and commit markers are
   retained; raw bank contributions and secrets are not.
9. **Git/security hygiene — PASS.** Merge and feature commits stay on the DP
   branch. Only a normal DP-branch push is authorized; no main checkout/push or
   history rewrite. Metadata-only fetch used GIT_LFS_SKIP_SMUDGE=1. Existing data
   was reused without downloads/copies. Staged artifacts are public aggregate
   models, hashes, configuration and explicit research evidence. Runtime ledgers,
   environment secrets, private keys, logs and transaction rows remain local.

Repairs from review: preserve ensemble initialization in controller snapshots; attribute historical training timestamps using the saved bank identity;
give private and historical scopes separate truthful labels; use actual ledger
reservations in status; suppress Sia's private training diagnostics; keep
plaintext temporal harmonization behind a nonprivate-only branch; strengthen the
source explanation guard to the required 1e-6; keep old metrics as historical.
