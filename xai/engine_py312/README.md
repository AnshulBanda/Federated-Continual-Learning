# Preserved source-less XAI runtime

These 17 CPython 3.12 modules are the supplied scoring engine and its original
support/legacy test modules. Their Python sources were absent in the upstream
submission. They are an intentional runtime distribution with a pinned version
and integrity manifest. Ordinary generated Python caches remain ignored.

The integration moved them from `xai/__pycache__/` without changing a byte.
`MANIFEST.json` records the upstream commit, original paths, byte counts and
SHA-256 hashes. `run_updated.CachedXaiFinder` loads the same `xai.*` module names
from this directory. Its directory depth relative to `xai/` is preserved for
existing module-relative paths. Dashboard provenance records use the new paths.

Use an existing **CPython 3.12** environment with compatible NumPy, pandas and
PyTorch dependencies for live scoring/explanation. Source utility tests and the
JavaScript frontend tests can run without executing this engine. An incompatible
interpreter receives an explicit error before any model source is staged.

Retain the bundle until editable original sources or a separately validated
replacement are supplied. Integration does not replace the original scoring
logic, alter SHAP calculations, or widen DP target parity tolerances. The
optimized Level-3 model's direct per-transaction explanation remains guarded by
the existing target-wrapper parity preflight.
