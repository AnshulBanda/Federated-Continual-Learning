# Level-3 utility optimization — final report

27 October 2026. Local work only; nothing pushed.

**TARGET ACHIEVED: 0.902810 ± 0.032415 macro August validation PR-AUC** across seeds 42, 52 and 62 (sample SD). These are private-continuation seeds from one fixed nonprivate pretraining checkpoint; see the explicit seed-scope statement below.

## Starting baseline

Reload-verified 0.832548 ± 0.055419. CausalTemporalGraphSAGE, 242,561 floating coordinates, fixed nonprivate warm starts, risk/account-context replay, equal secure mean, four private releases, C=6.5, multiplier=1e-5, delta=1e-6.
Conservative encoded-share epsilon: 60001820912.6. Exact checkpoint and source evidence: INITIAL_AUDIT.json, BASELINE_VERIFIED.json and baseline_reload_*.json.

## Optimization evidence

All trials, including failures, appear below and in SEARCH_LOG.json. Screening uses deterministic research-only noise; these are not operational DP results. Only production-confirmed candidates establish success. Plans were saved before their associated runs. Selection always chooses highest equal-bank August AP, earliest round on a tie. All executed releases count, including those after an earlier selected checkpoint.

| Candidate | Phase | Seeds | Selected August AP mean ± sample SD | Epsilon per run |
|---|---|---|---:|---:|
| calibrated_decoder_m0p03 | research | 42 | 0.921018 (single seed) | 1970.1521 |
| calibrated_decoder_m0p15 | research | 42,52,62 | 0.893513 ± 0.016720 | 127.36375 |
| calibrated_decoder_m0p1 | research | 42,52,62 | 0.917200 ± 0.011587 | 241.04563 |
| calibrated_decoder_m0p25 | research | 42,52 | 0.836891 ± 0.052276 | 60.418251 |
| calibrated_decoder_m0p2 | research | 42,52,62 | 0.757152 ± 0.202792 | 83.022814 |
| calibrated_decoder_m0p3 | research | 42 | 0.731507 (single seed) | 47.015209 |
| fixed_warm_decoder_m0p0001 | research | 42 | 0.921711 (single seed) | 1.5009105e+08 |
| fixed_warm_decoder_m0p001 | research | 42 | 0.921006 (single seed) | 1509104.6 |
| fixed_warm_decoder_m0p01 | research | 42,52,62 | 0.922025 ± 0.002971 | 15910.456 |
| fixed_warm_decoder_m0p03 | research | 42,52 | 0.894869 ± 0.023257 | 1970.1521 |
| fixed_warm_decoder_m0p1 | research | 42 | 0.306827 (single seed) | 241.04563 |
| refine_one_epochs4 | research | 42 | 0.801925 (single seed) | 1.500091e+10 |
| refine_one_lr0015_neg10 | research | 42,52,62 | 0.821777 ± 0.073335 | 1.500091e+10 |
| refine_one_lr002 | research | 42 | 0.724289 (single seed) | 1.500091e+10 |
| stage1_selection | research | 42,52,62 | 0.803821 ± 0.140604 | 6.0001821e+10 |
| stage2_0_fedavg | research | 42 | 0.836972 (single seed) | 6.0001821e+10 |
| stage2_1_fedavgm | research | 42,52,62 | 0.782258 ± 0.149353 | 6.0001821e+10 |
| stage2_2_fedavgm | research | 42 | 0.862330 (single seed) | 6.0001821e+10 |
| stage2_3_fedadam | research | 42 | 0.843098 (single seed) | 6.0001821e+10 |
| stage2_4_fedadam | research | 42 | 0.853697 (single seed) | 6.0001821e+10 |
| stage2_5_fedyogi | research | 42 | 0.811417 (single seed) | 6.0001821e+10 |
| stage3_epochs2 | research | 42,52,62 | 0.760333 ± 0.179183 | 6.0001821e+10 |
| stage3_lr0003 | research | 42 | 0.798881 (single seed) | 6.0001821e+10 |
| stage3_lr0005 | research | 42 | 0.784342 (single seed) | 6.0001821e+10 |
| stage3_lr00075 | research | 42 | 0.832985 (single seed) | 6.0001821e+10 |
| stage3_lr0015 | research | 42 | 0.846519 (single seed) | 6.0001821e+10 |
| stage3_replay4000 | research | 42 | 0.852063 (single seed) | 6.0001821e+10 |
| stage4_counter | research | 42,52,62 | 0.766344 ± 0.173684 | 6.0001821e+10 |
| stage5_C3p5 | research | 42 | 0.845451 (single seed) | 6.0001821e+10 |
| stage5_C5p5 | research | 42,52,62 | 0.796454 ± 0.160669 | 6.0001821e+10 |
| stage7_decoder | research | 42 | 0.830837 (single seed) | 6.0001821e+10 |
| stage7_message_decoder | research | 42,52,62 | 0.790900 ± 0.162430 | 6.0001821e+10 |
| stage7_temporal_decoder | research | 42 | 0.851206 (single seed) | 6.0001821e+10 |
| stage8_frozen_warm | research | 42 | 0.871001 (single seed) | 6.0001821e+10 |
| stage8_global_one | research | 42 | 0.543372 (single seed) | 1.500091e+10 |
| confirm_calibrated_decoder_m0p15 | production | 42,52,62 | 0.902810 ± 0.032415 | 127.36375 |
| stage1_selection_mean_last2 | research_postprocessing | 42,52,62 | 0.769044 ± 0.185621 | 6.0001821e+10 |
| stage1_selection_mean_last3 | research_postprocessing | 42,52,62 | 0.739772 ± 0.218914 | 6.0001821e+10 |
| stage1_selection_mean_all | research_postprocessing | 42,52,62 | 0.742969 ± 0.193192 | 6.0001821e+10 |
| stage1_selection_ema_half | research_postprocessing | 42,52,62 | 0.767713 ± 0.187506 | 6.0001821e+10 |
| stage2_1_fedavgm_mean_last2 | research_postprocessing | 42,52,62 | 0.711149 ± 0.247064 | 6.0001821e+10 |
| stage2_1_fedavgm_mean_last3 | research_postprocessing | 42,52,62 | 0.717400 ± 0.229790 | 6.0001821e+10 |
| stage2_1_fedavgm_mean_all | research_postprocessing | 42,52,62 | 0.727753 ± 0.200176 | 6.0001821e+10 |
| stage2_1_fedavgm_ema_half | research_postprocessing | 42,52,62 | 0.723354 ± 0.234277 | 6.0001821e+10 |
| stage3_epochs2_mean_last2 | research_postprocessing | 42,52,62 | 0.581574 ± 0.152493 | 6.0001821e+10 |
| stage3_epochs2_mean_last3 | research_postprocessing | 42,52,62 | 0.645692 ± 0.198956 | 6.0001821e+10 |
| stage3_epochs2_mean_all | research_postprocessing | 42,52,62 | 0.649822 ± 0.151467 | 6.0001821e+10 |
| stage3_epochs2_ema_half | research_postprocessing | 42,52,62 | 0.566931 ± 0.124172 | 6.0001821e+10 |
| stage4_counter_mean_last2 | research_postprocessing | 42,52,62 | 0.670143 ± 0.197615 | 6.0001821e+10 |
| stage4_counter_mean_last3 | research_postprocessing | 42,52,62 | 0.675062 ± 0.162425 | 6.0001821e+10 |
| stage4_counter_mean_all | research_postprocessing | 42,52,62 | 0.693834 ± 0.211455 | 6.0001821e+10 |
| stage4_counter_ema_half | research_postprocessing | 42,52,62 | 0.652660 ± 0.189649 | 6.0001821e+10 |
| stage5_C5p5_mean_last2 | research_postprocessing | 42,52,62 | 0.766140 ± 0.196539 | 6.0001821e+10 |
| stage5_C5p5_mean_last3 | research_postprocessing | 42,52,62 | 0.750837 ± 0.156372 | 6.0001821e+10 |
| stage5_C5p5_mean_all | research_postprocessing | 42,52,62 | 0.744497 ± 0.142448 | 6.0001821e+10 |
| stage5_C5p5_ema_half | research_postprocessing | 42,52,62 | 0.756334 ± 0.176357 | 6.0001821e+10 |
| stage7_message_decoder_mean_last2 | research_postprocessing | 42,52,62 | 0.718367 ± 0.202218 | 6.0001821e+10 |
| stage7_message_decoder_mean_last3 | research_postprocessing | 42,52,62 | 0.734522 ± 0.180263 | 6.0001821e+10 |
| stage7_message_decoder_mean_all | research_postprocessing | 42,52,62 | 0.731389 ± 0.181625 | 6.0001821e+10 |
| stage7_message_decoder_ema_half | research_postprocessing | 42,52,62 | 0.725561 ± 0.182020 | 6.0001821e+10 |

### Hypotheses, decisions and retained failures

1. **Checkpoint selection parity.** Retain every round and fix highest August equal-bank AP, earliest-round tie. The old `0.8630` intermediate summary lacked the seed-42 checkpoint and its separate fresh follow-up failed; neither was promoted. The new controlled, fully retained selection run scores `0.803821` across the original seed-specific warm starts. Selection alone is insufficient. Every executed release remains charged.
2. **Aggregate-only server optimization.** Screen damped FedAvg (step 0.5), FedAvgM (step 0.5, momentum 0.5 or 0.9), FedAdam (lr 0.01 or 0.03, beta1 0.9, beta2 0.99, epsilon 0.001), and FedYogi (lr 0.01, same moments). The leading momentum candidate scores `0.782258` across all three seeds. Other server candidates have lower seed-42 screening scores or destructive late-round behavior. No optimizer sees individual clean contributions. None is retained as the final optimizer.
3. **Local training.** Screen lr 3e-4, 5e-4, 7.5e-4 and 1.5e-3 around the accepted 1e-3, two epochs, and replay 4000. Two epochs passes early screens but finishes at `0.760333` across all seeds. Larger replay reaches `0.852063` on seed 42, without enough margin to outrank the promoted candidates. Subsequent one-release refinements test lr 2e-3, lr 1.5e-3 with negative ratio 10, and four epochs. Negative ratio 10 reaches `0.821777` across three seeds; the others fail seed-42 screening. The final smaller lr/two-epoch schedule is used for a distinct, fixed-warm decoder adaptation, rather than claimed as a successful full-model continuation.
4. **Public RNG stabilization.** SHA256 domains separate each worker's public phase/epoch dropout and sampling streams. No private entropy is shared. It passes worker equivalence tests but scores `0.766344` across the original three warm starts. Retain the implementation and negative evidence, use the accepted per-client RNG in the finalist, and make no bitwise claim about Sia's old global stream.
5. **Clipping.** C=3.5 and 5.5 were chosen near the old training-only median/p75 norms, with full quantization and share-sigma recomputation. C=5.5 plus momentum scores `0.796454` across seeds. Later, the winning decoder track receives a separate explicitly nonprivate training-only calibration: nine worker norms, maximum 1.115015, quarter-unit ceiling C=1.25. This is a public bound conditional on nonprivate research calibration, as in the original baseline. Operational workers still clip every update; no observed-norm assumption substitutes for clipping.
6. **Release count.** Compare 1/2/3/4-round prefixes of retained complete runs. The prefix diagnostic never erases the later releases actually made by screening runs. None of the original warm policies passes at shorter counts. The final deployment actually runs exactly one private release and stops; it does not execute four and retrospectively charge one.
7. **Private parameter subsets.** Decoder-only (65,793 coordinates), temporal/GRU plus decoder (165,249), and message/GRU plus decoder (230,529) are screened. The last reaches 0.882434 at seed 42 and 0.886907 at seed 52, then fails seed 62; its three-seed mean is 0.790900. Subset freezing and reconstruction pass real-training/SecAgg regression tests. The final decoder-only variant is paired with a fixed pretrained representation. Frozen coordinates never receive Gaussian noise or private parameter changes.
8. **Frozen starting checkpoints.** Hash and audit local Git objects from Sia's preexisting August-selected context-harmonized warm family and global-RNG context-replay family. Their initial three-seed means are approximately 0.811408 and 0.833127. Warm-family continuation at seed 42 reaches 0.871001; the global-RNG one-release continuation fails screening. Then predeclare one fixed, already frozen August-selected checkpoint (Sia pretraining seed 42) as the common starting model for three independent private-continuation seeds. This is the requested conditional WARM privacy scope. It is not three independent nonprivate pretraining replicates, and the original seed-specific tracks remain unsuccessful. Decoder-only adaptation preserves useful nonprivate pretrained knowledge; its final mean is below the fixed starting model's nonprivate 0.923388 AP.
9. **Aggregate-only refinements.** Four fixed weight-average rules are evaluated on all checkpoints of each of six complete original runs: last two, last three, all rounds, EMA 0.5. Each produces one full model, using checkpoints within the same already-accounted run. No independent private mechanisms are mixed. All 72 postprocessed checkpoints are retained; best three-seed mean is 0.769044. These alternatives are rejected.
10. **Privacy/utility refinement and production freeze.** At fixed warm/C=6.5, m=1e-4, 1e-3, 0.01, 0.03 and 0.1 are screened. The 0.01 candidate passes all three research seeds at 0.922025. At calibrated C=1.25, screen m=0.03, 0.1, 0.2, 0.3 and intermediate 0.25. m=0.2 fails seed 62; 0.25 is not promoted after that correlated higher-noise failure. A final bounded midpoint m=0.15 passes research confirmation at 0.893513. Freeze source and nominees m=0.15 then m=0.1 in increasing-epsilon order. Exactly one fresh production-entropy confirmation per seed at m=0.15 achieves 0.902810 ± 0.032415. The fallback is not executed. No further multiplier search or same-configuration noise reruns occur.

Research-only deterministic Gaussian comparisons are not operational DP releases and do not give the complete search bundle a finite DP guarantee. All production reservations, including Kafka acceptance, compose separately; historical production-only composition is also reported. Raw updates and Gaussian realization vectors were never retained.


## Final architecture

The configuration is frozen in FINALIST_CONFIG.json; per-seed operational configs are retained next to it. Training uses the same trainer as independent Kafka workers. Model temporal state, replay and local optimizer remain inside each bank.

```json
{
  "rounds": 1,
  "checkpoint_template": "/Users/pj/Desktop/college/capstone/Capstone-DP-SecAgg/artifacts/dp_level3_utility_optimization/frozen_warm_starts/seed_42/global_model.pt",
  "subset": "decoder",
  "learning_rate": 0.0003,
  "local_epochs": 2,
  "clip": 1.25,
  "entropy": "production",
  "pretraining_seed": 42,
  "seed_scope": "private_continuation",
  "starting_checkpoint_policy": "fixed_shared_nonprivate_August_selected",
  "multiplier": 0.15
}
```

Trainable private dimension: 65793; frozen keys: 176768 coordinates. AdamW, June then July chronological risk/account-context replay; batch size 1024, TBPTT 2, local gradient norm cap 5 for stability. Full training settings: {"batch_size": 1024, "distill": 0.0, "learning_rate": 0.0003, "local_epochs": 2, "negative_ratio": 20, "replay": "risk_context", "replay_size": 2000, "rng_policy": "per_client", "weight_decay": 0.0001}.

## Final three-seed utility

| Seed | Macro AP | JPMorgan AP | Wells Fargo AP | Key Bank AP | Precision | Recall | F1 | ROC-AUC | Selected round / releases |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 42 | 0.875533 | 0.805733 | 0.915762 | 0.905104 | 0.419752 | 0.900523 | 0.515730 | 0.998776 | 1 / 1 |
| 52 | 0.894250 | 0.850430 | 0.937802 | 0.894518 | 0.436829 | 0.937229 | 0.535480 | 0.998707 | 1 / 1 |
| 62 | 0.938646 | 0.921879 | 0.964384 | 0.929675 | 0.451321 | 0.953102 | 0.550631 | 0.999412 | 1 / 1 |

**Seed scope:** all three runs use the same previously frozen, nonprivate August-selected checkpoint (pretraining seed 42). Seeds 42/52/62 independently control local continuation/replay randomness and each gets fresh production DP entropy. The reported SD measures continuation variance; it does not measure pretraining-seed variance. The original seed-specific starting-model results remain separate. The utility gain relies substantially on preserved nonprivate pretrained knowledge.

Precision/recall/F1 use each bank’s original August F1 threshold protocol. AP is sklearn average precision, averaged equally across banks; ordinary accuracy was never optimized.

## Privacy comparison

| Quantity | Baseline | Finalist |
|---|---:|---:|
| C | 6.5 | 1.25 |
| effective_clip | 6.50001467779 | 1.25000764434 |
| quantization_l2_bound | 1.4677787492e-05 | 7.64433926297e-06 |
| n | 3 | 3 |
| dimension | 242561 | 65793 |
| multiplier | 1e-05 | 0.15 |
| sensitivity | 4.33334311852 | 0.83333842956 |
| encoded_share_sensitivity | 13.0000293556 | 2.50001528868 |
| sigma_mean | 4.33334311852e-05 | 0.125000764434 |
| sigma_share | 7.50557044791e-05 | 0.216507674985 |
| releases | 4 | 1 |
| rho_per_release | 15000000000 | 66.6666666667 |
| rho | 60000000000 | 66.6666666667 |
| epsilon | 60001820912.6 | 127.363751842 |
| delta | 1e-06 | 1e-06 |
| expected_noise_l2 | 0.021341923826 | 32.0628788264 |

Privacy is **stronger** under the same conservative encoded-share accountant: rho per release = n/(2m²), epsilon = rho_total + 2 sqrt(rho_total ln(1/delta)). Quantization error is sqrt(d)/(2s), C_eff=C+error, mean sensitivity=2*C_eff/3 and sigma_share=sqrt(3)*sigma_mean. All three noise contributors remain mandatory, with production OS entropy. No clean aggregate reaches the coordinator.

Conservative encoded-share ideal-Gaussian bound; finite-precision sampler is not exact-DP certified. Incremental privacy conditional on nonprivate checkpoint; no end-to-end training claim.

New production experiments and Kafka acceptance compose to rho=266.666666667, epsilon=388.060837017 at delta=1e-6. This includes all production-confirmed seeds/candidates and acceptance rounds, not only the retained models. Baseline reload consumes no new private release. Including the previous retained private-search rho of 361909180600, the historical-plus-new production-only composition is rho=361909180867, epsilon=361913652985 at the same delta. Historical source: artifacts/dp_level3_secagg/privacy_utility_frontier.json. Deterministic research screening and the complete research artifact bundle have no finite end-to-end DP guarantee.

## Secure aggregation and Kafka

X25519 ephemeral keys, HKDF domain binding, ChaCha20 pair masks, exact uint64 ring cancellation, authenticated SHA/HMAC transport, schema/base binding, complete cohort, duplicate/stale rejection and fail-closed operation remain active. Server optimizer state derives only from the noisy secure aggregate. No private keys, shared secrets, mask seeds, clean client updates or Gaussian realization vectors are retained.

```json
[
  {
    "path": "/Users/pj/Desktop/college/capstone/Capstone-DP-SecAgg/artifacts/dp_level3_utility_optimization/kafka_acceptance/finalist/result.json",
    "result": "PASS",
    "rho": 66.66666666666667
  }
]
```

## Tests and separate QA passes

See TEST_REPORT.txt and QA_REPORT.md for the complete final regression, smoke, checkpoint reload and separate model/privacy/crypto/statistical/distributed/regression reviews. These are review passes, not an external security certification.

## Artifacts and reproduction

FINALIST_CONFIG.json; FINALIST_PRIVACY.json; FINALIST_RESULTS.json; SEED_RESULTS.csv; PRIVACY_UTILITY_FRONTIER.json; SEARCH_LOG.json; QA_REPORT.md; TEST_REPORT.txt; SOURCE_MANIFEST.json; CHECKPOINT_PROVENANCE.json. Every round checkpoint remains under research/ or production/. The production plan is frozen before execution. Exact retained metrics are reproduced by checkpoint reload; fresh private entropy intentionally changes new training trajectories.

Use the existing interpreter /Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python. Run scripts/confirm_utility_finalists.py --plan artifacts/dp_level3_utility_optimization/PRODUCTION_CONFIRMATION_PLAN.json --output /absolute/path/to/NEW_output_directory. Do not overwrite completed evidence. Use scripts/evaluate_private_federation.py to reload any retained checkpoint. No dataset downloads, copies, regeneration or September evaluation occurred.

## Git state

Branch philip-dp-secagg-ddp; starting HEAD e2b49fc8ac3ac9e27cb1eed723570e2a1ed6781a. Historical Level-3 evidence hashes remain unchanged. Final status is recorded in FINAL_GIT_STATE.json. Nothing was pushed.

## Presentation-safe statement

The optimized three-bank Level-3 federated system retains secure aggregation and distributed differential privacy while achieving 0.9028 ± 0.0324 macro August validation PR-AUC across private-continuation seeds 42, 52 and 62 from one fixed nonprivate warm start. The retained per-run privacy budget is stronger relative to the previous Level-3 configuration under the same conservative encoded-share accounting, with three required noise contributors and delta 1e-6. This is incremental privacy conditional on a nonprivately trained warm start; the large epsilon bound does not establish practically strong or end-to-end differential privacy.
