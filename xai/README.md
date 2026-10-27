# Federated AML XAI

This folder explains the Sia and DP checkpoint families against the current
temporal dataset. It keeps the supplied XAI engine (Python 3.12 bytecode) under `engine_py312/` as the
scoring core because its original `.py` files were missing from the supplied
folder. The editable runner and source modules around it add checkpoint
staging, fixed-case comparisons, constrained amount counterfactuals, privacy
auditing, and a local review dashboard. The model implementation is staged from
the exact Git ref used for each checkpoint and SHA-256 checked before inference.

The current interactive dashboard explains **one selected adaptive federated
global checkpoint** (seed-42 run by default), with its saved prediction cutoffs.
Launch it with `python xai/serve_dashboard.py`. See the dashboard section below.

## Run workflow

From the repository root in PowerShell, first finish Sia seed 42. This creates a
balanced set of two August validation transactions per bank and persists their
IDs in `outputs/updated/case_manifest.json`.

```powershell
.\.venv\Scripts\python.exe .\xai\run_updated.py --family sia_context_harmonized --seeds 42
```

Then run the comparison models. All checkpoints reuse the same bank and
transaction IDs, so explanation changes are paired rather than comparing
different examples.

```powershell
.\.venv\Scripts\python.exe .\xai\run_updated.py --family sia_context_harmonized
.\.venv\Scripts\python.exe .\xai\run_updated.py --family dp_warm_none
.\.venv\Scripts\python.exe .\xai\run_updated.py --family dp_distributed_0.001
.\.venv\Scripts\python.exe .\xai\run_updated.py --family dp_distributed_0.01
```

The families `dp_option_a_0.001`, `dp_secure_central_0.001`,
`dp_distributed_1e-5`, and `dp_distributed_1e-5_best_validation` are also
available. By default, all three seeds and banks are processed. Use `--seeds 42`
or `--banks JPMorgan_Chase` for a smaller run. Existing complete outputs are
resumed only when their checkpoint hash matches; a different checkpoint cannot
overwrite them.

The runner uses training rows for empirical SHAP backgrounds and amount
counterfactual candidate values. Inference and explanation selection use
training history plus August validation only. September/test rows are not loaded.
The cached engine requires a `testing` key in its reference artifact; this is an
empty array, and the manifest explicitly records `test_loaded: false`.

## What each case report contains

- Prediction score and threshold decision with saved-evaluation parity check.
- Exact empirical interventional SHAP in raw-logit units, plus controlled
  feature ablation/fidelity checks. Account memory is held fixed for this part.
- Descriptive temporal history and bounded chronological graph perturbations.
  The existing implementation replays selected historical updates; it is not
  GNNExplainer and does not attribute static node features.
- A constrained amount counterfactual search. Amount aliases are changed
  together; candidate values come from training rows within matching currency
  and payment-format strata when available. It reports a score threshold flip
  if one is found. It holds pre-event memory fixed, so it is a transaction-input
  sensitivity analysis rather than a new-history simulation.
- Run provenance, checkpoint and metrics hashes, privacy mode, evaluation scope,
  and a generated `privacy_audit.json`.

## Compare, audit, and review

The comparison command uses only identical bank/transaction cases and writes a
local paired CSV plus an aggregate JSON summary. The aggregate contains no
transaction IDs or bank-row detail.

```powershell
.\.venv\Scripts\python.exe .\xai\manage.py compare `
  --run sia42=xai/outputs/updated/sia_context_harmonized/seed_42 `
  --run dp42=xai/outputs/updated/dp_distributed_0.001/seed_42 `
  --output xai/outputs/updated/comparisons/sia_vs_dp
```

Build a static, local dashboard for one run:

```powershell
.\.venv\Scripts\python.exe .\xai\manage.py dashboard `
  --reports xai/outputs/updated/sia_context_harmonized/seed_42 `
  --output xai/outputs/updated/sia_context_harmonized/seed_42/dashboard.html
```

Audit a run's privacy/provenance boundary:

```powershell
.\.venv\Scripts\python.exe .\xai\manage.py audit `
  --run xai/outputs/updated/dp_distributed_0.001/seed_42
```

## Interpretation and release rules

The Sia context-harmonized model is federated continual learning without formal
DP. DP runs record their privacy mode and accounting metadata; transaction-level
reports do not automatically inherit the model's client-level DP guarantee.
Local explanations, histories, account relationships, and paired-case CSVs are
bank-local artifacts. Aggregate summaries are not automatically differentially
private and need a separate release review.

The current classifier predicts suspiciousness. It does not classify fraud
typologies such as fan-in or fan-out, and XAI must not infer those labels from a
score or feature attribution. A typology dashboard requires a separately
validated typology detector or explicit ground-truth labels. The Sia ensemble
averages three member probabilities but has no saved ensemble checkpoint; the
runner explains member checkpoints and compares their outputs. After all three
Sia seed runs, compute exact feature SHAP for the true mean-probability ensemble:

```powershell
.\.venv\Scripts\python.exe .\xai\ensemble_updated.py
.\.venv\Scripts\python.exe .\xai\manage.py dashboard `
  --reports xai/outputs/updated/sia_ensemble/42_52_62 `
  --output xai/outputs/updated/sia_ensemble/42_52_62/dashboard.html
```

Those optional ensemble reports explain `logit(mean(member probabilities))`
with each member's own pre-event memory. The static-report command does not
attach a decision cutoff. Sia's separate ensemble experiment records its
validation-selected cutoffs in `artifacts/research_seed_ensemble/FREEZE.json`;
these are unrelated to the active single-model dashboard's saved cutoffs.

### Interactive dashboard: selected adaptive federated global model

Start the current dashboard from the repository root:

```powershell
.\.venv\Scripts\python.exe .\xai\serve_dashboard.py
```

Open `http://127.0.0.1:8765/`. The default is the seed-42 run's selected
`global_model.pt`, trained by `adaptive_continual_federated.py` using risk-context
replay and temporal harmonization. The saved checkpoint is round 4 of that
run's four configured federated rounds. It is one global federated model.
Its training-run seed is recorded for provenance; predictions are not averaged
across runs. An explicit `--seed 52` or `--seed 62` can select a different single
saved run. The legacy `serve_ensemble_dashboard.py` launch command now forwards
to this same single-model server.

The dashboard uses the selected model's saved per-bank thresholds from its
`metrics.json`; it does not fit new cutoffs. Startup verifies the checkpoint,
preprocessing artifact and full-validation metrics before serving data. The
views are **Flagged by model**, **Known fraud labels**, and **Missed fraud**.
Dataset labels are shown for evaluation and are not predictor inputs. The
server does not load September/test data. DP checkpoints remain blocked as
described below; this dashboard is the non-private Sia adaptive model.

Selecting a transaction generates or retrieves an explanation of that same
checkpoint's prediction. Its feature attribution, historical replay and amount
what-if all target the single global model. Cache records are separated from
older ensemble outputs under `outputs/updated/adaptive_federated/seed_42/`.
Their keys include the checkpoint, saved threshold, reference predictions,
preprocessing and explanation implementation. Old reports for an individual
model are reused only after their exact checkpoint and preprocessing hashes,
background settings, threshold and prediction parity have been checked.

The page answers two questions: **Why did the model flag this transaction?**
and **What feature, history and graph evidence supports the explanation?**
Transfer maps label arrows with actual transaction IDs and circles with the
dataset's account IDs, verified against the model event streams' stable node
mapping. Account IDs and transaction IDs are kept distinct. Only training
history and completed validation batches before prediction are considered;
current-batch and future transfers are excluded. A chain or chronological loop
is described only when its observed edges support it. It is not a validated
fraud typology or proof that the same funds traversed the path. A history score
effect comes from suppressing a specific earlier event in the selected model's
bounded replay; an entire path's combined effect is not asserted. Technical
methods, verification fields and optional what-if checks are expandable.

Page assets are in `static/` and reload on refresh. Keep the server running
while using the page; stop a foreground server with Ctrl+C. The older ensemble
scripts and artifacts above remain research comparisons and are not the
interactive dashboard's predictor.

### DP verification status

The DP `results.json` field `checkpoint_sha256` describes the initial conditional
checkpoint (the same corrected-FedAvg path is recorded in `results.json`), not
the final trained `experiments/.../global_model.pt`. The final model file hash is
confirmed by `ARTIFACT_MANIFEST.json`; this mismatch is a provenance-field
semantics bug, not evidence that the file itself is corrupt. The runner records
both hashes separately and does not rewrite source metadata.

DP full-stream validation metrics now reproduce to floating-point precision
when the final checkpoint is loaded with the experiment's fixed public
`feature_schema.json`, the archived model source, and training-before-validation
memory replay. However, the cached XAI target wrapper still disagrees with the
full-stream score on some fixed transactions. For example, the DP warm baseline
preflight records target errors in
`outputs/updated/diagnostics/dp_warm_none/seed_42.json`. The runner stops before
generating additional DP explanations when any target exceeds the 1e-6 parity
tolerance. Preserve that guard until the per-target temporal replay mismatch is
resolved.

## Automated utility tests and redacted export

Run the added deterministic utility suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s xai\tests -v
```

To create a redacted copy of one local JSON report, set a secret of at least 32
bytes in `XAI_REDACTION_KEY`. The source report is left unchanged. An optional
JSON policy can add keys to `drop_keys` or disable pseudonyms with
`pseudonymize_ids: false`.

```powershell
$env:XAI_REDACTION_KEY = 'use-a-private-random-secret-of-at-least-32-bytes'
.\.venv\Scripts\python.exe .\xai\manage.py redact `
  --source xai/outputs/updated/sia_context_harmonized/seed_42/local/JPMorgan_Chase/reports/validation_00059321/explanation.json `
  --output xai/outputs/updated/shareable/jpm_case.json
```

Redaction does not make an artifact differentially private. Review it for the
intended recipient and disclosure scope before sharing.

## Grouped dashboard XAI and evaluation

The single-global-model dashboard now uses exact grouped empirical interventional SHAP. Amount sent, amount received and both currencies are perturbed jointly. Numerical signed logit attributions, model provenance, reference-stability diagnostics, graph replay coverage, clickable accounts/edges and an intervention inspector are shown. See [XAI_EVALUATION.md](XAI_EVALUATION.md) for measured limitations and separate frozen detection performance.

Run `.venv/Scripts/python.exe xai/evaluate_xai.py` to reproduce diagnostic group stability, perturbation and source-level bounded-replay checks. Existing frozen September artifacts are hash-verified and reported without retuning or repeating test inference. September remains exploratory because it was previously inspected.

## Integration/runtime boundary

The source-less CPython 3.12 engine is intentionally versioned under
`engine_py312/`, outside ordinary `__pycache__` directories. Its original sources
were not supplied. All 17 upstream modules are preserved byte-for-byte; the
manifest records their source commit, original paths, sizes and SHA-256 hashes.
See [engine_py312/README.md](engine_py312/README.md). Ordinary generated caches
and repository-local temporary staging remain ignored. Run the live scoring
engine in an existing CPython 3.12 environment with its compatible dependencies.
The loader rejects incompatible Python versions before modifying staged model
source or importing the engine. Editable utility/frontend tests can run separately.

**DP model integration preserved; direct XAI explanation of DP checkpoints remains guarded pending target-wrapper parity.**

This statement applies to the legacy bytecode-engine checkpoint adapter. The new
three-member private federated ensemble also uses the current dashboard's
`streaming.app.explanations` path. Live checks of the nonprivate reference and the
private production round-four checkpoint passed with zero observed probability
parity error and rejected an injected 1.5e-6 mismatch under the strict 1e-6 guard.
See `artifacts/dp_level3_ensemble/LIVE_ENSEMBLE_XAI.json`. This verifies those
targets; it does not remove either path's guard or give transaction explanations
a DP guarantee.

The optimized decoder-only Level-3 finalist and its retained validation evidence
remain under `artifacts/dp_level3_utility_optimization/`. The current interactive
XAI dashboard targets the nonprivate Sia adaptive checkpoint. This integration
does not claim that the cached target wrapper explains the optimized DP finalist;
the existing per-target `1e-6` parity preflight and fail-closed behavior remain
unchanged. No model parameters, thresholds, DP accounting or explanation
attribution calculations were changed by this integration.
