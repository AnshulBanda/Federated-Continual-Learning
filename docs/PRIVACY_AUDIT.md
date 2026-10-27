# Final-path privacy audit

**Finding: differential privacy is not implemented in the final ensemble's training or transfer pipeline.** No epsilon/delta guarantee is available. This audit covers the integrated dashboard, its three adaptive members, automatic federation, manual file transfers and local explanations.

| Control | Finding | Code evidence |
|---|---|---|
| Bank-local transaction training | Implemented; each worker reads its configured bank | `prepare_frozen_runtime`, `train_local` in `distributed_federation/common/model_runtime.py` |
| Shared preprocessing | Fixed synthetic-reference training contract; not privately estimated | `feature_schema.json`, `FrozenEncoder`, `scripts/export_federation_schema.py` |
| Gradient clipping | Present for optimizer stability; insufficient for DP | `train_temporal_epoch` in `src/gnn/causal_temporal_graphsage.py` |
| DP noise | Absent in the final training/update path | `train_client`, `train_local`, `aggregate_adaptive` |
| Privacy accounting | Absent; no accountant, epsilon, delta or release budget | Final checkpoints and runtime schema |
| Update clipping/harmonization | Temporal optimization operation; no DP claim | `temporal_harmonized_average` |
| Transport integrity | HMAC authentication and SHA-256 verification, signed chunks and receipts | `distributed_federation/common/protocol.py`, `streaming/app/transfers.py` |
| Independent bank identity | Not established by one shared team secret | Collaboration/transfer configuration |
| Kafka TLS | Not configured by application producers/consumers | `distributed_federation/common/kafka_io.py`, `streaming/app/transfers.py` |
| Secure aggregation | Absent; coordinator deserializes individual updates | `distributed_federation/central/aggregator.py` |
| Explanation release | Local jobs only; no automatic publication through federation | `streaming/app/explanations.py` |

## What reaches the coordinator

Automatic collaboration sends safetensors parameter dictionaries for all three ensemble members, plus run, round, sender, schema/base-model identities and training diagnostics. Transaction graphs are not included in these payloads. Nevertheless, keeping raw data local is not a formal guarantee against inference from parameter updates.

The coordinator can read each client update before aggregation. The temporal conflict correction is an optimization algorithm, not cryptographic secure aggregation. Final checkpoint manifests explicitly report `differential_privacy: false` and no accountant.

Manual transfer is byte-preserving: it neither adds noise nor validates the training privacy of an arbitrary uploaded file. A separately trained DP model could theoretically be transported, but the transfer protocol itself cannot certify that claim. Final reference checkpoints in this project have no formal DP training guarantee.

## Why existing controls are not DP

Optimizer gradient clipping bounds gradients during training. The current code does not pair it with an appropriately calibrated randomized mechanism and a defined neighboring-dataset relation/accountant. Hashing proves file integrity. HMAC proves possession of the shared secret. Neither hides information contained in model parameters. Private-network transport, if configured externally, addresses transport confidentiality rather than model-training privacy.

The XAI directory contains reports from other historical configurations, some named with privacy-related terminology. Their names or metadata do not establish DP for the final `context_harmonized` checkpoints. The dashboard reports the controls of the actual selected final path.

## Explanations

Explanations include transaction-specific scores, fields and attribution values. They are generated locally and not passed to the automatic federation publisher. They do not inherit DP merely because they are derived from a model. The existing XAI redaction utilities can create reduced exports, but redaction/pseudonymization is not a substitute for a formal privacy mechanism.

## Review statement

“We implement bank-local training and authenticated, integrity-checked model transfers. Differential privacy, secure aggregation and application-configured Kafka TLS are not implemented in this final path.”

Adding formal DP is a separate model/protocol change requiring a privacy unit, bounded sensitivity, calibrated noise, accounting across rounds/releases and fresh utility evaluation. It would change the trained result; the existing 90.68% score must not be relabeled as a DP result.
