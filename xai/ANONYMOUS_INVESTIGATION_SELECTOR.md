# Anonymous banks and investigation selector

Implemented on `xai/explanation-ux-v2`, starting from merged main `af2748e04906a3fb02474ac0afe9dc6968de57d3`. Main is intentionally unchanged by this follow-up.

## Display aliases

The single shared helper is `xai/static/bank_display.js`, used by the operational dashboard and shared XAI renderer:

| Internal identifier | Display label |
|---|---|
| `Key_Bank` | Bank A |
| `Wells_Fargo` | Bank B |
| `JPMorgan_Chase` | Bank C |

Canonical values remain in options, requests, dataset paths, configuration, model descriptors, cache identities and saved provenance. Only presentation text changes. The helper also anonymizes newly rendered legacy status messages, roster names, errors, logs, accessible tooltips and audit displays before paint. It excludes script/style contents, input/option values, IDs, URLs, data attributes and payloads. The raw-audit disclosure explains that displayed bank aliases leave saved provenance unchanged. Historical research/evidence files were not rewritten.

## Investigation workflow

Explanations now provides five dropdowns: Bank, Completed replay / model, Model result, Actual dataset label, and Transaction. Defaults are Flagged for fraud, All actual labels, and the highest-scoring available flagged transaction. All matching transactions appear without a cap. Flagged/all results sort by descending saved score; non-flagged results sort ascending; ties use transaction ID. Empty selections show **No transactions match these filters.** and disable explanation submission.

The new read-only `/api/explanations/cases/<replay>` endpoint joins independent validation labels to the selected completed replay in memory. It checks replay identity and dataset fingerprints before and after reading labels. Missing, duplicate, nonbinary or mismatched labels fail closed. It does not alter the saved transaction feed, scores, cutoff, labels used by inference, or model provenance.

Model result uses only the saved score and cutoff. Actual-label filtering remains independent. A single **Explain selected transaction** action loads the selected report and collapses the selector to keep the approved graph/explanation hero prominent. Reopening the selector retains synchronized filters and transaction choices. Transactions → Explain score still opens the exact scored transaction directly. Bank, replay, transaction or filter changes hide incompatible evidence; old asynchronous responses cannot overwrite the selection.

The top comparison card displays TRUE POSITIVE, FALSE POSITIVE, TRUE NEGATIVE or MISSED FRAUD, derived from the existing deterministic presentation summary. It explicitly states that dataset labels did not determine the prediction. Existing attribution, history replay, patterns, counterfactuals, exact scores and A–I technical disclosures remain intact. Model/replay identity and the **1e-6** parity guard remain strict; an additional check binds the report to the independently selected dataset label.

## Tests and live review

| Check | Result |
|---|---|
| XAI frontend regressions | 54 passed |
| XAI Python unittest suite | 35 passed |
| Full main/dashboard pytest suite | 186 passed, 45 subtests passed |
| Focused selector/dashboard Python suite | 16 passed, 6 subtests passed |
| JavaScript syntax and `git diff --check` | Passed |

The full dashboard ran at `http://127.0.0.1:8767/` using isolated review state `.local/final-dashboard-integration`. Live dropdown-only reviews covered:

| Bank | Transaction | Model | Case |
|---|---|---|---|
| Bank A | 3262326 | Reference ensemble | True positive |
| Bank A | 3135307 | Reference ensemble | False positive |
| Bank A | 3538025 | Reference ensemble | True negative |
| Bank A | 3007762 | Reference ensemble | Missed fraud |
| Bank B | 3400471 | Retained private single | True positive |
| Bank B | 2794670 | Reference ensemble | Missed fraud |
| Bank C | 3400463 | Reference ensemble | True positive |
| Bank C | 3565491 | Reference ensemble | False positive |

Bank C has no missed fraud in this replay; its genuine empty state was checked. Bank A's non-flagged/not-fraud dropdown contained all 11,391 matching transactions. Changing Bank B's replay switched between the retained private model's 0.5 cutoff and the reference replay's 0.2648376809991874 cutoff, with refreshed choices. Exact model verification passed for all eight reports.

All seven operational sections were audited without visible real bank names or undefined/NaN values. Expanded technical/raw disclosures also contained only display aliases. Enter-key graph inspection worked. At phone width, the selector and hero had no page-level horizontal overflow; the explanation remained above the network. One unsupported-media browser event was recorded during the initial reload, before the reviewed replay started; there were no further warning/error events through the tested flows. The page has no audio/video elements. Fourteen captured screenshots were visually reviewed.

Evidence, test logs, browser measurements, actual report parity checks and inventories are in [review/anonymous-investigation-selector](review/anonymous-investigation-selector/).

## Preserved implementation

Ninety-five protected source/config/checkpoint files were byte-compared with main `af2748e`; their hashes are recorded in `protected-files.json`. Training, canonical DP, epsilon/delta, clipping, mandatory SecAgg, Kafka, ZeroTier, replay scoring, thresholds, checkpoints, attribution, history replay and counterfactual calculations are unchanged. No training, federation run or production DP noise was performed. The retained private result and privacy accounting remain unchanged.

Pre-existing standalone runtime-cache modifications under `xai/outputs/` were preserved and excluded from this work.
