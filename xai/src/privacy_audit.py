"""Privacy boundary checks and auditable provenance for XAI artifact release."""
from __future__ import annotations

import json
import hashlib
import hmac
import os
from pathlib import Path
from typing import Any


LOCAL_ONLY_NAMES = {"explanation.json", "explanation.txt", "explanation.html", "historical_events.csv", "feature_contributions.csv", "debug.txt", "paired_case_details.csv"}
DROP_FOR_SHARING = {
    "historical_events", "important_edges", "important_nodes", "background_txn_ids",
    "background_transaction_ids", "account_id", "raw_account_id", "debug", "debug_text",
}
IDENTIFIER_KEYS = {"transaction_id", "txn_id", "event_id", "account_id", "node_id", "source", "target", "src", "dst"}
RAW_VALUE_KEYS = {"value", "amount", "amount_received", "raw_feature_value", "time_since_last_seen_seconds"}


def redact_for_sharing(document: Any, *, key: bytes, pseudonymize_ids: bool = True,
                       drop_keys: set[str] | None = None) -> Any:
    """Remove detailed local evidence and pseudonymize identifier fields recursively."""
    if not key:
        raise ValueError("a non-empty redaction key is required")
    drop = DROP_FOR_SHARING | RAW_VALUE_KEYS | {item.lower() for item in (drop_keys or set())}
    def pseudonym(value: Any) -> str:
        digest = hmac.new(key, str(value).encode("utf-8"), hashlib.sha256).hexdigest()[:16]
        return f"id_{digest}"
    def visit(value: Any, parent_key: str = "") -> Any:
        normalized = parent_key.lower()
        if isinstance(value, dict):
            result = {}
            for raw_key, child in value.items():
                name = str(raw_key)
                lowered = name.lower()
                if lowered in drop:
                    continue
                if lowered in RAW_VALUE_KEYS:
                    continue
                result[name] = visit(child, lowered)
            return result
        if isinstance(value, list):
            return [visit(item, parent_key) for item in value]
        if normalized in IDENTIFIER_KEYS and value is not None:
            return pseudonym(value) if pseudonymize_ids else "[redacted]"
        return value
    return visit(document)


def export_redacted_json(source: Path, destination: Path, *, key: bytes,
                         policy: dict[str, Any] | None = None) -> None:
    """Write a redacted copy; the source local report is never modified."""
    document = json.loads(source.read_text(encoding="utf-8"))
    policy = policy or {}
    clean = redact_for_sharing(document, key=key,
                               pseudonymize_ids=bool(policy.get("pseudonymize_ids", True)),
                               drop_keys=set(policy.get("drop_keys", [])))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(clean, indent=2, default=str) + "\n", encoding="utf-8")


def audit_run(root: Path, *, release_scope: str = "local") -> dict[str, Any]:
    """Summarize provenance and flag local artifacts that should not be shared globally.

    The audit does not claim that aggregate statistics are DP. It checks for
    metadata and prevents row-level explanation files from being classified as
    shareable release material.
    """
    manifest_path = root / "xai_run_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing run manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    local_files = [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and p.name in LOCAL_ONLY_NAMES]
    formal_dp_mode = manifest.get("privacy_mode") in {
        "distributed_dp", "option_a", "secure_central_dp", "client_dp", "central_dp"
    }
    checks = {
        "checkpoint_hash_present": bool(manifest.get("checkpoint_sha256")),
        "evaluation_split_recorded": manifest.get("evaluation_split") in {"validation", "testing"},
        "test_loaded_flag_present": "test_loaded" in manifest,
        "privacy_mode_recorded": bool(manifest.get("privacy_mode")),
        "row_level_reports_marked_local_only": bool(local_files),
        "formal_dp_claim_supported": not formal_dp_mode or bool(manifest.get("accounting")),
    }
    findings = []
    if not checks["formal_dp_claim_supported"]:
        findings.append("DP training mode is marked formal but privacy accounting metadata is missing.")
    if manifest.get("privacy_mode") == "none":
        findings.append("The checkpoint has no formal DP guarantee.")
    findings.append("Transaction-level explanations can reveal information and do not automatically inherit model training DP.")
    if release_scope != "local":
        findings.append("Only sanitized aggregate files may be candidates for sharing; review the recipient and disclosure scope.")
    audit = {"schema_version": 1, "family": manifest.get("family"), "seed": manifest.get("seed"),
             "checkpoint_sha256": manifest.get("checkpoint_sha256"), "source_ref": manifest.get("source_ref"),
             "evaluation_split": manifest.get("evaluation_split"), "test_loaded": manifest.get("test_loaded"),
             "privacy_mode": manifest.get("privacy_mode"), "accounting": manifest.get("accounting", {}),
             "release_scope": release_scope, "checks": checks, "findings": findings,
             "local_only_artifact_count": len(local_files), "local_only_artifacts": local_files,
             "redaction_policy": {"identifiers": "HMAC-SHA256 pseudonyms in exported copies",
                                  "removed": sorted(DROP_FOR_SHARING | RAW_VALUE_KEYS),
                                  "local_sources_modified": False,
                                  "key_source": "caller-supplied secret; do not store it with exported files"}}
    (root / "privacy_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    return audit
