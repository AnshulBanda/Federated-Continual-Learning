# Final AML dashboard integration — 28 October 2026

Validated on `xai/explanation-ux-v2`, based on main `6db498730f36f112ea89d183b4bec6b1178f80f7`.

The existing `streaming.app.dashboard` entrypoint now serves the approved investigator renderer inside Explanations. It uses scoped component CSS, the same deterministic summary translator and graph interactions, and a replay-specific operational adapter. There is one global header and navigation shell; no iframe, standalone server dependency, LLM, or alternate checkpoint fallback.

The global H1 is **FCL for Anti-Money Laundering**. The browser title is **FCL for Anti-Money Laundering | Review workspace**. Final sidebar sections, in order:

1. Overview
2. Data & training
3. Collaboration
4. Transactions
5. Results & history
6. Weight transfers
7. Explanations

The obsolete Privacy & transfers frontend panel, navigation and dedicated rendering code were removed. Backend privacy APIs, accounting, ledgers, SecAgg, collaboration status and Kafka metadata remain available. Collaboration visibly retains **Level-3 Distributed DP + Secure Aggregation**.

## Exact replay model and evidence

Transactions → completed replay → Explain score opens the same transaction inline without another search. Browsing other completed replays remains available in a collapsed selector. The independent saved replay selection is checked against the returned report's bank, transaction, replay, data fingerprint, model SHA, model family, member count, privacy scope, score and cutoff. Bank changes and superseded asynchronous requests cannot render an older report.

The adapter loads the existing operational selected-model runtime. The reference path explains the arithmetic mean of all three members' probabilities, preserving each member's own pre-batch account memory. The private path reads the retained seed-42 single-model checkpoint and validates its canonical manifest. Compatible verified selected nonprivate models use the same operational runtime. Unsupported or incomplete private contracts fail closed.

Saved, direct and explanation scores must agree within **1e-6**. Report retrieval revalidates model files, data, saved rows, implementation hashes and cache identity. Legacy reports cannot silently substitute for this evidence. Real report copies were probed with wrong replay/model identities and a `1.5e-6` score mismatch; every probe was refused. Unit tests also verify acceptance at `0.5e-6`.

Grouped attribution uses 32 training background rows and fixed pre-batch account memory. Historical tests suppress up to eight eligible earlier updates within eight completed batches, separately in every actual member, with pre-window memory retained. Unperturbed member replay must pass the same parity guard. Observed history outside that test window remains explicitly untested. Patterns describe observed relationships rather than causes. Counterfactual crossings use tested scores and the saved cutoff. Stability is honestly marked unrecorded.

Technical A–I evidence, exact attribution arithmetic, faithfulness, bounded replay, graph details, counterfactuals, verification, provenance and nested raw JSON remain behind the initially collapsed in-depth disclosure. Local explanations do not inherit a checkpoint's DP guarantee.

## Validation

| Check | Result |
|---|---|
| XAI Python unittest suite | 35 passed |
| Node frontend suite | 41 passed (29 approved + 12 integration) |
| Full main pytest suite | 178 passed, 39 subtests passed |
| Privacy/transport pytest | 19 passed |
| Secure Aggregation smoke | PASS; exact ring cancellation; dimension 242561 |
| JavaScript syntax | Shared renderer, translator, integration controller and inline dashboard scripts passed |
| Whitespace | `git diff --check` passed |

Logs, seven complete actual-model reports, deliberate mismatch probes, protected-file hashes and browser measurements are in [review/final-dashboard-integration](review/final-dashboard-integration/).

Live review used the full dashboard at `http://127.0.0.1:8767/` with isolated state `.local/final-dashboard-integration`. Existing user dashboard sessions on other ports were preserved. The retained production descriptor was copied into this review state's selected-model record, with an absolute checkpoint path and the operational default cutoff 0.5, solely to exercise private inference. No model training, production DP noise, federation run, broker mutation or checkpoint modification was performed.

| Bank / transaction | Actual model | Saved score | Saved cutoff | Reviewed evidence |
|---|---|---:|---:|---|
| Wells Fargo / 2954161 | Reference ensemble | 0.21664444357156754 | 0.2648376809991874 | Non-flagged; no history; tested crossing |
| Wells Fargo / 2788586 | Reference ensemble | 0.9104695518811544 | 0.2648376809991874 | Flagged; observed untested history; fan-out |
| Wells Fargo / 2965480 | Reference ensemble | 2.598657305637649e-7 | 0.2648376809991874 | Eight verified history tests; tiny measured effects |
| JPMorgan Chase / 180245 | Reference ensemble | 0.028827516090435285 | 0.018216599960190167 | Flagged; verified lowering history; false positive |
| JPMorgan Chase / 66943 | Reference ensemble | 0.0009164763784307676 | 0.018216599960190167 | Non-flagged; three raising history effects; chronological cycle |
| JPMorgan Chase / 3008974 | Reference ensemble | 0.4320921003818512 | 0.018216599960190167 | Flagged; fan-in; independent fraud label |
| Wells Fargo / 2954161 | Retained private single | 0.14525170624256134 | 0.5 | Exact private checkpoint and Level-3 scope; no fallback |

Maximum observed saved-versus-target discrepancy across these cases was `4.7199375380335695e-8`, below `1e-6`. The same transaction's different reference/private scores demonstrate that model context is preserved.

Fourteen screenshots cover the full dashboard shell, flagged/non-flagged cases, no history, verified history, fan-in/fan-out/cycle, technical evidence, private replay workflow, Overview, Collaboration and responsive layouts. Browser console warnings/errors were empty. There was no page-level horizontal overflow at desktop, 900px or 390px. Desktop hero widths were approximately 57.4% network / 42.6% explanation. At 900px and 390px the explanation appeared above the network. The existing phone navigation has its own horizontal scroll area. Graph selection and Enter activation worked, and periodic polling preserved the selected graph item and disclosure state.

## Preserved pipeline and private result

Protected source and artifacts were byte-compared with main `6db4987`; recorded hashes are in `protected-files.json`. Canonical DP, model runtime, training, privacy, collaboration, schema, retained descriptor and checkpoint are unchanged. Other than replay identity metadata, replay scoring is unchanged. Kafka/ZeroTier broker `10.30.127.124:9092`, manual transfer controls, start/stop/cancel and results history remain in the existing shell and backend.

The canonical private protocol remains one seed-42 CausalTemporalGraphSAGE, 65,793 private decoder coordinates, three banks, four rounds, three local epochs, C=0.875, multiplier=0.30, delta=1e-6, distributed DP, mandatory SecAgg and noisy-only FedAvg server learning rate 0.1, with no plaintext fallback. Retained macro August PR-AUC is `0.9135646317452175`; retained per-run epsilon is `127.36375184207253`, delta `1e-6`. The SecAgg smoke dimension above belongs to that script's independent test vector and does not change the private decoder dimension.

Pre-existing modified/untracked standalone XAI runtime cache files under `xai/outputs/` were preserved and excluded from the integration commit.
