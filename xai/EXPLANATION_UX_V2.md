# Investigator explanation UX v2 — review record

The dashboard now answers why a selected transaction was flagged using measured feature contributions, before exposing the network or technical evidence. Text is deterministic; no LLM generates explanations. This is a presentation redesign of the existing XAI engine, with additive evidence retention and stricter cache/response checks.

## Git scope

- Branch: `xai/explanation-ux-v2`.
- Starting latest `origin/main`: `6db498730f36f112ea89d183b4bec6b1178f80f7`.
- Fetched with `GIT_LFS_SKIP_SMUDGE=1 git fetch origin --prune` before branching.
- Only commit unique to `origin/shuchika-xai`: `44c6b23` (Fix XAI explanation cache and dashboard copy), cherry-picked as `9860367`. No wholesale merge.
- All changes are under `xai/`. Canonical DP training, model files, thresholds, and main are untouched. Only the new branch is pushed. The final review SHA is reported in the chat and can be resolved with `git rev-parse HEAD`; it is deliberately not embedded in its own commit.

## Files and boundaries

| File | Change |
| --- | --- |
| `static/explanation_summary.js` | Pure translation from measured evidence into a structured summary; ranking, strength labels, verified history, patterns, actual counterfactual crossings, model scope and independent evaluation labels. CommonJS and browser entrypoints share the same implementation. |
| `static/dashboard.js` | Separate simple, network and technical renderers; exact evidence tables; active-model and strict score validation; request sequence guards retained. |
| `static/dashboard.html`, `static/dashboard.css` | Summary-first layout, prominent in-depth link, secondary network disclosure, All transactions filter, mobile summary placement and bounded evidence layout. |
| `serve_dashboard.py` | Serves the translation module; checks cache body identity, model, preprocessing, exact cutoff and saved/direct/target score agreement. Existing engine checks remain. |
| `src/transaction_story.py` | Retains every earlier eligible transfer in the existing bounded story scope separately from the graph's display limit. No graph selection or replay calculation changes. |
| `src/counterfactuals.py` | Retains every already-tested amount candidate and its score. Candidate generation, scoring, crossing decisions and selection order are unchanged. |
| `src/dataset_view.py` | Isolated runtime restoration of the exact originally hashed LF/CRLF manifest bytes. All original input hashes remain enforced; checkout data and saved preprocessing artifacts are not rewritten. Any other manifest difference fails closed. |
| `tests/test_dashboard_frontend.cjs` | Existing regression scenarios retained with new UI assertions, plus deterministic summary, directions, ordering, boundaries, provenance, disclosures, crossing, label and nonfinite-value checks. |
| `tests/test_dashboard_cache.py`, `tests/test_dataset_view.py`, `tests/test_transaction_story.py`, `tests/test_xai_extensions.py` | Cache identity/parity, manifest hash preservation, all eligible history retention and all tested amount candidate retention. |
| `README.md`, `EXPLANATION_UX_V2.md`, `review/explanation-ux-v2/` | Usage, review findings, screenshots, measured evidence, generated summaries and test results. |

Existing reference artifacts under `outputs/updated/` are not changed in this commit. Regenerated runtime reports were copied into the review folder as evidence, then the tracked reference artifacts were restored.

## Exact simple structure

`ExplanationSummary.summarize(report)` returns:

```text
{
  decision: { flagged, score, threshold, margin },
  primary_reason: { feature, direction, contribution, label, observed,
                    strength, relative_size, effect, sentence },
  top_factors: [up to three measured groups with the same factor fields],
  history_summary: { status: none | untested | tested, strongest,
                     tested_count, sentence },
  patterns: [{ label, description }],
  counterfactual_summary: { alternative, crossed, available_count,
                           sentence, note },
  model_scope,
  evaluation: { label, status }
}
```

If no feature group has a non-negligible contribution in the decision's direction, the primary reason has `feature: null`, a neutral direction and an explicit evidence-limited sentence. It never substitutes the threshold rule for a feature explanation.

Display order:

1. Transaction identity and observed transfer; prominent in-depth link.
2. Flagged / not flagged; score, bank cutoff, signed margin and model scope.
3. Main reason: strongest positive group for flagged, strongest negative for unflagged. Earlier-activity and observed-pattern summaries appear immediately beneath it.
4. Top three absolute feature contributions, arrows, observed values and relative strength. Strong ≥67%, Moderate ≥33%, Small = remaining non-negligible effect relative to the largest absolute contribution. The help text explicitly says these are visual comparisons, not probabilities.
5. Strongest verified earlier-history test, with/without scores and a control to all tested transfers; distinct no-history and untested-history states.
6. Fan-in, fan-out and chronological-cycle descriptions, with observed-only limitations.
7. Constrained amount sensitivity result, actual current/alternative decisions if a crossing is verified, and the transaction-behavior disclaimer.
8. Independent dataset evaluation label and model outcome, uncalibrated-score explanation.
9. Collapsed transaction network, then collapsed in-depth explanation.

The simple view exposes no SHAP, logits, SHA-256 or JSON. Scores are rounded for display; small nonzero scores/margins use scientific notation rather than rounding to zero. Decisions always use full precision. No calibrated fraud probability, account ownership, transaction purpose, criminal intent, causal graph claim or proof of fraud is generated.

## Exact in-depth structure

The prominent link opens the same initially collapsed disclosure as **View in-depth explanation**:

- **A. Exact decision:** full-precision saved score, bank-specific threshold, exact signed margin, exact model class, independent evaluation label and threshold source.
- **B. Feature attribution:** grouped empirical/interventional SHAP, training background, fixed account-memory scope, every group and observed value, exact signed logit contribution, one-group perturbation, base/target/reconstructed logits, additivity residual, reconstructed/target score and equation. Background IDs/grouping have an additional disclosure.
- **C. Feature faithfulness:** existing perturbation evidence; average coalition contribution and one-group replacement explicitly answer different questions.
- **D. Historical replay:** every earlier transfer retained in the existing eligible bounded scope; tested/untested status, exact with/without/delta and retained-memory scope; full temporal evidence and graph fidelity. Replay is explicitly not GNNExplainer or evidence of purpose/fraud.
- **E. Graph / network details:** selected/earlier transactions, dataset account IDs, model node IDs, timestamps, amounts, method, observed patterns, important nodes/edges and limitations.
- **F. Constrained counterfactuals:** all retained tested amount alternatives, exact resulting scores, validity, actual crossings and constraints. Legacy reports explicitly state if they only retained successful alternatives.
- **G. Verification:** saved/direct/XAI scores, allowed tolerance, pass/fail, grouped target score, faithfulness, stability, temporal replay, coverage, engine evaluation/configuration and the strict `1e-6` guard. Missing diagnostics are not presented as passes.
- **H. Model provenance:** family, seed, count, round, exact model/preprocessing/source/reference hashes, evaluation split, threshold policy, privacy scope, engine provenance and limitations.
- **I. Raw audit record:** the complete report JSON behind a further initially collapsed **View raw audit record** disclosure.

The network retains clickable and keyboard-accessible accounts/transfers, selected/observed/tested distinctions and fan-in/out/cycle labels. Its graph is secondary to the written explanation.

## Model and numerical scope

This catalog explains one selected Sia adaptive federated checkpoint, seed 42, round 4. The UI truthfully labels it **Non-private reference model**. It is not an assertion that the catalog explains the canonical private finalist or the separate reference ensemble. An explicit supported Level-3 scope maps to **Level-3 DP federated model**; missing/unrecognized scope remains unknown. Neither local explanations nor exported account histories inherit a model DP guarantee.

Grouped attribution, fixed references, chronological replay, model/account mapping, threshold policy, checkpoint staging, comparison engines and source-less engine bytes remain intact. Strict DP target-wrapper parity handling remains unchanged and is tested. No DP support is fabricated.

The one runtime portability repair was necessary on macOS: all bank input files matched their saved hashes, while `model_feature_columns.json` differed only by LF versus CRLF bytes. A temporary dataset view restores the bytes whose SHA-256 exactly matches the saved artifact. It does not accept merely equivalent JSON, refit preprocessing, replace a saved hash or modify canonical data.

## Visual review on 28 October 2026

All cases below were served by the real local dashboard at port 8766, from verified model evidence. Screenshots and DOM checks are in [the review folder](review/explanation-ux-v2/). These are not mocked explanations.

| Required scenario | Bank / transaction | Screenshot |
| --- | --- | --- |
| False positive; no eligible earlier history | Wells Fargo 2954161 | `false-positive-no-history-desktop.png`; narrow view `false-positive-no-history.png` |
| True positive; untested history; fan-out | JPMorgan Chase 2580817 | `true-positive-untested-fan-out.png` |
| True positive; fan-in | JPMorgan Chase 3008974 | `true-positive-fan-in.png` |
| True negative | Wells Fargo 2965480 | `true-negative.png` |
| Missed fraud | Wells Fargo 2794670 | `missed-fraud.png` |
| Verified positive history effect | Key Bank 2974317 | `verified-positive-history.png` |
| Verified negative history effect; fan-out | JPMorgan Chase 180245 | `verified-negative-history.png` |
| Chronological cycle | JPMorgan Chase 66943 | `chronological-cycle.png` |
| Keyboard-operated tested graph edge | JPMorgan Chase 66942 in 66943's network | `network-tested-transfer.png` |
| Full-precision technical evidence | JPMorgan Chase 66943 | `technical-explanation.png`; `historical-replay.png` |

Human-style review found that the first layout placed history too far down. The header, decision cards and factor layout were compacted, and history/pattern summaries moved beside the main reason. At the reviewed desktop size, all six investigator questions can be answered from the first viewport. At 319px width, the selected explanation moves ahead of the transaction picker, with a link back to it. Exact nested evidence initially overflowed; nested definition lists were corrected. Final default and expanded technical views have no horizontal document overflow. No console warnings/errors were recorded.

Graph keyboard activation, the in-depth link, the all-tested-history control and the nested raw-audit control were exercised. Network, technical and raw disclosures start closed for every reviewed case. This is a qualitative UX review, not a timed study with independent investigators.

## Generated examples

- Wells Fargo 2954161: **Flagged for review**, score `0.2051`, cutoff `0.1869`, margin `+0.0183`. “The payment method was the strongest measured factor pushing the model score higher.” Observed ACH; amount/currencies pushed lower. No eligible earlier history. Dataset label Not fraud / False positive stays separate.
- Key Bank 2974317: “TX 2627867: this earlier transfer helped push the current score higher.” With history `0.4101`; without the update `0.2704`. It is a verified replay result; the explanation makes no claim of fraud or payment purpose.
- JPMorgan Chase 180245: “TX 180238: this earlier transfer helped keep the current score lower.” With history `0.0862`; without the update `0.2785`. Fan-out across four displayed counterparties is described separately as an observed relationship.
- Wells Fargo 2794670: **Not flagged**, score `0.0340`, margin `−0.1529`; “The amount and currency combination was the strongest measured factor pushing the model score lower.” Dataset label Fraud / Missed fraud remains distinguishable.

Full structured summaries and their source reports are retained in `generated-summaries.json` and `cases/` under the review folder.

## Regression results

Runtime: isolated CPython 3.12.16, torch 2.14.1, numpy 2.5.4, pandas 3.1.0; the repository's original environment is Python 3.13, while the preserved engine requires CPython 3.12. Review environment lives only under ignored `tmp/xai-ux-venv`.

| Check | Result |
| --- | --- |
| `python -m unittest discover -s xai/tests -v` | **35 passed** (CPython 3.12); preserved engine integrity and strict DP parity tests included |
| `node --test xai/tests/test_dashboard_frontend.cjs` | **17 passed** |
| `python xai/evaluate_xai.py` | **16 real cases**, **49 independently replayed historical interventions**; saved cutoffs and frozen artifact lineage checked |
| Maximum grouped target / saved score error | `7.81343665323675e-08`, below unchanged `1e-6` |
| Maximum independent replay error | `1.1102230246251565e-16` |
| Maximum logit additive residual | `1.9073486328125e-06` (the existing logit reconstruction check is separate from the strict score-parity guard) |
| Feature perturbation agreement | 31 / 32; differing SHAP/replacement direction remains visible as measured evidence |
| Reference stability | Largest group stable in 15 / 16 cases; all group directions stable in 12 / 16. No claim of universal stability |
| Browser review | Eight actual transactions cover every requested scenario; collapsed defaults, no overflow or console errors, graph/history/technical/raw interactions verified |
| JavaScript syntax | Both scripts pass `node --check` |
| `git diff --check` | Pass |
| Canonical pipeline / main | No changes; no merge and no push to main |

Detailed results: `python-tests.txt`, `frontend-tests.txt`, `evaluation.json`, `browser-checks.json`, `interaction-checks.json`, and `validation.json` in the review folder. No additional repository-level regression was required because all edits are confined to XAI and its documentation/evidence.
