# Reproduction

Run in `/Users/pj/Desktop/college/capstone/Capstone-DP-SecAgg`.
The existing interpreter is `/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python`.
Use an otherwise equivalent environment from `environment.json` on another host.
All output directories must be new; examples intentionally use `reproduce_*` paths.
The dataset remains at `/Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset`.
Do not fetch LFS, copy the dataset, or score September during selection.

## Tests

```sh
CAPSTONE_DATASET_DIR=/Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset /Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python -m pytest tests -q
/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python scripts/secagg_smoke.py
git diff --check
```

## Nonprivate reference and baseline

```sh
/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python scripts/run_private_federation.py --dataset /Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset --output artifacts/dp_level3_secagg/reproduce_reference --mode none --reference --multipliers 0 --seeds 42 52 62 --rounds 4
/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python scripts/run_private_federation.py --dataset /Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset --output artifacts/dp_level3_secagg/reproduce_baseline --mode none --multipliers 0 --seeds 42 52 62 --rounds 4
```

## Level 2 and SecAgg-only

```sh
/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python scripts/run_private_federation.py --dataset /Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset --output artifacts/dp_level3_secagg/reproduce_level2 --mode secure_central_dp --clip 6.5 --multipliers 0 0.001 --seeds 42 52 62 --rounds 4
```

## Level 3 and old-mechanism Option A comparison

```sh
/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python scripts/run_private_federation.py --dataset /Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset --output artifacts/dp_level3_secagg/reproduce_level3 --mode distributed_dp --clip 6.5 --multipliers 0.00001 0.0001 0.001 0.01 --seeds 42 52 62 --rounds 4
/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python scripts/run_private_federation.py --dataset /Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset --output artifacts/dp_level3_secagg/reproduce_option_a --mode option_a --clip 6.5 --multipliers 0.001 --seeds 42 52 62 --rounds 4
```

For the independent-initialization track, add `--track scratch --rounds 16`.
A private scratch run uses `--mode distributed_dp --multipliers 0.001`; the baseline
uses `--mode none --multipliers 0`. Noise realization is intentionally unreproducible
from a public seed. Model initialization and local training are reproducible;
new private runs should have statistically comparable distributions, not identical
private noise. Reload the saved checkpoints for exact saved-result verification.

## Real local Kafka acceptance

The acceptance evidence used `apache/kafka:3.9.1`, digest
`sha256:4ceccc577f03f51f6af8dbfda55194d0d892f4fa7913ffbded567ce3895622ed`,
on `127.0.0.1:19092`. This is a real local broker, three bank processes and one
coordinator. Topics are `fcl.global-model` (one partition) and `fcl.client-updates`
(three partitions). The harness creates the topics and generates HMAC secrets in
memory; no `.env` is written. With that broker running:

```sh
/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python scripts/kafka_private_acceptance.py --config configs/privacy_distributed_dp.json --rounds 2 --output artifacts/dp_level3_secagg/reproduce_kafka_ddp
/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python scripts/kafka_private_acceptance.py --config configs/privacy_secure_central_dp.json --rounds 2 --output artifacts/dp_level3_secagg/reproduce_kafka_central
```

The normal distributed CLI is unchanged:

```sh
python -m distributed_federation.central.aggregator --config configs/privacy_distributed_dp.json
python -m distributed_federation.client.bank_worker --config configs/privacy_distributed_dp.json --client-id bank-1
```

Run workers 2 and 3 separately with their IDs and corresponding client secret.
Set `FCL_CENTRAL_SECRET` in all processes, `FCL_CLIENT_SECRET` in each bank and
`FCL_CLIENT_SECRET_BANK_1`, `_BANK_2`, `_BANK_3` in the coordinator. Use independent
random secrets, a fresh run ID and a retained output/ledger root. The harness is
the reproducible alternative that handles this without writing secrets.

## August checkpoint reload/evaluation

```sh
/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python scripts/evaluate_private_federation.py --dataset /Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset --checkpoint artifacts/dp_level3_secagg/experiments/warm_distributed_dp_m0.001_s42/global_model.pt --output artifacts/dp_level3_secagg/reproduce_evaluation.json
```

The evaluator also accepts a returned `.safetensors` checkpoint. Model validation
warms temporal state on training before scoring August. There is deliberately no
September/test option. Graph checks used `--split validation` and new output paths
under `artifacts/dp_level3_secagg/visualization`.

## Restart the task-owned local broker

The broker was stopped after QA. On this host, restart it before a Kafka rerun:

```sh
docker start capstone-dp-kafka-20261026
```

The already frozen checkpoint-selection follow-up can be reproduced in a NEW output directory with:

```sh
/Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python scripts/run_private_federation.py --dataset /Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset --output artifacts/dp_level3_secagg/reproduce_selected_validation --mode distributed_dp --clip 6.5 --multipliers 0.00001 --seeds 42 52 62 --rounds 4 --selection best_validation
```

This samples fresh private noise. Do not repeat runs to select a favorable noise sequence. The completed frozen follow-up is negative and remains so in the report.
