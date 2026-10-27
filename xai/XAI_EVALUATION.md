# XAI improvements and evaluation

This report supersedes the legacy field-attribution findings in XAI_AUDIT.md. The detector checkpoint and bank cutoffs were not changed.

## Implemented

- Exact grouped empirical interventional SHAP: payment method is one group; amount sent, amount received, sending currency and receiving currency are one joint group. Reference values always come from one real training row; target account metadata stays fixed.
- Observed values, signed logit contributions, method, additive baseline, and fixed-memory scope are visible. Separate amount and currency effects are no longer claimed.
- Global-model seed and checkpoint are visible. No ensemble averaging is used by this dashboard.
- Clickable and keyboard-accessible accounts/edges open a detail panel. A colour legend distinguishes supporting, lowering, negligible, untested and selected edges. Replay coverage, before/after scores, retained pre-window memory and non-fraud-proof limitations are visible.
- Deep links select All transactions, check exact response identity, and reject unknown banks. Bank switching clears stale search and selected transaction.

## Numerical consistency

12 diagnostic cases across all three banks: cached cases plus available detected-fraud, false-alarm and legitimate-non-alert strata.
Maximum additive reconstruction error: 0.0000004470 logit.
Maximum displayed probability error: 0.0000000749.

## Reference stability

Three independently sampled training backgrounds of 32 rows per case; seeds 42, 52 and 62. These are explanation-reference seeds, not model ensemble members.

| Bank | Transaction | Largest group stable | Group directions stable |
|---|---|---|---|
| JPMorgan_Chase | 180245 | True | True |
| JPMorgan_Chase | 2580817 | True | True |
| JPMorgan_Chase | 3400462 | True | True |
| Wells_Fargo | 2794670 | True | False |
| Key_Bank | 2974317 | False | True |
| JPMorgan_Chase | 2912559 | True | True |
| JPMorgan_Chase | 2952760 | True | True |
| Wells_Fargo | 2788586 | True | False |
| Wells_Fargo | 2961223 | True | True |
| Wells_Fargo | 2965480 | True | False |
| Key_Bank | 3007764 | True | True |
| Key_Bank | 2928144 | True | True |

The largest group changed for Key Bank 2974317. Group direction changed for Wells Fargo 2794670, 2788586 and 2965480. Therefore reference stability does not pass uniformly; case-specific warnings are shown. This is a small stratified diagnostic, not a population estimate.

## Perturbation faithfulness and temporal replay

Joint-group reference replacement agrees in direction with SHAP for 23 of 24 group/case checks. The transfer-terms group in transaction 3400462 disagrees. SHAP averages across combinations, while that replacement conditions on other actual values, so they answer different questions. A warning is shown for disagreement.
Independently replayed 46 historical interventions in editable source, plus each unperturbed baseline. Every probability agrees with the original replay results within 0.000001.
Replay coverage: 32 of 51 displayed historical edges have verified measured effects. Other edges are context, not evidence of model influence.

## Frozen detection performance (separate from XAI)

Existing one-time September evaluations were reused after verifying checkpoint, metrics hashes and exact saved validation cutoffs for all seeds. Test inference was not repeated and no cutoffs or models were changed. These artifacts explicitly classify September evaluation as exploratory because September had been inspected earlier in project development. An untouched later period is still needed for independent confirmation.

| Seed | Bank | Precision | Recall | F1 | PR-AUC | Alerts | False positives |
|---|---|---|---|---|---|---|---|
| 42 | JPMorgan_Chase | 0.174312 | 1.000000 | 0.296875 | 1.000000 | 109 | 90 |
| 42 | Wells_Fargo | 0.750000 | 1.000000 | 0.857143 | 0.984264 | 32 | 8 |
| 42 | Key_Bank | 0.941176 | 0.711111 | 0.810127 | 0.810559 | 34 | 2 |
| 52 | JPMorgan_Chase | 0.190000 | 1.000000 | 0.319328 | 0.896793 | 100 | 81 |
| 52 | Wells_Fargo | 0.718750 | 0.958333 | 0.821429 | 0.972131 | 32 | 9 |
| 52 | Key_Bank | 0.896552 | 0.577778 | 0.702703 | 0.746732 | 29 | 3 |
| 62 | JPMorgan_Chase | 0.213483 | 1.000000 | 0.351852 | 0.868296 | 89 | 70 |
| 62 | Wells_Fargo | 0.833333 | 0.833333 | 0.833333 | 0.907806 | 24 | 4 |
| 62 | Key_Bank | 0.954545 | 0.466667 | 0.626866 | 0.652201 | 22 | 1 |

Alert counts are recovered from the archived exact threshold precision/recall and recall-at-k integer counts; provenance and checks are in the JSON results.

## Checks and reproduction

- 23 unit tests passed, including joint reference coherence, target metadata preservation, additive reconstruction, reproducible references, nonfinite-output rejection and existing graph checks.
- JavaScript syntax and Python compilation passed.
- Live browser: JPMorgan 180245 score/cutoff/SHAP/stability; tested-edge label click and keyboard inspection; untested edge; account selection; Wells Fargo bank selection and search reset; legitimate non-alert deep link 2965480 verified against catalog and detail.

Reproduce numerical evaluation: `.venv/Scripts/python.exe xai/evaluate_xai.py`.
Run unit tests: `.venv/Scripts/python.exe -m unittest discover -s xai/tests`.
Measured JSON: `outputs/updated/adaptive_federated/seed_42/xai_evaluation.json`.

Numerical consistency, perturbation agreement and reference stability are separate. None establishes actual fraud or compensates for detector false positives.

Final browser validation also passed for Key Bank 2974317 (score 0.41010210, cutoff 0.37591952), its reference-ranking warning, and supporting edge 2627867 (without-update score 0.27039180). No console errors were captured on the final third-bank page. Responsive graph layout was visually inspected. Evidence: `outputs/updated/adaptive_federated/seed_42/browser_checks.json` and the saved PNGs.

## Presentation simplification

The default view now leads with the decision and plain-language findings, ranked contribution bars, and a with/without summary of the strongest measured historical effect before the graph. Main-view scores and cutoffs use four decimals; model decisions still use unrounded values. Exact attribution values, original eight-decimal scores, method, reference selection, stability diagnostics, replay limits, threshold policy and checkpoint provenance remain under Technical methods and verification. Material uncertainty is also summarized in plain language in the main view. Graph labels now say Raised the score (tested), Lowered the score (tested), Little or no change (tested), Connection only / not tested, and Transaction being explained.

Verification: JavaScript syntax passed. Browser checks verified both Key Bank 2974317 (two upward feature groups and a supporting historical transfer) and JPMorgan Chase 180245 (lowering amount/currency and historical effects). The expanded technical section retained 0.41010210 / 0.37591952 and exact attribution/replay values; it starts collapsed. Graph inspection remained functional and no console errors were captured. No detector parameters, cutoffs or attribution calculations changed. Preview: `outputs/updated/adaptive_federated/seed_42/dashboard_simplified.png`.

## Transaction consistency and empty-state fixes

Feature directions were verified against the selected report, not hardcoded. For Wells Fargo 2954161, payment method is +1.41181345 logit and joint amount/currencies is -0.03490890; its eligible earlier-history count is zero. Wells Fargo 2961223 instead has a positive joint contribution of +0.72046956, confirming that direction legitimately differs by transaction.

The UI now validates response bank/transaction, selected graph edge details, actual observed payment/amount/currency, SHAP target probability, threshold decision and historical-effect baseline/arithmetic before displaying an explanation. Catalog requests have a sequence guard to prevent an older bank response overwriting the current threshold. The threshold is labelled configured and validation-selected. Observed values are explicitly labelled. History absence and untested existing history have distinct messages; no history table or empty effects table is rendered for an empty state.

Six frontend regression tests pass (`node --test xai/tests/test_dashboard_frontend.cjs`), including rendering every one of 13 cached reports across three banks, intentionally mixed report rejection, absent versus untested history, and out-of-order catalog/explanation responses. JavaScript syntax also passes.

Live browser transaction-selection checks passed for Wells Fargo 2954161 and 2961223; JPMorgan Chase 180245 and 2580817; Key Bank 2974317 and 3007764. IDs, scores, thresholds, numeric SHAP evidence, history states and graph edge counts agree. Graph inspection remains functional and resets on selection. No console errors were captured. The original reported Wells Fargo page was restored with the fixes. Evidence: `outputs/updated/adaptive_federated/seed_42/selection_workflow_checks.json` and `empty_history_fixed.png`.
