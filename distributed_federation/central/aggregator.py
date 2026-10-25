from __future__ import annotations

from distributed_federation.common.control import check_control

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime

from distributed_federation.common.config import load_config, secret_env_name
from distributed_federation.common.events import emit
from distributed_federation.common.kafka_io import make_consumer, make_producer, publish_payload
from distributed_federation.common.model_runtime import (
    deserialize_state,
    fedavg,
    load_initial_checkpoint,
    prepare_runtime,
    prepare_frozen_runtime,
    save_state_and_manifest,
    serialize_state,
    validate_state,
)
from distributed_federation.common.protocol import ChunkAssembler, peek_sender, sha256_bytes, verify_chunk


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the central federated model aggregator")
    parser.add_argument("--config", required=True, help="Path to federation JSON configuration")
    parser.add_argument("--broker", help="Override broker host:port from the JSON file")
    return parser.parse_args()


def required_secret(name: str) -> str:
    value = os.environ.get(name, "")
    if len(value) < 32:
        raise RuntimeError(f"Set {name} to a random secret containing at least 32 characters")
    return value


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def main() -> int:
    args = parse_args()
    config = load_config(args.config, args.broker)
    return run(config)


def run(config) -> int:
    from distributed_federation.privacy.transport import central
    return central(config)


if __name__ == "__main__":
    raise SystemExit(main())
