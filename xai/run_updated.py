#!/usr/bin/env python3
"""Run the cached XAI engine on frozen Sia or DP checkpoints.

The XAI Python sources were not included in this folder; Python 3.12 bytecode is
preserved as versioned runtime assets in ``engine_py312``. This runner loads
those immutable modules and adds branch-aware checkpoint staging and validation-only execution.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from typing import Any


XAI_ROOT = Path(__file__).resolve().parent
ENGINE_ROOT = XAI_ROOT / "engine_py312"
REPO_ROOT = XAI_ROOT.parent
DATASET = REPO_ROOT / "data" / "final_temporal_dataset"
VAL_SPLITS = ("training", "validation")
BANKS = ("JPMorgan_Chase", "Wells_Fargo", "Key_Bank")


FAMILIES: dict[str, dict[str, Any]] = {
    "sia_context_harmonized": {
        "ref": "origin/sia",
        "base": "artifacts/research_adaptive_fcl/warm_start/federated/context_harmonized/seed_{seed}",
        "metrics": "metrics.json",
        "label": "Sia context replay + temporal harmonization",
        "privacy": {"mode": "none", "formal_dp": False},
    },
    "dp_warm_none": {
        "ref": "origin/philip-dp-secagg-ddp",
        "base": "artifacts/dp_level3_secagg/experiments/warm_none_m0_s{seed}",
        "metrics": "results.json",
        "label": "DP study warm non-private comparator",
        "privacy": {"mode": "none", "formal_dp": False},
    },
    "dp_distributed_1e-5": {
        "ref": "origin/philip-dp-secagg-ddp",
        "base": "artifacts/dp_level3_secagg/experiments/warm_distributed_dp_m1e-05_s{seed}",
        "metrics": "results.json",
        "label": "Distributed DP, multiplier 1e-5, fixed-final selection",
        "privacy": {"mode": "distributed_dp", "formal_dp": True},
    },
    "dp_distributed_1e-5_best_validation": {
        "ref": "origin/philip-dp-secagg-ddp",
        "base": "artifacts/dp_level3_secagg/experiments/warm_distributed_dp_m1e-05_s{seed}_best_validation",
        "metrics": "results.json",
        "label": "Distributed DP, multiplier 1e-5, best-August selection",
        "privacy": {"mode": "distributed_dp", "formal_dp": True},
    },
    "dp_distributed_0.001": {
        "ref": "origin/philip-dp-secagg-ddp",
        "base": "artifacts/dp_level3_secagg/experiments/warm_distributed_dp_m0.001_s{seed}",
        "metrics": "results.json",
        "label": "Distributed DP, multiplier 0.001, fixed-final selection",
        "privacy": {"mode": "distributed_dp", "formal_dp": True},
    },
    "dp_distributed_0.01": {
        "ref": "origin/philip-dp-secagg-ddp",
        "base": "artifacts/dp_level3_secagg/experiments/warm_distributed_dp_m0.01_s{seed}",
        "metrics": "results.json",
        "label": "Distributed DP, multiplier 0.01, fixed-final selection",
        "privacy": {"mode": "distributed_dp", "formal_dp": True},
    },
    "dp_option_a_0.001": {
        "ref": "origin/philip-dp-secagg-ddp",
        "base": "artifacts/dp_level3_secagg/experiments/warm_option_a_m0.001_s{seed}",
        "metrics": "results.json",
        "label": "Option A local DP, multiplier 0.001",
        "privacy": {"mode": "option_a", "formal_dp": True},
    },
    "dp_secure_central_0.001": {
        "ref": "origin/philip-dp-secagg-ddp",
        "base": "artifacts/dp_level3_secagg/experiments/warm_secure_central_dp_m0.001_s{seed}",
        "metrics": "results.json",
        "label": "Secure central DP, multiplier 0.001",
        "privacy": {"mode": "secure_central_dp", "formal_dp": True},
    },
}


class CachedXaiFinder(importlib.abc.MetaPathFinder):
    """Load the preserved CPython 3.12 source-less runtime assets."""

    def find_spec(self, fullname: str, path: Any = None, target: Any = None):
        if not fullname.startswith("xai."):
            return None
        module_name = fullname.rsplit(".", 1)[1]
        bytecode = ENGINE_ROOT / f"{module_name}.cpython-312.pyc"
        if not bytecode.is_file():
            return None
        loader = importlib.machinery.SourcelessFileLoader(fullname, str(bytecode))
        return importlib.util.spec_from_loader(fullname, loader)


def load_cached_engine(ref: str):
    if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 12):
        raise RuntimeError("The source-less XAI scoring engine requires CPython 3.12; use an existing compatible environment. Editable utility tests do not require the engine.")
    # XAI must hash and import the same model implementation that produced the
    # selected checkpoint. The two source branches have small but real changes.
    model_path = XAI_ROOT / "src" / "gnn" / "causal_temporal_graphsage.py"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_bytes(git_blob(ref, "src/gnn/causal_temporal_graphsage.py"))
    # The XAI model copy is first so imports and its source hash refer to the
    # same implementation used to train the selected checkpoints.
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    if str(XAI_ROOT) not in sys.path:
        sys.path.insert(0, str(XAI_ROOT))
    package = types.ModuleType("xai")
    package.__path__ = [str(XAI_ROOT)]
    package.__package__ = "xai"
    package.__file__ = str(XAI_ROOT / "__init__.py")
    sys.modules["xai"] = package
    sys.meta_path.insert(0, CachedXaiFinder())

    import xai.cli  # type: ignore[import-not-found]
    import xai.preprocessing  # type: ignore[import-not-found]
    import xai.temporal  # type: ignore[import-not-found]
    import src.gnn.causal_temporal_graphsage as model_module

    # The original engine predates validation-only experiment artifacts.
    # Narrow every data loader, including function defaults bound at import time.
    model_module.SPLITS = VAL_SPLITS
    model_module.load_bank_frames.__defaults__ = (VAL_SPLITS,)
    model_module.build_bank_data.__defaults__ = (None, None, VAL_SPLITS)
    xai.preprocessing.SPLITS = VAL_SPLITS
    xai.temporal.SPLITS = VAL_SPLITS
    if ref == "origin/philip-dp-secagg-ddp":
        # DP artifacts use the fixed, public feature contract embedded by the
        # federation runtime. The legacy XAI migration would otherwise refit
        # participant-derived encoders and fail score parity.
        schema = json.loads(git_blob(ref, "artifacts/dp_level3_secagg/feature_schema.json"))

        def encoder_spec(kind: str) -> dict[str, Any]:
            groups = schema[kind]
            numeric = groups["numeric"]
            categorical = groups["categorical"]
            parts = []
            if numeric:
                parts.append({
                    "kind": "numeric", "columns": [item["name"] for item in numeric],
                    "impute": [item.get("median") for item in numeric],
                    "valid": list(range(len(numeric))),
                    "mean": [item["mean"] for item in numeric],
                    "scale": [item["scale"] for item in numeric],
                })
            if categorical:
                parts.append({
                    "kind": "categorical", "columns": [item["name"] for item in categorical],
                    "impute": [item.get("fill") for item in categorical],
                    "valid": list(range(len(categorical))),
                    "categories": [item["categories"] for item in categorical],
                })
            return {"columns": schema["node_columns" if kind == "nodes" else "edge_columns"],
                    "parts": parts,
                    "encoded_columns": (
                        [f"numeric__{item['name']}" for item in numeric]
                        + [f"categorical__{item['name']}_{category}"
                           for item in categorical for category in item["categories"]]
                    )}

        node_spec, edge_spec = encoder_spec("nodes"), encoder_spec("edges")
        def frozen_encoders(_dataset: Path):
            return xai.preprocessing.FrozenEncoder(node_spec), xai.preprocessing.FrozenEncoder(edge_spec)
        xai.preprocessing.fit_shared_feature_encoders = frozen_encoders
        xai.preprocessing.dump_encoder = lambda encoder: encoder.spec
    return xai.cli


def git_blob(ref: str, relative_path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{ref}:{relative_path}"],
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_checkpoint_for_engine(checkpoint: bytes) -> bytes:
    """Add architecture metadata absent from the DP checkpoint wrapper.

    This preserves every tensor byte-for-byte and infers the hidden width from
    the serialized model weights. The original downloaded blob hash remains the
    checkpoint provenance hash in reports.
    """
    import torch

    payload = torch.load(io.BytesIO(checkpoint), map_location="cpu", weights_only=False)
    args = payload.setdefault("args", {})
    if "hidden_channels" in args:
        return checkpoint
    state = payload.get("state_dict", {})
    projection = state.get("static_projection.weight")
    if projection is None or len(projection.shape) != 2:
        raise ValueError("cannot infer hidden_channels from checkpoint architecture")
    args["hidden_channels"] = int(projection.shape[0])
    buffer = io.BytesIO()
    torch.save(payload, buffer)
    return buffer.getvalue()


def dp_encoder_specs(schema: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Convert the DP runtime's fixed schema into the cached adapter's format."""
    def convert(kind: str, raw_columns: str) -> dict[str, Any]:
        groups = schema[kind]
        numeric, categorical = groups["numeric"], groups["categorical"]
        parts: list[dict[str, Any]] = []
        if numeric:
            parts.append({
                "kind": "numeric", "columns": [item["name"] for item in numeric],
                "impute": [item.get("median") for item in numeric],
                "valid": list(range(len(numeric))), "mean": [item["mean"] for item in numeric],
                "scale": [item["scale"] for item in numeric],
            })
        if categorical:
            parts.append({
                "kind": "categorical", "columns": [item["name"] for item in categorical],
                "impute": [item["fill"] for item in categorical],
                "valid": list(range(len(categorical))),
                "categories": [item["categories"] for item in categorical],
            })
        encoded = ([f"numeric__{item['name']}" for item in numeric]
                   + [f"categorical__{item['name']}_{value}"
                      for item in categorical for value in item["categories"]])
        return {"columns": schema[raw_columns], "parts": parts, "encoded_columns": encoded}
    return convert("nodes", "node_columns"), convert("edges", "edge_columns")


def prepare_dp_artifact(
    output: Path, checkpoint_path: Path, checkpoint_hash: str,
    raw_metrics: dict[str, Any], schema: dict[str, Any], model_module: Any,
) -> dict[str, Any]:
    """Reproduce DP validation via its archived runtime schema; fail closed on mismatch."""
    import numpy as np
    import torch
    import xai.preprocessing as preprocessing  # type: ignore[import-not-found]

    # Match distributed_federation.common.model_runtime._imports exactly.
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)

    node_spec, edge_spec = dp_encoder_specs(schema)
    node_encoder = preprocessing.FrozenEncoder(node_spec)
    edge_encoder = preprocessing.FrozenEncoder(edge_spec)
    payload = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    expected_by_bank = {item["bank"]: item for item in raw_metrics["final"]["per_bank"]}
    artifact: dict[str, Any] = {
        "version": 1, "mode": "federated", "checkpoint_sha256": checkpoint_hash,
        "origin": "verified_dp_frozen_feature_schema", "original_fitted_object_available": True,
        "node_encoder": node_spec, "edge_encoder": edge_spec,
        "software": {"torch": torch.__version__, "numpy": np.__version__},
        "banks": {}, "training_inputs_sha256": {},
        "original_model_source_sha256": sha256((XAI_ROOT / "src/gnn/causal_temporal_graphsage.py").read_bytes()),
        "metrics_sha256": sha256(json.dumps(raw_metrics, sort_keys=True).encode()),
        "testing_predictions_available": False, "evaluation_split": "validation", "test_loaded": False,
    }
    errors: dict[str, Any] = {}
    output.mkdir(parents=True, exist_ok=True)
    for bank in BANKS:
        static, streams, _, _ = model_module.build_bank_data(
            DATASET, bank, node_encoder=node_encoder, edge_encoder=edge_encoder, splits=VAL_SPLITS
        )
        model = model_module.CausalTemporalGraphSAGE(
            static.shape[1], streams["training"].edge_attr.shape[1],
            int(payload["args"]["hidden_channels"]), 0.25,
        ).cpu()
        model.load_state_dict(payload["state_dict"], strict=True)
        state = model.initial_state(static)
        _, _, state = model_module.score_stream(model, state, streams["training"], 1024)
        probabilities, labels, _ = model_module.score_stream(model, state, streams["validation"], 1024)
        expected = expected_by_bank[bank]
        threshold = float(expected["threshold"])
        computed = model_module.metric_block(labels, probabilities, threshold)
        bank_errors = {key: abs(float(computed[key]) - float(expected["validation"][key]))
                       for key in expected["validation"]}
        errors[bank] = bank_errors
        passed = all(value <= 1e-10 for value in bank_errors.values())
        local = output / "local" / bank
        local.mkdir(parents=True, exist_ok=True)
        reference_path = local / "reference_predictions.npz"
        np.savez_compressed(reference_path, validation=probabilities.astype(np.float32),
                            testing=np.empty(0, dtype=np.float32))
        hashes = preprocessing.dataset_hashes(DATASET, bank)
        artifact["banks"][bank] = {
            "passed": passed, "threshold": threshold, "batch_size": 1024,
            "encoded_tensors_bitwise_equal": None,
            "evaluation": {"validation": {"metrics": computed,
                                             "saved_metric_absolute_errors": bank_errors,
                                             "max_probability_error": None}},
            "reference_sha256": sha256(reference_path.read_bytes()), "input_sha256": hashes,
        }
        artifact["training_inputs_sha256"].update(hashes)
        if not passed:
            raise ValueError(f"DP validation parity failed for {bank}: {bank_errors}")
    preprocessing_path = output / "preprocessing.json"
    preprocessing_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return {"preprocessing_path": str(preprocessing_path), "bank_metric_errors": errors,
            "test_loaded": False, "checkpoint_sha256": checkpoint_hash,
            "feature_schema_source": "origin/philip-dp-secagg-ddp:artifacts/dp_level3_secagg/feature_schema.json"}


def preflight_dp_cases(output: Path, checkpoint_path: Path, cases: dict[str, list[str]]) -> dict[str, Any]:
    """Check individual XAI target scores against frozen stream predictions before reports."""
    import numpy as np
    import xai.temporal as temporal  # type: ignore[import-not-found]

    results = []
    for bank, txn_ids in cases.items():
        reference_path = output / "local" / bank / "reference_predictions.npz"
        with np.load(reference_path, allow_pickle=False) as saved:
            reference = saved["validation"]
        adapter = temporal.TemporalAdapter(
            DATASET, checkpoint_path, bank, "federated", output / "preprocessing.json", reference_path
        )
        frame = adapter.frames["validation"]
        for txn_id in txn_ids:
            index = int(adapter.index("validation", str(txn_id)))
            state, _, _ = adapter.context("validation", index, 8)
            logits = adapter.predictor(state, "validation", index)(frame.iloc[[index]])
            score = float(1.0 / (1.0 + np.exp(-np.clip(float(np.asarray(logits).reshape(-1)[0]), -40, 40))))
            expected = float(reference[index])
            results.append({"bank": bank, "transaction_id": str(txn_id), "index": index,
                            "stream_probability": expected, "xai_probability": score,
                            "absolute_error": abs(expected - score), "passed": abs(expected - score) <= 1e-6})
    result = {"method": "pre-report target parity check", "tolerance": 1e-6,
              "passed": all(item["passed"] for item in results), "cases": results,
              "test_loaded": False}
    (output / "target_parity_preflight.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def translated_metrics(family: str, raw: dict[str, Any]) -> dict[str, Any]:
    if family == "sia_context_harmonized":
        return raw
    selected = raw.get("final") or {}
    per_bank = selected.get("per_bank")
    if not isinstance(per_bank, list) or not per_bank:
        raise ValueError("DP results do not contain selected-round per-bank validation metrics")
    return {
        "configuration": {
            "mode": "federated",
            "calibration": "none",
            "seed": raw.get("seed"),
            "track": raw.get("track"),
            "selection": raw.get("selection"),
        },
        "per_bank": per_bank,
        "privacy": raw.get("privacy"),
        "accounting": raw.get("accounting"),
        "test_loaded": bool(raw.get("test_loaded", False)),
    }


def patch_validation_artifact(output: Path) -> None:
    """Mark the old engine's required testing key as explicitly unavailable."""
    artifact_path = output / "preprocessing.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    for bank, bank_data in artifact["banks"].items():
        predictions = output / "local" / bank / "reference_predictions.npz"
        import numpy as np

        with np.load(predictions, allow_pickle=False) as saved:
            arrays = {name: saved[name] for name in saved.files}
        arrays.setdefault("testing", np.empty(0, dtype=np.float32))
        np.savez_compressed(predictions, **arrays)
        bank_data["reference_sha256"] = sha256(predictions.read_bytes())
    artifact["testing_predictions_available"] = False
    artifact["evaluation_split"] = "validation"
    artifact["test_loaded"] = False
    artifact["validation_only_note"] = (
        "The source checkpoint was selected without loading the test split. "
        "The cached XAI adapter requires a testing key; it is an empty array and no test rows were loaded."
    )
    artifact_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")


def add_provenance(output: Path, provenance: dict[str, Any]) -> None:
    old_sentence = "No combined federated-continual checkpoint or formal differential privacy is implemented."
    if provenance["privacy_mode"] == "none":
        replacement = (
            "This explanation uses a federated continual checkpoint. "
            "The model was not trained with a formal differential-privacy mechanism."
        )
    else:
        replacement = (
            f"This model used {provenance['privacy_mode']} training. "
            "The experiment's client-level privacy accounting is recorded in xai_run_manifest.json. "
            "A transaction-level explanation is not automatically differentially private."
        )

    for path in output.rglob("*"):
        if path.is_dir():
            continue
        if path.name in {"explanation.json", "summary.json", "shareable_statistics.json"}:
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            document["xai_provenance"] = provenance
            def replace(value: Any) -> Any:
                if isinstance(value, str):
                    return value.replace(old_sentence, replacement)
                if isinstance(value, list):
                    return [replace(item) for item in value]
                if isinstance(value, dict):
                    return {key: replace(item) for key, item in value.items()}
                return value
            path.write_text(json.dumps(replace(document), indent=2) + "\n", encoding="utf-8")
        elif path.suffix.lower() in {".txt", ".html"}:
            text = path.read_text(encoding="utf-8")
            if old_sentence in text:
                path.write_text(text.replace(old_sentence, replacement), encoding="utf-8")

    (output / "xai_run_manifest.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )


def load_case_manifest(path: Path) -> dict[str, list[str]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return {bank: [str(txn) for txn in values] for bank, values in document["cases"].items()}


def build_case_manifest(output: Path, path: Path, banks: tuple[str, ...], count: int) -> dict[str, list[str]]:
    cases: dict[str, list[str]] = {}
    for bank in banks:
        reports = sorted((output / "local" / bank).glob("reports/validation_*/explanation.json"))
        ids = []
        for report in reports:
            doc = json.loads(report.read_text(encoding="utf-8"))
            txn_id = str(doc.get("transaction_id", ""))
            if txn_id and txn_id not in ids:
                ids.append(txn_id)
        if len(ids) < count:
            raise RuntimeError(f"only {len(ids)} validation cases were generated for {bank}; expected {count}")
        cases[bank] = ids[:count]
    document = {
        "schema_version": 1,
        "selected_from": "Sia context-harmonized seed 42 August validation, balanced selection",
        "selection_note": "Fixed transaction IDs are reused for paired checkpoint comparisons.",
        "cases": cases,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return cases


def augment_counterfactuals(cli: Any, output: Path, checkpoint: Path, banks: list[str], txn_ids: dict[str, list[str]]) -> None:
    """Attach constrained amount alternatives using the engine's pre-event scorer."""
    import xai.temporal as temporal  # type: ignore[import-not-found]
    from xai.src.counterfactuals import constrained_amount_counterfactuals

    for bank in banks:
        prediction_path = output / "local" / bank / "reference_predictions.npz"
        adapter = temporal.TemporalAdapter(
            DATASET, checkpoint, bank, "federated", output / "preprocessing.json", prediction_path
        )
        training = adapter.frames["training"]
        for txn_id in txn_ids.get(bank, []):
            reports = list((output / "local" / bank).glob("reports/validation_*/explanation.json"))
            report_path = None
            for candidate in reports:
                doc = json.loads(candidate.read_text(encoding="utf-8"))
                if str(doc.get("transaction_id")) == txn_id:
                    report_path = candidate
                    break
            if report_path is None:
                continue
            doc = json.loads(report_path.read_text(encoding="utf-8"))
            if doc.get("counterfactual_explanation"):
                continue
            index = int(adapter.index("validation", txn_id))
            state, _, _ = adapter.context("validation", index, 8)
            row = adapter.frames["validation"].iloc[index]
            scorer = adapter.predictor(state, "validation", index)
            doc["counterfactual_explanation"] = constrained_amount_counterfactuals(
                row, training, scorer, threshold=float(doc["prediction"]["threshold"])
            )
            report_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def run_one(cli: Any, family: str, seed: int, args: argparse.Namespace) -> None:
    spec = FAMILIES[family]
    ref = spec["ref"]
    base = spec["base"].format(seed=seed)
    checkpoint = git_blob(ref, f"{base}/global_model.pt")
    metric_blob = git_blob(ref, f"{base}/{spec['metrics']}")
    raw_metrics = json.loads(metric_blob)
    metrics = translated_metrics(family, raw_metrics)
    output = XAI_ROOT / "outputs" / "updated" / family / f"seed_{seed}"

    model_source = (XAI_ROOT / "src" / "gnn" / "causal_temporal_graphsage.py").read_bytes()
    branch_source = git_blob(ref, "src/gnn/causal_temporal_graphsage.py")
    if sha256(model_source) != sha256(branch_source):
        raise ValueError(f"XAI model source does not match {ref} for {family}")

    privacy = raw_metrics.get("privacy", {}) if family != "sia_context_harmonized" else spec["privacy"]
    final_checkpoint_hash = sha256(checkpoint)
    checkpoint_hash_in_metrics = raw_metrics.get("checkpoint_sha256")
    artifact_manifest = json.loads(git_blob(ref, "artifacts/dp_level3_secagg/ARTIFACT_MANIFEST.json")) if family != "sia_context_harmonized" else {}
    manifest_artifact = artifact_manifest.get("files", {}).get(f"{base}/global_model.pt", {}) if artifact_manifest else {}
    initial_checkpoint_relative = f"artifacts/final_evaluation/corrected_fedavg/seed_{seed}/global_model.pt"
    initial_checkpoint_hash = sha256(git_blob(ref, initial_checkpoint_relative)) if family != "sia_context_harmonized" else None
    manifest = {
        "family": family,
        "label": spec["label"],
        "source_ref": ref,
        "checkpoint_path": f"{ref}:{base}/global_model.pt",
        "checkpoint_sha256": final_checkpoint_hash,
        "metrics_path": f"{ref}:{base}/{spec['metrics']}",
        "source_metrics_sha256": sha256(metric_blob),
        "checkpoint_hash_in_metrics": checkpoint_hash_in_metrics,
        "checkpoint_hash_matches_metrics": checkpoint_hash_in_metrics in (None, final_checkpoint_hash),
        "initial_checkpoint_path_in_results": raw_metrics.get("checkpoint"),
        "initial_checkpoint_relative_path": initial_checkpoint_relative if family != "sia_context_harmonized" else None,
        "initial_checkpoint_sha256": initial_checkpoint_hash,
        "initial_checkpoint_hash_matches_results": initial_checkpoint_hash == checkpoint_hash_in_metrics if family != "sia_context_harmonized" else None,
        "artifact_manifest_sha256": manifest_artifact.get("sha256"),
        "checkpoint_hash_matches_artifact_manifest": manifest_artifact.get("sha256") in (None, final_checkpoint_hash),
        "checkpoint_hash_semantics": (
            "results.json checkpoint_sha256 and checkpoint path identify the initial conditional checkpoint; "
            "the experiment output global_model.pt is the final trained model and is hashed separately"
            if family != "sia_context_harmonized" and checkpoint_hash_in_metrics != final_checkpoint_hash
            else "checkpoint hash identifies the selected model file"
        ),
        "seed": seed,
        "evaluation_split": "validation",
        "test_loaded": False,
        "privacy_mode": privacy.get("mode", "none"),
        "privacy": privacy,
        "validation_metrics": raw_metrics.get("per_bank", ()),
        "accounting": raw_metrics.get("accounting", {}),
        "selection": raw_metrics.get("selection", "validation checkpoint selection"),
        "privacy_disclaimer": (
            "XAI reports are per-transaction outputs and do not automatically inherit the model's training privacy guarantee."
            if privacy.get("mode", "none") != "none"
            else "This model was not trained with a formal differential-privacy mechanism."
        ),
    }

    staging_root = REPO_ROOT / "tmp"
    staging_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="capstone_xai_", dir=staging_root) as temp_name:
        staged = Path(temp_name)
        checkpoint_path = staged / "global_model.pt"
        checkpoint_path.write_bytes(normalize_checkpoint_for_engine(checkpoint))
        (staged / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            existing = output / "xai_run_manifest.json"
            if existing.exists():
                saved = json.loads(existing.read_text(encoding="utf-8"))
                if saved.get("checkpoint_sha256") != manifest["checkpoint_sha256"]:
                    raise FileExistsError(f"Existing output belongs to a different checkpoint: {output}")
            elif (output / "preprocessing.json").exists():
                # Resume the previously interrupted seed-42 baseline output.
                pass
            else:
                raise FileExistsError(f"Output exists without a resumable preprocessing artifact: {output}")
        if family == "sia_context_harmonized" and not (output / "preprocessing.json").exists():
            try:
                cli.main([
                    "prepare", "--banks", *BANKS, "--mode", "federated",
                    "--checkpoint", str(checkpoint_path),
                    "--dataset-dir", str(DATASET), "--output-dir", str(output),
                    "--threads", str(args.threads),
                ])
            except Exception as exc:
                if "Saved experiment metrics do not reproduce" in str(exc):
                    diagnostic = XAI_ROOT / "outputs" / "updated" / "diagnostics" / family / f"seed_{seed}.json"
                    diagnostic.parent.mkdir(parents=True, exist_ok=True)
                    diagnostic.write_text(json.dumps({
                        "family": family, "seed": seed, "source_ref": ref,
                        "checkpoint_path": manifest["checkpoint_path"],
                        "checkpoint_sha256": manifest["checkpoint_sha256"],
                        "checkpoint_hash_in_metrics": manifest["checkpoint_hash_in_metrics"],
                        "checkpoint_hash_matches_metrics": manifest["checkpoint_hash_matches_metrics"],
                        "metrics_path": manifest["metrics_path"], "test_loaded": False,
                        "status": "blocked_by_prediction_parity", "error": str(exc),
                        "note": "No XAI reports were generated because model scores did not reproduce the saved validation metrics.",
                    }, indent=2) + "\n", encoding="utf-8")
                raise
        elif family != "sia_context_harmonized" and not (
            (output / "preprocessing.json").exists()
            and (output / "xai_run_manifest.json").exists()
            and json.loads((output / "xai_run_manifest.json").read_text(encoding="utf-8")).get("validation_parity")
        ):
            import src.gnn.causal_temporal_graphsage as dp_model  # type: ignore[import-not-found]
            dp_schema = json.loads(git_blob(ref, "artifacts/dp_level3_secagg/feature_schema.json"))
            dp_verification = prepare_dp_artifact(
                output, checkpoint_path, sha256(checkpoint_path.read_bytes()), raw_metrics, dp_schema, dp_model
            )
            manifest["xai_checkpoint_sha256"] = sha256(checkpoint_path.read_bytes())
            manifest["validation_parity"] = dp_verification
        patch_validation_artifact(output)

        case_manifest_path = XAI_ROOT / "outputs" / "updated" / "case_manifest.json"
        cases = None
        if case_manifest_path.exists():
            cases = load_case_manifest(case_manifest_path)
        elif family != "sia_context_harmonized" or seed != 42:
            raise FileNotFoundError("Run Sia context-harmonized seed 42 first to establish fixed validation cases.")
        if family != "sia_context_harmonized" and cases is not None:
            target_parity = preflight_dp_cases(output, checkpoint_path, cases)
            manifest["target_parity_preflight"] = target_parity
            if not target_parity["passed"]:
                diagnostic = XAI_ROOT / "outputs" / "updated" / "diagnostics" / family / f"seed_{seed}.json"
                diagnostic.parent.mkdir(parents=True, exist_ok=True)
                diagnostic.write_text(json.dumps({
                    "family": family, "seed": seed, "source_ref": ref,
                    "checkpoint_sha256": final_checkpoint_hash,
                    "checkpoint_hash_in_results": checkpoint_hash_in_metrics,
                    "checkpoint_hash_matches_artifact_manifest": manifest["checkpoint_hash_matches_artifact_manifest"],
                    "validation_metric_parity": manifest.get("validation_parity"),
                    "target_parity_preflight": target_parity,
                    "status": "blocked_by_target_prediction_parity",
                    "note": "The experiment validation metrics reproduce through its frozen schema and checkpoint, but at least one individual XAI target score does not match the full-stream score. No new transaction reports were generated.",
                }, indent=2) + "\n", encoding="utf-8")
                raise ValueError(f"DP target parity preflight failed; see {diagnostic}")

        for bank in args.banks:
            if cases is None:
                # The initial baseline chooses balanced rows; these IDs become
                # the shared case set for all later checkpoints and seeds.
                existing_reports = list((output / "local" / bank).glob("reports/validation_*/explanation.json"))
                if len(existing_reports) < args.samples:
                    cli.main([
                        "explain", "--bank", bank, "--mode", "federated",
                        "--checkpoint", str(checkpoint_path), "--dataset-dir", str(DATASET),
                        "--output-dir", str(output), "--preprocessing", str(output / "preprocessing.json"),
                        "--split", "validation", "--num-samples", str(args.samples),
                        "--selection", args.selection, "--threads", str(args.threads),
                    ])
            else:
                for txn_id in cases.get(bank, []):
                    already = False
                    for report in (output / "local" / bank).glob("reports/validation_*/explanation.json"):
                        if str(json.loads(report.read_text(encoding="utf-8")).get("transaction_id")) == txn_id:
                            already = True; break
                    if already:
                        continue
                    cli.main([
                        "explain", "--bank", bank, "--mode", "federated",
                        "--checkpoint", str(checkpoint_path), "--dataset-dir", str(DATASET),
                        "--output-dir", str(output), "--preprocessing", str(output / "preprocessing.json"),
                        "--split", "validation", "--txn-id", txn_id, "--threads", str(args.threads),
                    ])
        if cases is None:
            cases = build_case_manifest(output, case_manifest_path, tuple(args.banks), args.samples)
        augment_counterfactuals(cli, output, checkpoint_path, list(args.banks), cases)
    add_provenance(output, manifest)
    from xai.src.privacy_audit import audit_run
    audit_run(output)
    print(f"Saved {family} seed {seed}: {output}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", choices=tuple(FAMILIES), required=True)
    parser.add_argument("--seeds", nargs="+", type=int, choices=(42, 52, 62), default=(42, 52, 62))
    parser.add_argument("--banks", nargs="+", choices=BANKS, default=BANKS)
    parser.add_argument("--samples", type=int, default=2, help="Illustrative examples per bank")
    parser.add_argument("--selection", choices=("balanced", "random"), default="balanced")
    parser.add_argument("--threads", type=int, default=1)
    args = parser.parse_args()
    if args.samples < 1 or args.threads < 1:
        parser.error("--samples and --threads must be positive")
    return args


def main() -> None:
    args = parse_args()
    ref = FAMILIES[args.family]["ref"]
    cli = load_cached_engine(ref)
    for seed in args.seeds:
        run_one(cli, args.family, seed, args)


if __name__ == "__main__":
    main()
