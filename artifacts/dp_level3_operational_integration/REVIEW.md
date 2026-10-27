# Final review passes

Each pass below was performed separately against the final code and its evidence.
No subagents were used.

1. **Pipeline integration — PASS.** Followed `Collaboration.start` through
   `RunController.start`, its allowlisted snapshot and forced `--operational-final`
   child flag, `runner.execute`, the bank/central wrappers and `privacy.transport`.
   Real subprocess acceptance used this path without replacing the trainer,
   protocol, crypto, Kafka client or model runtime. All four exit codes were zero.
2. **Privacy — PASS within the retained scope.** Exact policy requires C=1.25,
   m=0.15, delta=1e-6, three noise contributors and production entropy. Reviewed
   `client_contribution`: global decoder L2 clipping, separate fixed-point
   encoding of clipped delta and independently sampled Gaussian share, ring
   addition, then pair masking. `aggregate` has no central noise step for
   distributed_dp because bank noise is already present. Status allowlists public
   event details and excludes loss, example counts, norms and secrets. Per-run
   configured budget is explicitly distinguished from composed reservations.
3. **SecAgg/crypto — PASS.** Existing X25519 ephemeral keys, HKDF-SHA256 domain
   separation and ChaCha20 masks are unchanged. Full roster is required before
   local training and before unmasking. Tests cover malformed/substituted keys,
   context mismatch, duplicate contributions, missing peers, HMAC tampering and
   rejection of model tensors in place of the masked int64 ring. Smoke verifies
   exact uint64 cancellation for 242,561 coordinates; real final payloads have
   65,793 coordinates. This assumes the existing honest-but-curious,
   noncolluding-coordinator model; a team-shared HMAC secret is not independent
   per-bank identity authentication.
4. **Dashboard/config — PASS.** Three distinct banks, fixed round/epoch fields,
   no downgrade selector; validation repeats before spawn and in the child.
   Approved config, provenance, checkpoint and schema hashes are checked.
   Missing assets block launch. Decoder dimension is constructed from the public
   schema, without coordinator bank-data reads. Historical research modes have
   distinct labels. Saved historical client-to-bank identities are used for
   model selection after adopting the retained canonical seed order.
5. **Kafka transport — PASS.** Captured topic offsets delimit each actual run.
   Reassembled and HMAC-verified every current-run payload in those ranges. Three
   bank contributions contain only `masked_ring`, int64 bits, shape [65793]. No
   `client_update` occurred. Complete run emitted key exchange and aggregate
   return; all four checkpoint commit records verify with identical model bytes.
   Missing bank produced only public model/key exchange, TimeoutError on every
   launched role, no training, no update, no checkpoint, no fallback. The broker
   was stopped after acceptance. This tests Kafka application traffic locally,
   not remote ZeroTier availability or cryptography.
6. **XAI regression — PASS with existing guard.** 26 Python and 9 frontend tests
   pass. All 1,007 tracked XAI files match the merge checkpoint. Engine asset
   hashes and CPython 3.12 compatibility checks remain intact. No DP parity
   tolerance was changed. Live sourceless-engine inference was not run: the
   available project environment is Python 3.13, while that engine requires 3.12.
7. **Model/evidence integrity — PASS.** All 3,131 retained artifact files match
   the initial audit hashes. All 32 frozen model/training/privacy source files
   match the retained source manifest. Actual acceptance leaves frozen tensors
   unchanged and changes decoder tensors. No utility search or metric evaluation
   was rerun. Retained August macro PR-AUC remains 0.9028095494826616 with sample
   SD 0.03241549443748849. It measures private continuations from a shared
   nonprivate seed-42 warm checkpoint, not end-to-end DP or pretraining variance.
8. **Git/security hygiene — PASS.** Separate XAI merge checkpoint and operational
   commit; normal push restricted to `philip-dp-secagg-ddp`. No main checkout,
   reset, force-push or main push. Runtime secrets remain in child environments;
   no keys, seeds, payload vectors, SQLite databases or runtime model checkpoints
   are added. Evidence includes public configuration, hashes, event phases and
   test output. Local origin/main stays 18663536f62e6e3c61ca6a43c3f98651320ec9d2;
   read-only remote inspection observed main externally advance to
   f2c873e51ebf95cd07f7e7dd010284fb919749ca. That new main commit was not integrated.

Repairs from review: reject nonintegral values before parser coercion; label
historical distributed configurations with different settings as research;
preserve historical model selection using saved bank identities; update the older
acceptance command and operational docs to remove obsolete nonprivate defaults.
