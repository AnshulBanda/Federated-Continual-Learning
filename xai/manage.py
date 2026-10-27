#!/usr/bin/env python3
"""Generate paired XAI comparisons, privacy audits, and a local review dashboard."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from src.checkpoint_comparison import compare_checkpoints
from src.dashboard import build_dashboard
from src.privacy_audit import audit_run, export_redacted_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    compare = sub.add_parser("compare", help="Compare checkpoints on identical bank/transaction cases")
    compare.add_argument("--run", action="append", required=True, metavar="NAME=PATH",
                         help="Run output root; pass at least two, e.g. sia42=xai/outputs/updated/sia.../seed_42")
    compare.add_argument("--output", type=Path, required=True)
    dashboard = sub.add_parser("dashboard", help="Build a static local XAI review HTML")
    dashboard.add_argument("--reports", type=Path, required=True)
    dashboard.add_argument("--output", type=Path, required=True)
    audit = sub.add_parser("audit", help="Audit a run's provenance and privacy boundary")
    audit.add_argument("--run", type=Path, required=True)
    audit.add_argument("--release-scope", choices=("local", "aggregate", "external"), default="local")
    redact = sub.add_parser("redact", help="Write a redacted shareable JSON copy without changing local source")
    redact.add_argument("--source", type=Path, required=True)
    redact.add_argument("--output", type=Path, required=True)
    redact.add_argument("--key-env", default="XAI_REDACTION_KEY", help="Environment variable containing a secret key")
    redact.add_argument("--policy", type=Path, help="Optional JSON policy with drop_keys and pseudonymize_ids")
    args = parser.parse_args()
    if args.command == "compare":
        roots = {}
        for value in args.run:
            if "=" not in value:
                parser.error("--run must use NAME=PATH")
            name, path = value.split("=", 1)
            roots[name] = Path(path)
        result = compare_checkpoints(roots, args.output)
        print(f"Compared {result['shared_case_count']} paired cases; saved {args.output}")
    elif args.command == "dashboard":
        count = build_dashboard(args.reports, args.output)
        print(f"Built local dashboard with {count} cases: {args.output}")
    else:
        if args.command == "audit":
            result = audit_run(args.run, release_scope=args.release_scope)
            print(f"Audited {result['family']} seed {result['seed']}: {args.run / 'privacy_audit.json'}")
        else:
            secret = os.environ.get(args.key_env, "").encode("utf-8")
            if len(secret) < 32:
                parser.error(f"set {args.key_env} to a secret of at least 32 bytes before redacting")
            policy = json.loads(args.policy.read_text(encoding="utf-8")) if args.policy else None
            export_redacted_json(args.source, args.output, key=secret, policy=policy)
            print(f"Wrote redacted copy: {args.output}")


if __name__ == "__main__":
    main()
