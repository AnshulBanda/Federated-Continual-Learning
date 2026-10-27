# Final review: demonstration and verified status

Prepared 27 October 2026. This checklist describes the integrated local application and the checks completed during implementation. It does not certify external networks or production deployment.

## Start

From the repository root, install `requirements-dashboard.txt`, then run:

```bash
python -m streaming.app.dashboard
```

Open `http://127.0.0.1:8765`. If another instance owns the port, use `--port 8766`. Local scoring, adaptation and explanations do not require a running Kafka broker. Keep the terminal open. The completed development workspace is a separate clone in `final_review/`; start commands from that clone, not its parent checkout.

## Suggested presentation sequence

1. **Overview:** choose Key Bank. Explain that the selected system averages three adaptive temporal models. Show the saved **90.68% September macro PR-AUC**, identifying it as exploratory average precision rather than accuracy.
2. **Data & training:** show the prepared dataset and run **Check data quality**. Explain training-only normalization, separated labels, chronological splits and bank-local data. If time permits, start local adaptation; otherwise show a previously completed run and its measured validation result.
3. **Transactions:** choose **Score validation replay**, then **Load replay**. Use **Next alert** or **Review all scored transactions**, search a transaction/account and inspect the account graph. The screen is a recorded August replay, not a live bank feed.
4. **Explanations:** click **Explain score** on a transaction. Show the three member probabilities, the final score, payment-method and joint amount/currency contributions, and the additive residual. Explain that account memory is fixed and feature attribution is not proof of causation.
5. **Results & history:** compare earlier models with the final ensemble. Separate the original September headline from new August validation runs. Export the displayed JSON if reviewers want evidence.
6. **Collaboration:** show coordinator/bank roles and the common run setup. With Kafka available, demonstrate readiness, training, signed updates, harmonization, verified returns and explicit shared-model selection. Use a fresh run ID and the same roster/settings on all participants.
7. **Weight transfers:** explain Published versus Delivered versus Verified. Demonstrate only when both endpoints and a broker are ready; transfer receipt confirmation is separate from model evaluation.
8. **Privacy & transfers:** state that signatures and hashes protect integrity, while **formal DP, secure aggregation and application-configured Kafka TLS are not implemented**.

## Checks already completed

These results are from executed checks, not planned acceptance criteria.

| Check | Observed outcome |
|---|---|
| Dashboard/federation regression suite | 83 tests passed |
| Adaptive-model regression suite | 17 tests passed |
| Existing XAI regression suite | 23 tests passed after removing a machine-specific temporary-directory dependency |
| JPMorgan Chase ensemble validation | AP **0.8300817557164852**, exactly matches saved evidence |
| Wells Fargo ensemble validation | AP **0.9622832604116025**, exactly matches saved evidence |
| Key Bank ensemble validation | AP **0.8654682493601763**, exactly matches saved evidence |
| Transaction explanation | Matches the selected high-risk replay prediction; additive residual **−0.00000246154** |
| Local ensemble adaptation | All three members processed; Key Bank validation AP **0.9087593748751843**; selected checkpoint reload reproduces the measured score |
| Real local Kafka federation | One round, three bank workers, one epoch per task per member; all three updates verified and all three returned aggregates byte-identical |
| Returned federation payload | **2,915,100 bytes**, SHA-256 `e4a2ff8a3f8e6a800575a6045fb2900bc9d60dd8187d61dfb283a2da3e3cf96d` |

The new **90.88% Key Bank validation AP** is a bank-local August adaptation result. It is not a replacement for the **90.68% three-bank September result**, and it must not be presented as a new untouched-test score. Seeds 42 and 62 retained their starting checkpoint; seed 52 selected its adapted checkpoint.

The real Kafka check used local processes and a local broker. It verifies the actual three-member training, harmonization, serialization and return path, but not cross-laptop VPN/firewall setup. It is a one-round transport/training acceptance check, not a complete reproduction of the historical four-round study.

Sanitized saved evidence is in [DASHBOARD_ACCEPTANCE.json](DASHBOARD_ACCEPTANCE.json). Full local worker logs remain under:

- `streaming/.local/dashboard-check-7fc8bcd8a1/`
- `streaming/.local/accept-b8e0a85d2b0042b9/`

These ignored state folders belong to the implementation machine and are not required for a clean clone. The repeatable checks below create fresh evidence.

## Repeatable checks, when needed

```bash
python -m unittest discover -s tests/streaming -v
python -m unittest discover -s tests -p 'test_adaptive_fcl.py' -v
python -m unittest discover -s xai/tests -v
python scripts/verify_dashboard_workflow.py
python -m streaming.test_federation --broker 127.0.0.1:9092 --rounds 1
```

The HTTP workflow check never loads September transactions and does not modify the original checkpoints. It runs in an isolated state folder. The federation check uses the configured local broker and separate run identities.

## Questions reviewers may ask

**Why three models?** The measured final system averages probabilities from seeds 42, 52 and 62. This reduces dependence on one initialization; it costs three model passes. Ensembling itself is established practice.

**Where is continual learning?** Each member learns June, then July with a capacity-2,000 buffer containing historical fraud, risk and account-context events.

**Where is federated learning?** Bank workers train locally and send parameter updates. The coordinator harmonizes temporal components and averages equal-client updates separately for each seed, then returns the ensemble.

**Where is explainability?** Exact grouped Shapley values explain the selected transaction's features under fixed pre-batch account memory, using 32 training references. Predictions are checked against the saved replay.

**Is the model differentially private?** No. The final path has no calibrated DP noise or privacy accountant. This limitation is displayed and documented rather than hidden.

**Does 90.68% mean accuracy?** No. It is macro average precision across three banks on the saved exploratory September evaluation.

**Does the dashboard preserve existing features?** Transfer signatures, receipts, retries, cancellation, history, model selection and graph investigation remain present. The dashboard's active model/training path now uses the final ensemble; legacy CLI paths remain for historical experiments.

## Remaining limits to state honestly

- The data is simulated, with three selected banks and two training tasks.
- September was inspected in prior development and is exploratory.
- New local/federated training versions must be evaluated; they do not inherit the original headline.
- Cross-laptop deployment, external network availability and production hardening require separate verification.
- DP, secure aggregation and application-configured TLS are absent.
- Backend acceptance checks passed. Full browser/responsive inspection of every screen was not completed before the final documentation-only stop.
