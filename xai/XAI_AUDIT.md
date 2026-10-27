# Dashboard audit

**Legacy audit:** grouped attribution improvements and expanded evaluation are documented in [XAI_EVALUATION.md](XAI_EVALUATION.md).

Reproduce: `.venv/Scripts/python.exe xai/audit_dashboard.py`.
Measured results: `outputs/updated/adaptive_federated/seed_42/xai_audit.json`.

## Cutoffs

Selected model: origin/sia context-harmonized seed 42, best round 4.
Checkpoint SHA-256: d650af6959d1da46888f30fb79bbfd888a6ec20743d14d447ea078dc351536f5.
Scores and cutoffs use the same 0–1 scale. The dashboard checks checkpoint,
preprocessing and per-bank saved validation metric provenance.

The training snapshot selects maximum validation F1 over 501 score quantiles.
Independent recomputation for all three banks gives cutoff differences below
0.000000087 and identical decisions. Saved validation metrics also reproduce.
JPMorgan Chase: 129 alerts, 16 true positives, 113 false positives against labels.
The low cutoff is reproducible; this does not establish deployment suitability.
Validation-selected cutoffs and validation metrics are not independent test
evidence. Score-to-cutoff ratios do not measure fraud likelihood or calibration.

## Features

Independently recomputed exact empirical interventional SHAP for five cached
dashboard cases across three banks using each report's 32 training reference
transaction IDs, fixed account memory, and all 32 coalitions of five fields.
This uses editable calculation code independently of the bytecode engine.
Maximum attribution disagreement is below 1e-15 logit units; additive
reconstruction error below 0.00000045; displayed probability error below
0.00000005. These are numerical consistency checks, not proof of fraud.

Single-field reference ablations corroborate all directions in cases 180245,
2580817 and 2794670. Amount disagrees in 3400462; both amount aliases disagree
in 2974317. SHAP averages across coalitions while single-field ablations hold
other actual values fixed, so they answer different questions. The interface
now explicitly names SHAP and describes this limitation.

Amount/currency aliases are perturbed separately by the supplied engine and
summed only for display. This is not grouped SHAP and may produce inconsistent
hybrid inputs. Reference-sample stability and causal faithfulness are not
established by this audit; the baseline and account memory remain undecomposed.

## Graph

Existing checked-effect code requires replay parity within 0.000001 and matches
transaction ID, endpoints and timestamp to preceding history. Current-batch and
future events are excluded. Effects suppress one update in a bounded replay
with pre-window memory retained, rather than removing an entire account/path.

The graph now distinguishes dashed blue untested context, solid orange upward
support, solid mint downward support, and solid gray negligible measured effects.
Tested labels, hover before/after scores, and all accepted result cards are
displayed. Width distinguishes tested evidence, not effect magnitude.

Validation: all 19 existing XAI tests and JavaScript syntax checking passed.
No live-browser visual inspection or independent rerun of every graph replay
was performed; graph effects retain the original replay verification.
