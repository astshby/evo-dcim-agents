"""One-work controller. SQLite is authoritative; Markdown/JSON are derived views.

This is project code, not an import of the seven upstream agent loops.
"""
from __future__ import annotations

import copy
import json
import random
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Callable

from .policies import (ContractError, action_key, apply_edits, assess, canonical,
                       digest, jit_scores, memory_update, validate_config)


def write_text(path: Path, text: str, root: Path) -> None:
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise ContractError("output path escapes work or is a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    if temp.is_symlink():
        raise ContractError("temporary output is a symlink")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


class Work:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        if not (self.root / "state.sqlite3").is_file():
            raise ContractError("work does not exist; run init first")

    @classmethod
    def create(cls, root: str | Path, config: dict, bundle: dict[str, str]) -> "Work":
        validate_config(config)
        if "ace" not in bundle or "executor" not in bundle:
            raise ContractError("seed bundle requires ace and executor")
        if any(not isinstance(v, str) or not v.strip() for v in bundle.values()):
            raise ContractError("empty seed text")
        if any(not k.replace("-", "").isalnum() for k in bundle):
            raise ContractError("invalid bundle key")
        root = Path(root).resolve()
        if root.exists() and any(root.iterdir()):
            raise ContractError("refusing to overwrite a non-empty work")
        root.mkdir(parents=True, exist_ok=True)
        (root / "work.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        initial = {"config": config, "config_hash": digest(config), "release": 0, "bundle": bundle,
                   "sessions": {}, "active": None, "head": "D0000", "action_history": [],
                   "memories": [], "tool_stats": {}, "publications": [],
                   "checkpoints": {"D0000": {"metrics": config["baseline"], "mode": config["mode"],
                                                "kind": "declared_baseline", "verified": False}}}
        with closing(sqlite3.connect(root / "state.sqlite3")) as db:
            db.execute("CREATE TABLE state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
            db.execute("INSERT INTO state VALUES (1,?)", (canonical(initial),))
            db.commit()
        work = cls(root)
        work.export()
        return work

    def read(self) -> dict:
        with closing(sqlite3.connect(self.root / "state.sqlite3")) as db:
            return json.loads(db.execute("SELECT payload FROM state WHERE id=1").fetchone()[0])

    def _guard(self, state: dict) -> None:
        actual = json.loads((self.root / "work.json").read_text(encoding="utf-8"))
        if digest(actual) != state["config_hash"]:
            raise ContractError("work configuration changed; create another work")
        for key, text in state["bundle"].items():
            path = self.root / ("mem/ACE.md" if key == "ace" else f"skills/{key}/SKILL.md")
            if path.is_symlink() or not path.is_file() or path.read_text(encoding="utf-8") != text:
                raise ContractError("published knowledge changed outside session publication; repair views from DB")

    @contextmanager
    def _transaction(self):
        db = sqlite3.connect(self.root / "state.sqlite3", timeout=10)
        try:
            db.execute("BEGIN IMMEDIATE")
            state = json.loads(db.execute("SELECT payload FROM state WHERE id=1").fetchone()[0])
            self._guard(state)
            yield state
            db.execute("UPDATE state SET payload=? WHERE id=1", (canonical(state),))
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()
        self.export()

    @staticmethod
    def _session(s: dict, sid: str) -> dict:
        if sid not in s["sessions"]:
            raise ContractError("unknown session")
        return s["sessions"][sid]

    @staticmethod
    def _episode(s: dict, sid: str, eid: str) -> dict:
        session = Work._session(s, sid)
        if eid not in session["episodes"]:
            raise ContractError("unknown episode")
        return session["episodes"][eid]

    def start_session(self, checkpoint: str | None = None) -> str:
        with self._transaction() as s:
            if s["active"]:
                raise ContractError("one active session per work")
            start = checkpoint or s["head"]
            if start not in s["checkpoints"]:
                raise ContractError("unknown checkpoint")
            sid = f"S{len(s['sessions']) + 1:04d}"
            s["sessions"][sid] = {"id": sid, "status": "active", "start": start, "head": start,
                                  "release": s["release"], "bundle_hash": digest(s["bundle"]),
                                  "steps": 0, "episodes": {}}
            s["active"] = sid
        return sid

    def start_episode(self, sid: str, intent: str, state_key: str) -> str:
        if not intent.strip() or not state_key.strip() or len(intent) > 1200 or len(state_key) > 200:
            raise ContractError("bounded non-empty intent and state_key required")
        with self._transaction() as s:
            session = self._session(s, sid)
            if s["active"] != sid:
                raise ContractError("session is not active")
            if any(e["state"] not in {"SETTLED", "BLOCKED", "PENDING"} for e in session["episodes"].values()):
                raise ContractError("finish or suspend the current episode first")
            limits = s["config"]["limits"]
            if len(session["episodes"]) >= limits["episodes_per_session"]:
                raise ContractError("session episode budget exhausted")
            eid = f"E{len(session['episodes']) + 1:04d}"
            memories = [m for m in s["memories"] if m["state_key"] == state_key]
            # Deliberately exact-state retrieval bootstrap, not upstream embeddings.
            memories.sort(key=lambda m: (-m["utility"], m["id"]))
            chosen = copy.deepcopy(memories[:limits["memory_k"]])
            recent = [self.card(e) for e in session["episodes"].values()][-limits["recent_k"]:]
            context = {"intent": intent, "state_key": state_key, "start": session["head"],
                       "current_design": s["checkpoints"][session["head"]], "memory": chosen,
                       "recent": recent, "release": s["release"], "mode": s["config"]["mode"]}
            session["episodes"][eid] = {"id": eid, "intent": intent, "state_key": state_key,
                "state": "READY", "start": session["head"], "release": s["release"],
                "context": context, "injected_ids": [m["id"] for m in chosen],
                "steps": [], "events": [{"type": "READY"}], "outcome": None}
        return eid

    def plan(self, sid: str, eid: str, candidates: list[dict]) -> dict:
        with self._transaction() as s:
            e = self._episode(s, sid, eid)
            if s["active"] != sid or e["state"] != "READY":
                raise ContractError("planning requires active READY episode")
            scores = jit_scores(candidates, s["action_history"], e["state_key"], int(eid[1:]))
            unknown = [r for r in scores if not r["observations"]]
            rng = random.Random(s["config"]["seed"] + len(s["sessions"]) * 1000 + int(eid[1:]))
            exploratory = bool(unknown) and rng.random() < s["config"]["exploration_epsilon"]
            winner = rng.choice(unknown) if exploratory else max(scores, key=lambda r: r["score"])
            e["selected"] = copy.deepcopy(next(c for c in candidates if c["id"] == winner["id"]))
            e["candidates"], e["ranking"] = copy.deepcopy(candidates), scores
            e["selection_mode"] = "unknown-exploration" if exploratory else "upstream-additive-subset"
            e["state"] = "PLANNED"
            e["events"].append({"type": "PLANNED", "selected": winner["id"]})
            selected = copy.deepcopy(e["selected"])
        return selected

    def begin_step(self, sid: str, eid: str, tool: str) -> str:
        with self._transaction() as s:
            e, session = self._episode(s, sid, eid), self._session(s, sid)
            if s["active"] != sid or e["state"] not in {"PLANNED", "REPAIR"}:
                raise ContractError("step requires a planned operation")
            limits = s["config"]["limits"]
            if len(e["steps"]) >= limits["steps_per_episode"] or session["steps"] >= limits["steps_per_session"]:
                raise ContractError("step budget exhausted")
            step = f"T{len(e['steps']) + 1:04d}"
            e["steps"].append({"id": step, "tool": tool, "status": "running"})
            session["steps"] += 1
            e["state"] = "EXECUTING"
            e["events"].append({"type": "STEP_STARTED", "step": step, "tool": tool})
        return step

    def complete_step(self, sid: str, eid: str, step: str, success: bool, evidence: str) -> None:
        if type(success) is not bool:
            raise ContractError("success must be boolean")
        with self._transaction() as s:
            e = self._episode(s, sid, eid)
            matches = [x for x in e["steps"] if x["id"] == step]
            if not matches:
                raise ContractError("unknown step")
            record = matches[0]
            final = {"success": success, "evidence": evidence}
            if record["status"] != "running":
                if record["result"] == final:
                    return
                raise ContractError("conflicting duplicate step completion")
            if s["active"] != sid or e["state"] != "EXECUTING":
                raise ContractError("step not currently executable")
            record.update(status="completed", result=final)
            stats = s["tool_stats"].setdefault(record["tool"], {"success": 0, "failure": 0})
            stats["success" if success else "failure"] += 1
            e["state"] = "CHECKING"
            e["events"].append({"type": "STEP_COMPLETED", "step": step, **final})

    def request_repair(self, sid: str, eid: str) -> None:
        with self._transaction() as s:
            e = self._episode(s, sid, eid)
            if s["active"] != sid or e["state"] != "CHECKING":
                raise ContractError("repair only after tool completion")
            e["state"] = "REPAIR"
            e["events"].append({"type": "REPAIR", "action_unchanged": True})

    def settle(self, sid: str, eid: str, result: dict) -> dict:
        with self._transaction() as s:
            if s["config"]["mode"] != "mock":
                raise ContractError("real/replay ingestion requires a future independent evaluator adapter")
            e = self._episode(s, sid, eid)
            result_hash = digest(result)
            if e.get("settled_hash"):
                if e["settled_hash"] != result_hash:
                    raise ContractError("conflicting settlement; never reward twice")
                return copy.deepcopy(e["outcome"])
            if e["state"] not in {"CHECKING", "PENDING"}:
                raise ContractError("settlement requires CHECKING or PENDING")
            if result.get("input_checkpoint") != e["start"]:
                raise ContractError("result does not belong to this starting design")
            outcome = assess(s["config"], s["checkpoints"][e["start"]]["metrics"], result)
            e["evaluation"] = copy.deepcopy(result)
            e["outcome"] = outcome
            if outcome["decision"] == "pending":
                e["state"] = "PENDING"
            else:
                e["state"] = "BLOCKED" if outcome["decision"] == "blocked" else "SETTLED"
                e["settled_hash"] = result_hash
                reward = outcome["reward"]
                if reward is not None and e["release"] == s["release"]:
                    s["action_history"].append({"state_key": e["state_key"], "action_key": action_key(e["selected"]),
                        "reward": reward, "episode": f"{sid}/{eid}", "release": e["release"], "mode": "mock"})
                    for m in s["memories"]:
                        if m["id"] in e["injected_ids"]:
                            m["utility"] = memory_update(m["utility"], reward, s["config"]["memory_alpha"])
                            m["uses"] += 1
                    s["memories"].append({"id": f"{sid}/{eid}", "state_key": e["state_key"],
                        "summary": f"{e['selected']['operation']}: {outcome['reason']}",
                        "utility": 0.0, "uses": 0, "mode": "mock", "decision": outcome["decision"]})
                # Late results may inform statistics, but never silently move another session's head.
                if outcome["decision"] == "adopt":
                    checkpoint = f"D{len(s['checkpoints']):04d}"
                    s["checkpoints"][checkpoint] = {"metrics": result["metrics"], "mode": "mock",
                        "kind": "synthetic", "verified": False, "parent": e["start"], "episode": f"{sid}/{eid}"}
                    e["end"] = checkpoint
                    session = self._session(s, sid)
                    if s["active"] == sid and session["head"] == e["start"]:
                        session["head"] = checkpoint
                        s["head"] = checkpoint
                    else:
                        outcome["decision"] = "keep_branch"
                        outcome["reason"] += "; late/conflicting result retained as branch"
            e["events"].append({"type": e["state"], "decision": outcome["decision"], "result_hash": result_hash})
            returned = copy.deepcopy(outcome)
        return returned

    def close_session(self, sid: str) -> dict:
        with self._transaction() as s:
            session = self._session(s, sid)
            if session["status"] == "closed":
                return copy.deepcopy(session["summary"])
            if s["active"] != sid or not session["episodes"]:
                raise ContractError("no active non-empty session")
            if any(e["state"] not in {"SETTLED", "BLOCKED", "PENDING"} for e in session["episodes"].values()):
                raise ContractError("unfinished episode; do not erase a live job")
            summary = {"session": sid, "start": session["start"], "end": session["head"],
                       "strategy": {"release": session["release"], "bundle_hash": session["bundle_hash"]},
                       "actions_and_effects": [self.card(e) for e in session["episodes"].values()],
                       "mode": s["config"]["mode"], "is_real_ppa_evidence": False}
            session.update(status="closed", summary=summary)
            s["active"] = None
        return summary

    def preview_update(self, sid: str, edits: list[dict]) -> dict:
        s = self.read()
        self._guard(s)
        if s["active"] or self._session(s, sid)["status"] != "closed":
            raise ContractError("ACE/Skill changes require a completed session and no active session")
        bundle = apply_edits(s["bundle"], edits, s["config"]["limits"]["max_patch_edits"])
        return {"session": sid, "base_release": s["release"], "base_hash": digest(s["bundle"]),
                "edits": edits, "candidate_hash": digest(bundle)}

    def publish_mock(self, proposal: dict, gate: dict) -> int:
        """Gate contract test only. A model-produced gate is never real validation."""
        with self._transaction() as s:
            if s["config"]["mode"] != "mock" or gate.get("mode") != "mock":
                raise ContractError("real promotion is intentionally not implemented")
            if s["active"] or self._session(s, proposal["session"])["status"] != "closed":
                raise ContractError("publication is forbidden inside an active session")
            if proposal["base_release"] != s["release"] or proposal["base_hash"] != digest(s["bundle"]):
                raise ContractError("stale proposal")
            bundle = apply_edits(s["bundle"], proposal["edits"], s["config"]["limits"]["max_patch_edits"])
            if proposal["candidate_hash"] != digest(bundle) or gate.get("candidate_hash") != digest(bundle):
                raise ContractError("gate not bound to candidate")
            if (gate.get("base_hash") != proposal["base_hash"] or gate.get("no_regression") is not True
                    or gate.get("passed") is not True or not gate.get("evidence_ref")):
                raise ContractError("gate failed or missing bound evidence")
            s["publications"].append({"proposal": proposal, "gate": gate, "previous_bundle": s["bundle"]})
            s["bundle"] = bundle
            s["release"] += 1
            # Keep raw evidence; revalidate utility under the new text policy instead of inheriting certainty.
            for memory in s["memories"]:
                memory["utility"] = 0.0
                memory["uses"] = 0
            s["action_history"] = []
            revision = s["release"]
        return revision

    @staticmethod
    def card(e: dict) -> dict:
        return {"episode": e["id"], "state": e["state"], "intent": e["intent"],
                "start": e["start"], "end": e.get("end"),
                "action": e.get("selected"), "outcome": e["outcome"], "evidence": "evaluation.json"}

    def export(self) -> None:
        """Rebuild disposable views from the committed DB. Never executes a job."""
        s = self.read()
        def put(path: str, value):
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
            write_text(self.root / path, text, self.root)
        for key, text in s["bundle"].items():
            put("mem/ACE.md" if key == "ace" else f"skills/{key}/SKILL.md", text)
        put("mem/index.json", s["memories"])
        put("mem/statistics.json", {"actions": s["action_history"], "tools": s["tool_stats"]})
        put("status.json", {"active": s["active"], "head": s["head"], "release": s["release"], "mode": s["config"]["mode"]})
        for cid, checkpoint in s["checkpoints"].items():
            put(f"dcim/artifacts/{cid}/manifest.json", checkpoint)
        for sid, session in s["sessions"].items():
            prefix = f"sessions/{sid}"
            put(f"{prefix}/manifest.json", {k: v for k, v in session.items() if k not in {"episodes", "summary"}})
            for eid, e in session["episodes"].items():
                ep = f"{prefix}/{eid}"
                put(f"{ep}/card.json", self.card(e))
                put(f"{ep}/context.json", e["context"])
                put(f"{ep}/events.jsonl", "".join(canonical(event) + "\n" for event in e["events"]))
                for field in ("candidates", "ranking", "evaluation", "outcome"):
                    if field in e:
                        put(f"{ep}/{field}.json", e[field])
            if "summary" in session:
                put(f"{prefix}/summary.json", session["summary"])
                put(f"{prefix}/report.md", "# Session comparison (" + s["config"]["mode"] + ")\n\n"
                    + "Not real EDA/PPA evidence.\n\n```json\n"
                    + json.dumps(session["summary"], ensure_ascii=False, indent=2) + "\n```\n")
