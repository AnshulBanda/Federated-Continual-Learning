# Implementation guide

This guide describes the integrated dashboard in this repository. Start with the [README](../README.md) for installation and the [review checklist](FINAL_REVIEW.md) for a presentation sequence. The [codebase reference](CODEBASE_REFERENCE.md) links individual classes and functions.

## 1. Application boundaries

The application is a local Python HTTP server with a browser interface. It binds to `127.0.0.1`, serves one HTML/CSS/JavaScript page and uses JSON endpoints. Model training, transaction scoring and explanations run in separate Python processes so the page remains responsive. The frontend polls job status; progress comes from persisted worker evidence, not simulated timers.

The three bank workspaces are Key Bank, Wells Fargo and JPMorgan Chase. Selecting a bank scopes the local model, replay, explanation and result views. It does not authenticate a real institution. Local state lives in `streaming/.local/`; the final research checkpoints and metrics are read-only inputs to normal dashboard operations.

There are two independent communication workflows:

- **Automatic collaboration:** structured, signed model messages over Kafka, local training, coordinator aggregation, atomic checkpoints, and verified model returns.
- **Manual transfer:** opaque file bytes, signed chunks, hash verification and delivery receipts. Receiving a file does not run it or activate it as a model.

## 2. Data preparation and feature contract

`data/final_temporal_dataset/` contains `training/`, `validation/` and `testing/`, each partitioned by bank. A bank/split includes transaction edges, node features, a local-node-to-account map, separated ground-truth labels, and a tabular transaction file. `configuration/model_feature_columns.json` defines approved input columns. Labels, fraud markers and leaked transaction-type fields are excluded from the encoder.

The model loader joins labels by `txn_id`, checks exact transaction-ID correspondence and binary labels, reconciles account IDs across chronological splits, and creates tensor event streams. It uses stable timestamp sorting. The same real account maps to one account-memory entry across the loaded periods.

The dashboard uses `distributed_federation/feature_schema.json`. This JSON contains numeric medians, means and scales, categorical fill values and category order. `FrozenEncoder.transform` applies these values without fitting on participant validation data. The contract was exported from the simulated reference **training** data. It is shared preprocessing, not a claim of privately estimated normalization.

Before a data check or training run, `check_dataset` verifies required files, unique IDs, one-to-one node maps, valid edge endpoints, exact label joins, both label classes, finite features and chronological separation. It hashes the files and feature manifest. Workers check the fingerprint again before publishing completed outputs. A job with changed data fails instead of selecting its model.

## 3. Temporal model mechanics

The model is `CausalTemporalGraphSAGE` in `src/gnn/causal_temporal_graphsage.py`.

1. A linear projection of static node features initializes account memory.
2. A transaction decoder reads source and destination memory, their absolute difference and projected edge features. Its logit is converted to a risk probability with sigmoid.
3. Messages combine the old endpoint states, edge features and elapsed-time encodings.
4. Mean aggregation collects messages for each account and a GRU updates memory.
5. The entire batch is scored **before** that batch updates memory. Earlier batches can influence later scores; same-batch events share the prior memory state.

The final configuration uses hidden size 128, dropout 0.25 and event batches of 1,024. Training uses two-batch truncated backpropagation. Negative sampling affects supervised loss; chronological events still update temporal memory. Evaluation reconstructs memory using frozen weights rather than reusing the mixed-weight training state.

## 4. What the 90.68% model actually is

It is an ensemble of three saved adaptive global models, seeds 42/52/62. Each model maintains its own account memory. For transaction i:

`p(i) = (sigmoid(logit42(i)) + sigmoid(logit52(i)) + sigmoid(logit62(i))) / 3`

This is neither averaged weights nor averaged logits. PR-AUC here is scikit-learn average precision. Each bank gets an AP score; the final headline is the unweighted mean across banks. It is not the percentage of transactions classified correctly.

`final_model.reference_model` resolves portable repository-relative checkpoint locations and verifies each file against `artifacts/research_seed_ensemble/FREEZE.json`. This avoids relying on the original author's absolute paths stored in historical manifests. `reference_evidence` reads the completed September report. Model selection never fabricates new scores from that headline.

August validation AP is 0.8300817557 for JPMorgan Chase, 0.9622832604 for Wells Fargo and 0.8654682494 for Key Bank. Their mean is 0.8859444218. The saved September mean is 0.9067783483. The integrated scorer reproduces the August values.

## 5. Local training workflow

`LocalTraining.start` accepts a prepared dataset and job kind. Training requires a prior completed quality check for the selected bank and folder; the worker repeats the checks. The supervisor creates a job directory, log and cancellable subprocess under a filesystem lock.

`ensemble_training.train_ensemble` loads the three final members. For each member it:

1. Scores August to establish its starting validation AP.
2. Trains three epochs on June.
3. Scores June to select a capacity-2,000 buffer with positive, risk and earlier account-context events.
4. Trains three epochs on July combined chronologically with replay.
5. Scores August again and retains the initial weights if the candidate did not improve that member's AP.
6. Saves the selected member and records baseline/candidate AP and replay diagnostics.

The total progress budget is 18 epochs (three members × two tasks × three epochs). The final probabilities are averaged, a validation threshold is chosen, and the job saves `ensemble.json`, three checkpoints and measured metrics. This is a new bank-local continuation, not a replay of the historical three-bank study. Independent member selection does not mathematically guarantee an improved ensemble AP.

`LocalTraining.activate` accepts only a completed job for the saved bank, verifies every member hash and writes its active-model descriptor. Legacy single-model training jobs remain historical evidence but cannot replace the final ensemble through this path. **Use final ensemble** restores the original reference selection without deleting any completed run.

## 6. Evaluation and transaction replay

`Monitoring.start` snapshots the selected model descriptor and data location. The worker validates checkpoint hashes, loads only training and validation streams, warms each member on earlier training events, scores August and averages probabilities. It records metrics, fixed-budget alert performance, the threshold, model identity and dataset fingerprint.

For the original ensemble, the threshold comes from its frozen August record. Locally adapted ensembles carry the threshold selected during their training validation. A newly returned federated ensemble uses cutoff 0.5 until a separate operational threshold policy is established; the UI labels the adjustable cutoff as a review control.

The browser loads saved transaction scores without rerunning the model. Play/step controls reveal them chronologically; **Next alert** advances to the next score above the chosen cutoff, and **Review all scored transactions** reveals the complete saved replay. Search filters transaction/account IDs. The graph shows connections among already revealed events. This graph is contextual evidence, not itself a causal explanation or a live transaction stream.

The results page distinguishes original single-seed runs, the one final three-member ensemble, and new local/federated validation runs. Saved September numbers are read from the frozen evidence. No dashboard endpoint retrains or selects a model on September.

## 7. Explainable predictions

`Explanations.start` accepts a completed replay ID and one transaction ID belonging to that replay and bank. It snapshots the replay's model version and checks that the input data still matches the replay fingerprint. It cannot explain another bank's replay by passing its ID.

The explanation worker:

1. Loads exactly the selected ensemble and preprocessing contract.
2. Reconstructs each member's training memory and preceding validation batches.
3. Stops before the target transaction's batch, preserving the scorer's actual visibility boundary.
4. Creates predictors that hold the two account states fixed while varying current transaction fields.
5. Uses the existing `xai/src/grouped_features.py` exact empirical group-Shapley implementation and `ensemble_explainer.py` probability-ensemble predictor.
6. Uses 32 training reference transactions, grouping payment method separately from joint amount/currency terms.
7. Verifies the resulting probability against the saved replay score within numerical tolerance and checks additive reconstruction.

Attribution units are `logit(mean member probability)`. A positive contribution increases the score relative to the background; a negative contribution reduces it. The joint transfer group prevents presenting amount and currency replacements as independent effects. These are conditional feature attributions, not evidence that a field caused fraud. Historical memory is held fixed, so the explanation does not attribute every historical account event.

Reports include member scores, baseline/target logits, group contributions, residual, model version and hash. They stay in the local state directory. The automatic federation code never publishes explanation reports or transaction rows.

## 8. Federated training and final transfers

The dashboard's `Collaboration.config` sets `training_protocol="adaptive_ensemble"` and replay size 2,000. New collaboration defaults are four rounds and three local epochs per task. Legacy CLI JSON files default to `legacy` for historical reproducibility; they are not the current dashboard path.

`prepare_frozen_runtime` builds a `ModuleDict` containing the three members, initialized from their verified final checkpoints. Schema metadata includes feature contract, training protocol, roster, member seeds and initial hashes. Every bank and coordinator must match this contract before updates are accepted.

For each round:

1. Banks publish signed readiness. The coordinator waits for the configured roster.
2. The coordinator broadcasts a serialized safetensors ensemble and its identity.
3. Each bank verifies the schema, run, round and base-model hash, then trains all three members on its own June/July stream with context replay.
4. The bank serializes and signs the three-member update. Metadata records the training sample count and actual mean training loss.
5. The coordinator validates one update per configured bank. `aggregate_adaptive` splits state keys by seed and applies equal-client `temporal_harmonized_average` independently for each member.
6. Temporal harmonization reduces conflicting temporal-component updates; the classifier components use equal-client averaging. It is not DP noise or secure aggregation.
7. The coordinator atomically saves the aggregate, manifest and commit marker, then broadcasts the result. Banks verify and save identical returned bytes.
8. A bank can explicitly select the returned ensemble and evaluate it through Transactions. This integration does not automatically select federation rounds by global August performance; all newly selected versions require evaluation.

Stop finishes the current local round; cancel checks cooperative boundaries. These requests affect the local worker, not remote laptops. Restarted active jobs are marked interrupted. Retry/recovery does not claim partial-byte or training-state resume.

## 9. HTTP endpoint map

All mutations require a session token and matching loopback Origin. Hosts other than the exact local address are rejected. These are local prototype protections, not multi-user internet authentication.

| Route | Operation |
|---|---|
| `GET /api/overview`, `POST /api/overview` | Read/save bank identity and current model/evaluation state |
| `GET /api/final-model` | Read original ensemble evidence |
| `POST /api/model/reference` | Restore the original ensemble selection |
| `GET /api/training` | Jobs, dependency availability, default dataset, process status |
| `POST /api/training/start`, `/cancel`, `/activate` | Data check/training, cancellation, verified model selection |
| `GET /api/monitoring`, `/api/monitoring/rows/{id}` | Scoring jobs and completed bank-scoped transaction scores |
| `POST /api/monitoring/start`, `/cancel` | Start/cancel validation scoring |
| `GET /api/explanations`, `POST /api/explanations/start` | Explanation jobs/reports and transaction explanation request |
| `GET /api/results` | Research comparison and local job/federation/transfer evidence |
| `GET /api/privacy` | Explicit implementation privacy status |
| `GET /api/collaboration` | Roles, profiles, readiness, roster and round events |
| `POST /api/collaboration/save`, `/check`, `/start`, `/stop`, `/select` | Configure/check/start/control collaboration and select a returned ensemble |
| `GET /api/settings`, `POST /api/settings` | Non-secret transfer preferences |
| `GET /api/status`, `POST /api/check` | Manual transfer status and broker/peer checks |
| `POST /api/upload`, `/start`, `/cancel`, `/retry`, `/recover` | Opaque upload and transfer lifecycle |
| `GET /api/download/{id}` | Download a verified received file |

## 10. Files, failures and operational limits

Each training/scoring/explanation job has JSON status and a worker log. Writes use a temporary file plus atomic replacement. A completed worker may still be exiting; the API exposes `process_running`, and the UI waits before enabling the next job. SQLite stores transfer jobs and supervised collaboration events. `RuntimeLock` prevents competing supervised processes from using one state folder.

There is no automatic deletion of local evidence. Shutdown requests cancellation or terminates explanation work; an interrupted job cannot masquerade as completed. Missing checkpoints, modified hashes, wrong-bank IDs, changed data and incompatible feature schemas produce errors rather than silent model substitution.

DP, TLS configuration, secure aggregation and independent institutional authentication are not implemented. The repository's real-Kafka acceptance test proves local-process transport and aggregation, not availability across an external network. Exact deployment, multi-laptop firewall/VPN setup and access control remain environment-specific. See [PRIVACY_AUDIT.md](PRIVACY_AUDIT.md).
