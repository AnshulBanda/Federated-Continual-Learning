# Validation/privacy frontier

Initial screening uses fixed final checkpoints; the separately frozen follow-up retains the best-August checkpoint, labeled explicitly. ± is sample standard deviation across model seeds, with one independent production noise sequence per seed. Best intermediate August AP is descriptive; all rounds are charged. Epsilon is per seed/pipeline, not the entire search. See `seed_results.csv` for every metric, bank and mechanism parameter.

| Track | Mode / selection | m | Seeds | Selected macro AP ± SD | Best intermediate AP ± SD | Epsilon/pipeline |
|---|---|---:|---|---:|---:|---:|
| scratch | distributed_dp / final | 0.001 | 42,52,62 | 0.5662 ± 0.3046 | 0.6882 ± 0.1601 | 2.40364e+07 |
| scratch | none / final | 0 | 42,52,62 | 0.4841 ± 0.2827 | 0.7620 ± 0.0692 | infinite |
| warm | distributed_dp / best_validation | 1e-05 | 42,52,62 | 0.8293 ± 0.0998 | 0.8293 ± 0.0998 | 6.00018e+10 |
| warm | distributed_dp / final | 1e-05 | 42,52,62 | 0.8325 ± 0.0554 | 0.8630 ± 0.0500 | 6.00018e+10 |
| warm | distributed_dp / final | 0.0001 | 42,52,62 | 0.5931 ± 0.3319 | 0.8449 ± 0.0684 | 6.00182e+08 |
| warm | distributed_dp / final | 0.001 | 42,52,62 | 0.7609 ± 0.1223 | 0.8085 ± 0.0834 | 6.01821e+06 |
| warm | distributed_dp / final | 0.01 | 42,52,62 | 0.5886 ± 0.2275 | 0.7506 ± 0.1418 | 61820.9 |
| warm | distributed_dp / final | 0.1 | 42 | 0.0031 (single seed) | 0.1495 (single seed) | 782.091 |
| warm | none / final | 0 | 42,52,62 | 0.7032 ± 0.2601 | 0.8242 ± 0.0676 | infinite |
| warm | option_a / final | 0.001 | 42,52,62 | 0.7027 ± 0.1792 | 0.8293 ± 0.0278 | 2.01051e+06 |
| warm | research_reference / final | 0 | 42,52,62 | 0.6735 ± 0.3099 | 0.8056 ± 0.1368 | infinite |
| warm | secure_central_dp / final | 0 | 42,52,62 | 0.7016 ± 0.2590 | 0.8241 ± 0.0675 | infinite |
| warm | secure_central_dp / final | 0.001 | 42,52,62 | 0.6006 ± 0.2704 | 0.8405 ± 0.0643 | 2.01051e+06 |

Private subset composition: rho=3.6190918e+11, epsilon=3.6191365e+11, delta=1e-6. The whole nonprivate research bundle is not DP.

A bounded negative result does not prove impossibility for every other multiplier or training configuration. No seed, noise realization or September result is selected to manufacture a passing mean.
