"""Observed account transfers and checked model evidence for a transaction.

Account paths describe records; a structural pattern is never treated as a
fraud label. History ends at the model's completed-batch prediction boundary.
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd


STORY_VERSION = 2


def canonical_frames(adapter: Any) -> dict[str, pd.DataFrame]:
    """Use the model's stable bank-wide IDs, not split-specific CSV node IDs."""
    result = {}
    for split in ("training", "validation"):
        frame = adapter.frames[split].copy()
        stream = adapter.streams[split]
        source = stream.src.detach().cpu().numpy()
        target = stream.dst.detach().cpu().numpy()
        if len(source) != len(frame) or len(target) != len(frame):
            raise ValueError("model event endpoints and frame rows do not align")
        identities = pd.DataFrame({
            "local": pd.concat([frame["src_node"], frame["dst_node"]], ignore_index=True),
            "canonical": list(source) + list(target),
        }).drop_duplicates()
        if identities["local"].duplicated().any():
            raise ValueError("split-specific account IDs do not align with model event IDs")
        frame["src_node"] = source
        frame["dst_node"] = target
        result[split] = frame
    return result


def completed_history(training: pd.DataFrame, validation: pd.DataFrame,
                      index: int, batch_size: int) -> pd.DataFrame:
    if batch_size < 1 or index < 0 or index >= len(validation):
        raise ValueError("invalid prediction boundary")
    stop = index // batch_size * batch_size
    columns = [name for name in validation.columns if name != "y"]
    history = pd.concat([training.reindex(columns=columns), validation.iloc[:stop][columns]],
                        ignore_index=True)
    target_time = pd.Timestamp(validation.iloc[index]["timestamp"])
    times = pd.to_datetime(history["timestamp"], errors="coerce")
    # A strict time bound also rejects malformed training rows from the future.
    history = history.loc[times < target_time].copy()
    history["timestamp"] = times.loc[history.index]
    return history.sort_values("timestamp", kind="stable")


def _event(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    amount = row.get("amount")
    return {
        "transaction_id": str(row.get("txn_id", row.get("transaction_id", ""))),
        "source": int(row.get("src_node", row.get("source"))),
        "target": int(row.get("dst_node", row.get("target"))),
        "timestamp": str(row["timestamp"]),
        "amount": float(amount) if amount is not None and pd.notna(amount) else None,
        "currency": str(row.get("currency", "")),
        "payment_method": str(row.get("payment_format", "")),
    }


def _checked_effects(report: dict[str, Any], history_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if "graph_explanation" in report:
        graph = report["graph_explanation"] or {}
        fidelity = graph.get("fidelity") or {}
        original = float(fidelity.get("original_probability", float("nan")))
        replay_error = float(fidelity.get("unperturbed_replay_error", float("inf")))
        score = float(report["prediction"]["probability"])
        if (not math.isfinite(original) or not math.isfinite(replay_error)
                or abs(original - score) > 1e-6 or replay_error > 1e-6):
            return {}
        effects = {}
        for edge in graph.get("important_edges", []):
            txn_id = str(edge.get("transaction_id", ""))
            event = history_by_id.get(txn_id)
            without = float(edge.get("probability_without", float("nan")))
            if (event is None or not math.isfinite(without) or not 0 <= without <= 1
                    or int(edge["source"]) != event["source"] or int(edge["target"]) != event["target"]
                    or pd.Timestamp(edge["timestamp"]) != pd.Timestamp(event["timestamp"])):
                continue
            effects[txn_id] = {"original_model_score": score, "model_score_without_event": without,
                               "score_support": score - without, "verified_model_count": 1,
                               "scope": "one historical update suppressed in the selected global model's bounded replay; pre-window account memory retained"}
        return effects
    members = report.get("per_member_graph_evidence", [])
    member_probabilities = report.get("ensemble", {}).get("member_probabilities", [])
    if len(members) != 3 or len(member_probabilities) != 3:
        return {}
    if [int(member["seed"]) for member in members] != [42, 52, 62]:
        return {}
    edge_maps = []
    for member, expected in zip(members, member_probabilities):
        graph = member.get("graph_explanation") or {}
        fidelity = graph.get("fidelity") or {}
        original = float(fidelity.get("original_probability", float("nan")))
        replay_error = float(fidelity.get("unperturbed_replay_error", float("inf")))
        if (not math.isfinite(original) or not math.isfinite(replay_error)
                or abs(original - float(expected)) > 1e-6 or replay_error > 1e-6):
            return {}
        edge_maps.append({str(edge["transaction_id"]): edge for edge in graph.get("important_edges", [])
                          if "transaction_id" in edge})
    shared = set.intersection(*(set(mapping) for mapping in edge_maps))
    effects = {}
    score = float(report["prediction"]["probability"])
    for txn_id in shared & history_by_id.keys():
        event = history_by_id[txn_id]
        edges = [mapping[txn_id] for mapping in edge_maps]
        if any(int(edge["source"]) != event["source"] or int(edge["target"]) != event["target"]
               or pd.Timestamp(edge["timestamp"]) != pd.Timestamp(event["timestamp"]) for edge in edges):
            continue
        without = [float(edge.get("probability_without", float("nan"))) for edge in edges]
        if not all(math.isfinite(value) and 0 <= value <= 1 for value in without):
            continue
        removed_score = sum(without) / 3
        effects[txn_id] = {
            "original_ensemble_score": score,
            "ensemble_score_without_event": removed_score,
            "score_support": score - removed_score,
            "member_scores_without_event": without,
            "verified_members": [int(member["seed"]) for member in members],
            "scope": "same historical update suppressed separately in each member's bounded replay; account memory before the window is retained",
        }
    return effects


def build_transaction_story(row: pd.Series, history: pd.DataFrame,
                            report: dict[str, Any], max_edges: int = 9,
                            account_ids: dict[int, str] | None = None) -> dict[str, Any]:
    selected = _event(row)
    source, target = selected["source"], selected["target"]
    def account_label(node):
        if account_ids is not None and node not in account_ids:
            raise ValueError("model account node is absent from the dataset account map")
        return str(account_ids[node]) if account_ids is not None else str(node)
    if len(history):
        times = pd.to_datetime(history["timestamp"], errors="coerce")
        history = history.loc[times < pd.Timestamp(selected["timestamp"])].copy()
        history = history.loc[history["txn_id"].astype(str) != selected["transaction_id"]]
        history = history.sort_values("timestamp", kind="stable")
        related = history.loc[history["src_node"].isin([source, target])
                              | history["dst_node"].isin([source, target])].tail(256)
    else:
        related = history
    observed = [_event(record) for _, record in related.iterrows()]
    by_id = {event["transaction_id"]: event for event in observed}
    effects = _checked_effects(report, by_id)
    # Seek a time-ordered return path B->C->A, closed by the selected A->B.
    cycle = []
    for latter in reversed(observed):
        if latter["target"] != source:
            continue
        if latter["source"] == target and source != target:
            cycle = [latter]
            break
        for earlier in reversed(observed):
            if (earlier["source"] == target and earlier["target"] == latter["source"]
                    and latter["source"] not in (source, target)
                    and pd.Timestamp(earlier["timestamp"]) < pd.Timestamp(latter["timestamp"])):
                cycle = [earlier, latter]
                break
        if cycle:
            break
    priority = cycle + [by_id[key] for key in sorted(effects, key=lambda key: abs(effects[key]["score_support"]), reverse=True)]
    priority += list(reversed(observed))
    visible, seen = [], set()
    nodes = {source, target}
    for event in priority:
        if event["transaction_id"] in seen or len(visible) >= max_edges - 1:
            continue
        if len(nodes | {event["source"], event["target"]}) > 8:
            continue
        seen.add(event["transaction_id"])
        nodes.update([event["source"], event["target"]])
        visible.append(dict(event, kind="earlier", ensemble_effect=effects.get(event["transaction_id"])))
    visible.sort(key=lambda event: pd.Timestamp(event["timestamp"]))
    aliases = {source: "A"}
    if target != source:
        aliases[target] = "B"
    for event in visible:
        for node in (event["source"], event["target"]):
            if node not in aliases:
                aliases[node] = chr(ord("A") + len(aliases))
    for event in visible + [selected]:
        event["source_alias"] = aliases[event["source"]]
        event["target_alias"] = aliases[event["target"]]
        event["source_account_id"] = account_label(event["source"])
        event["target_account_id"] = account_label(event["target"])
    selected["kind"] = "selected"
    if source == target:
        observation = f"Transaction {selected['transaction_id']} uses the same sender and receiver account ID, {account_label(source)}. Earlier related records are shown when available."
        pattern = "same_account_record"
    elif cycle:
        path = [account_label(cycle[0]["source"])] + [account_label(event["target"]) for event in cycle] + [account_label(target)]
        observation = "Earlier transfers and the selected transfer form the time-ordered account path " + " → ".join(path) + "."
        observation += " Transaction IDs in that order: " + " → ".join([event["transaction_id"] for event in cycle] + [selected["transaction_id"]]) + "."
        pattern = "observed_return_path"
    elif observed:
        prior_recipients = {event["target"] for event in observed if event["source"] == source}
        if len(prior_recipients | {target}) > 1:
            observation = f"Account {account_label(source)} also sent money to other accounts before transaction {selected['transaction_id']}. The map labels each transfer with its transaction ID."
            pattern = "multiple_recipients"
        else:
            observation = "The map shows earlier transfers involving the sender or receiver, followed by the selected transfer."
            pattern = "connected_history"
    else:
        observation = f"No earlier transfers involving these account IDs were available before this prediction. Transaction {selected['transaction_id']} goes from account {account_label(source)} to account {account_label(target)}."
        pattern = "single_transfer"
    feature_groups: dict[str, dict[str, Any]] = {}
    feature_labels = {"payment_format": "payment method", "amount": "transaction amount",
                      "Amount_Received": "transaction amount", "currency": "currency", "Receiving_Currency": "currency"}
    for feature in report.get("feature_explanation", {}).get("features", []):
        name = feature_labels.get(feature["feature"], feature["feature"].replace("_", " "))
        entry = feature_groups.setdefault(name, {"label": name, "value": feature.get("value"), "contribution": 0.0})
        entry["contribution"] += float(feature.get("shap_logit", 0))
    strongest = max(feature_groups.values(), key=lambda feature: abs(feature["contribution"]), default=None)
    checked_effects = [dict(transaction_id=key, **value) for key, value in effects.items()]
    checked_effects.sort(key=lambda effect: abs(effect["score_support"]), reverse=True)
    return {
        "schema_version": STORY_VERSION,
        "selected_transfer": selected,
        "accounts": [{"alias": alias, "node_id": node, "account_id": account_label(node),
                      "role": "sender and receiver" if source == target else ("sender" if node == source else ("receiver" if node == target else "connected account"))}
                     for node, alias in aliases.items()],
        "transfers": visible + [selected],
        "eligible_earlier_transfers": [dict(event, kind="earlier",
            source_account_id=account_label(event["source"]),
            target_account_id=account_label(event["target"])) for event in observed],
        "observation": observation,
        "pattern": pattern,
        "known_labels_explain_paths": False,
        "path_is_not_a_fraud_classification": True,
        "earlier_related_transfers_considered": len(observed),
        "model_link_effects": checked_effects,
        **({"ensemble_link_effects": checked_effects} if "ensemble" in report else {}),
        "strongest_feature": strongest,
        "history_scope": "training history and completed validation batches before the selected prediction; current-batch and later transactions excluded; up to 256 recent endpoint-related transfers considered",
        "display_limit": max_edges,
    }
