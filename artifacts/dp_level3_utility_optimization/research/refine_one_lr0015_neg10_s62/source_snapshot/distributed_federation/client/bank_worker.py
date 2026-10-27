from __future__ import annotations

from distributed_federation.common.control import check_control

import argparse
import os
import sys
import time

from distributed_federation.common.config import load_config
from distributed_federation.common.events import emit
from distributed_federation.common.kafka_io import make_consumer, make_producer, publish_payload
from distributed_federation.common.model_runtime import (
    deserialize_state,
    prepare_runtime,
    serialize_state,
    train_local,
    validate_state,
    save_state_and_manifest,
)
from distributed_federation.common.protocol import ChunkAssembler, verify_chunk, verify_for_run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one bank's federated-learning worker")
    parser.add_argument("--config", required=True, help="Path to federation JSON configuration")
    parser.add_argument("--client-id", required=True, help="Client ID assigned in the configuration")
    parser.add_argument("--broker", help="Override broker host:port from the JSON file")
    return parser.parse_args()


def required_secret(name: str) -> str:
    value = os.environ.get(name, "")
    if len(value) < 32:
        raise RuntimeError(f"Set {name} to a random secret containing at least 32 characters")
    return value


def main() -> int:
    args = parse_args()
    config = load_config(args.config, args.broker)
    return run(config, args.client_id)


def run(config, client_id) -> int:
    from distributed_federation.privacy.transport import worker
    return worker(config, client_id)


if __name__ == "__main__":
    raise SystemExit(main())
