"""Small, explicitly scoped adaptations; see docs/REFERENCES.md, not paper replicas."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any


class ContractError(ValueError):
    """An input, lifecycle boundary, or evaluation contract was violated."""


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ContractError(f"{name} must be a finite number")
    return float(value)


def validate_config(c: dict) -> None:
    if c.get("schema_version") != 1 or c.get("mode") not in {"mock", "replay", "real"}:
        raise ContractError("schema_version=1 and mode=mock|replay|real are required")
    for key in ("work_id", "pdk", "environment", "stage", "corner"):
        if not isinstance(c.get(key), str) or not c[key].strip():
            raise ContractError(f"missing {key}")
    if c["objective"].get("direction") not in {"min", "max"}:
        raise ContractError("objective.direction must be min or max")
    metric = c["objective"]["metric"]
    for name, value in c["baseline"].items():
        number(value, name)
    if metric not in c["baseline"]:
        raise ContractError("objective absent from baseline")
    for name, upper in c["upper_bounds"].items():
        number(upper, name)
        if name not in c["baseline"]:
            raise ContractError(f"missing constrained metric {name}")
    if not c["required_checks"] or len(set(c["required_checks"])) != len(c["required_checks"]):
        raise ContractError("required_checks must be non-empty and unique")
    for key in ("episodes_per_session", "steps_per_episode", "steps_per_session", "max_patch_edits", "memory_k", "recent_k"):
        n = c["limits"][key]
        if type(n) is not int or n <= 0:
            raise ContractError(f"positive integer required: limits.{key}")
    alpha = number(c["memory_alpha"], "memory_alpha")
    epsilon = number(c["exploration_epsilon"], "exploration_epsilon")
    if not 0 < alpha <= 1 or not 0 <= epsilon <= 1:
        raise ContractError("invalid alpha/epsilon")
    if number(c["objective"]["min_delta"], "min_delta") < 0:
        raise ContractError("negative tolerance")


def validate_candidates(items: list[dict]) -> list[dict]:
    if not items or len(items) > 16:
        raise ContractError("provide 1..16 candidates")
    ids, signatures = set(), set()
    for c in items:
        if set(c) != {"id", "source", "operation", "parameters", "prior"}:
            raise ContractError("candidate keys: id, source, operation, parameters, prior")
        for field in ("id", "source", "operation"):
            if not isinstance(c[field], str) or not c[field].strip():
                raise ContractError(f"invalid candidate {field}")
        if not isinstance(c["parameters"], dict):
            raise ContractError("parameters must be an object")
        if not 0 <= number(c["prior"], "prior") <= 1:
            raise ContractError("prior outside [0,1]")
        if len(canonical(c).encode()) > 4096:
            raise ContractError("candidate exceeds compact-input budget (4096 bytes)")
        sig = action_key(c)
        if c["id"] in ids or sig in signatures:
            raise ContractError("duplicate candidate ID or semantic operation")
        ids.add(c["id"])
        signatures.add(sig)
    if sum(c["prior"] for c in items) <= 0:
        raise ContractError("at least one positive prior is required")
    canonical(items)
    return items


def action_key(candidate: dict) -> str:
    return digest({"operation": candidate["operation"], "parameters": candidate["parameters"]})


def jit_scores(candidates: list[dict], history: list[dict], state_key: str, episode_number: int) -> list[dict]:
    """Upstream-style probability + normalized advantage, NOT logit correction.

    JitRL 143d221... update_scores: positive-max advantage scale, episode weight.
    Project changes: exact state/action matching; unknown=baseline; no hidden
    memory-action insertion. Exploration is handled separately by the controller.
    """
    validate_candidates(candidates)
    samples = [h for h in history if h["state_key"] == state_key]
    baseline = sum(h["reward"] for h in samples) / len(samples) if samples else 0.0
    means, counts = {}, {}
    for c in candidates:
        values = [h["reward"] for h in samples if h["action_key"] == action_key(c)]
        means[c["id"]] = sum(values) / len(values) if values else baseline
        counts[c["id"]] = len(values)
    adv = {key: value - baseline for key, value in means.items()}
    positive = [a for a in adv.values() if a > 0]
    scale = max(positive) if positive else max((abs(a) for a in adv.values()), default=0)
    weight = min(1.0 + max(0, episode_number) / 100.0, 1.5)
    total = sum(c["prior"] for c in candidates)
    return [{"id": c["id"], "observations": counts[c["id"]], "q": means[c["id"]],
             "score": c["prior"] / total + weight * (adv[c["id"]] / scale if scale else 0)}
            for c in candidates]


def memory_update(old: float, reward: float, alpha: float) -> float:
    """MemRL QValueUpdater gamma=0 numerical update; not causal attribution."""
    return (1 - alpha) * old + alpha * reward


def assess(config: dict, before: dict, result: dict) -> dict:
    """Separate execution, validity, comparable quality and evidence provenance."""
    if result.get("mode") != config["mode"]:
        raise ContractError("mock/replay/real evidence must never cross work boundaries")
    execution = result.get("execution")
    if execution not in {"completed", "blocked", "error", "pending"}:
        raise ContractError("unknown execution status")
    if execution in {"blocked", "error"}:
        return {"decision": "blocked", "reward": None, "reason": "execution not evaluable"}
    if execution == "pending":
        return {"decision": "pending", "reward": None, "reason": "result incomplete"}
    if result.get("stage") != config["stage"] or result.get("corner") != config["corner"]:
        return {"decision": "pending", "reward": None, "reason": "evaluation stage/corner mismatch"}
    checks = result.get("checks", {})
    values = [checks.get(k) for k in config["required_checks"]]
    if any(v not in {"pass", "fail", "not_run"} for v in values) or "not_run" in values:
        return {"decision": "pending", "reward": None, "reason": "required checks missing"}
    if "fail" in values:
        return {"decision": "reject", "reward": -1.0, "reason": "required design check failed"}
    metrics = result.get("metrics", {})
    for name in set(config["upper_bounds"]) | {config["objective"]["metric"]}:
        if name not in metrics:
            return {"decision": "pending", "reward": None, "reason": f"missing metric {name}"}
        number(metrics[name], name)
    if any(metrics[k] > bound for k, bound in config["upper_bounds"].items()):
        return {"decision": "reject", "reward": -1.0, "reason": "hard metric constraint failed"}
    obj = config["objective"]
    old, new = before[obj["metric"]], metrics[obj["metric"]]
    delta = old - new if obj["direction"] == "min" else new - old
    if abs(delta) <= obj["min_delta"]:
        return {"decision": "keep", "reward": 0.0, "reason": "within fixed tolerance"}
    reward = max(-1.0, min(1.0, delta / max(abs(old), 1e-9)))
    return {"decision": "adopt" if delta > 0 else "keep_branch", "reward": reward,
            "reason": "comparable objective improvement" if delta > 0 else "objective regression"}


def apply_edits(bundle: dict[str, str], edits: list[dict], limit: int) -> dict[str, str]:
    """Bounded exact text edits; never edits config, evaluator, tools, or code."""
    if not edits or len(edits) > limit:
        raise ContractError("invalid edit budget")
    out = dict(bundle)
    for edit in edits:
        target = edit["target"]
        if target not in out:
            raise ContractError("target is not a registered text asset")
        op, old, new = edit["op"], edit.get("old", ""), edit.get("new", "")
        if not all(isinstance(s, str) for s in (old, new)):
            raise ContractError("edits must contain text")
        if op == "append" and new.strip():
            out[target] = out[target].rstrip() + "\n\n" + new.strip() + "\n"
        elif op in {"replace", "delete"} and old and out[target].count(old) == 1:
            out[target] = out[target].replace(old, new if op == "replace" else "", 1)
        else:
            raise ContractError("unknown edit, empty content, or non-unique target")
        if not out[target].strip() or len(out[target].encode()) > 16000:
            raise ContractError("empty or oversized text asset")
    return out
