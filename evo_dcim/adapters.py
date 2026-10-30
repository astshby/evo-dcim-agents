"""Mock EDA and explicit Codex CLI boundary. Never installs tools or reads auth.json."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Protocol

from .core import Work
from .policies import ContractError, digest

REPO = Path(__file__).resolve().parents[1]


class EDAAdapter(Protocol):
    """Future real adapter must independently validate artifacts, not LLM claims."""
    def capabilities(self) -> dict: ...
    def execute(self, action: dict, checkpoint: dict, workspace: Path) -> dict: ...
    def poll(self, job_id: str) -> dict: ...
    def cancel(self, job_id: str) -> None: ...
    def evaluate(self, job_id: str) -> dict: ...


class AgentRunner(Protocol):
    def prepare(self, context: dict, workspace: Path) -> list[str]: ...
    def run(self, argv: list[str], timeout: int) -> dict: ...


class UnavailableEDA:
    def capabilities(self) -> dict:
        return {"available": False, "reason": "PDK, license and real evaluator not configured"}

    def execute(self, *args, **kwargs):
        raise ContractError("real EDA is not connected; no mock fallback is allowed")


def run_mock(work: Work, sid: str, eid: str) -> dict:
    s = work.read()
    if s["config"]["mode"] != "mock":
        raise ContractError("mock executor cannot be used for real or replay works")
    e = Work._episode(s, sid, eid)
    action = e.get("selected", {})
    if action.get("operation") != "synthetic_test":
        raise ContractError("MockEDA only accepts synthetic_test, never production commands")
    scenario = action["parameters"].get("scenario")
    if scenario not in {"improve", "neutral", "regress", "invalid", "blocked", "pending"}:
        raise ContractError("unknown mock scenario")
    step = work.begin_step(sid, eid, "MockEDA")
    metrics = dict(s["checkpoints"][e["start"]]["metrics"])
    objective = s["config"]["objective"]
    sign = 1 if objective["direction"] == "min" else -1
    if scenario in {"improve", "regress"}:
        metrics[objective["metric"]] *= 1 + (-0.05 if scenario == "improve" else 0.05) * sign
    result = {"mode": "mock", "input_checkpoint": e["start"],
              "execution": scenario if scenario in {"blocked", "pending"} else "completed",
              "stage": s["config"]["stage"], "corner": s["config"]["corner"],
              "checks": {k: "pass" for k in s["config"]["required_checks"]},
              "metrics": metrics, "artifact_kind": "synthetic_not_layout"}
    if scenario == "invalid":
        result["checks"][s["config"]["required_checks"][0]] = "fail"
    work.complete_step(sid, eid, step, scenario != "blocked", "synthetic fixture")
    return work.settle(sid, eid, result)


def prepare_codex(work: Work, sid: str, eid: str, destination: Path) -> list[str]:
    """Materialize a new runtime workspace OUTSIDE this development checkout."""
    s = work.read()
    work._guard(s)
    e = Work._episode(s, sid, eid)
    if s["active"] != sid or e["state"] != "PLANNED":
        raise ContractError("prepare requires an active planned episode")
    destination = destination.expanduser().resolve()
    if destination.is_relative_to(REPO) or REPO.is_relative_to(destination):
        raise ContractError("runtime workspace must not overlap development checkout")
    if destination.is_relative_to(work.root) or work.root.is_relative_to(destination):
        raise ContractError("runtime workspace must not expose the controller's work database")
    if destination.exists():
        raise ContractError("refusing to overwrite runtime workspace")
    # Reject inherited project instruction sources; global Codex settings still need user review.
    for parent in destination.parents:
        if (parent / ".git").exists() or any((parent / name).exists() for name in ("AGENTS.md", "AGENTS.override.md")):
            raise ContractError(f"runtime parent contains project instructions or Git root: {parent}")
    destination.mkdir(parents=True)
    (destination / "AGENTS.md").write_text((REPO / "templates/AGENTS.runtime.md").read_text(encoding="utf-8"), encoding="utf-8")
    for name, text in s["bundle"].items():
        if name == "ace":
            (destination / "ACE.md").write_text(text, encoding="utf-8")
        else:
            folder = destination / ".agents" / "skills" / name
            folder.mkdir(parents=True)
            (folder / "SKILL.md").write_text(text, encoding="utf-8")
    context = {**e["context"], "selected_action": e["selected"], "permissions": "proposal/report only; real EDA not connected"}
    (destination / "context.json").write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    (destination / "design").mkdir()
    (destination / "design" / "README.md").write_text("No physical design copied. Mount only explicitly approved files in a future adapter.\n", encoding="utf-8")
    schema = {"type": "object", "properties": {
        "status": {"type": "string", "enum": ["reported", "blocked"]},
        "action_id": {"type": "string"}, "summary": {"type": "string"},
        "evidence_paths": {"type": "array", "items": {"type": "string"}}},
        "required": ["status", "action_id", "summary", "evidence_paths"], "additionalProperties": False}
    (destination / "report.schema.json").write_text(json.dumps(schema), encoding="utf-8")
    argv = ["codex", "--ask-for-approval", "never", "exec", "--sandbox", "workspace-write",
            "--json", "--skip-git-repo-check", "--cd", str(destination),
            "--output-schema", str(destination / "report.schema.json"),
            "--output-last-message", str(destination / "final.json"),
            "Use $executor. Read context.json and ACE.md. Report only the selected operation. "
            "This bootstrap has no real EDA adapter. Do not claim PPA or checks were measured."]
    manifest = {"schema_version": 1, "kind": "codex_plan_only", "workspace": str(destination),
                "work_id": s["config"]["work_id"], "session": sid, "episode": eid,
                "release": s["release"], "context_hash": digest(context), "argv": argv}
    (destination / "runner.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return argv


def run_codex(workspace: Path, timeout: int, confirmed: bool = False) -> dict:
    """Opt-in one-shot CLI call; does NOT settle an episode or validate PPA.

    Only wall time is enforced here. CLI internal tool count/account quota are
    not hard-limited. Never deserialize an executable command from runner.json.
    """
    if not confirmed:
        raise ContractError("explicit --execute confirmation required; model calls may consume quota")
    if timeout <= 0:
        raise ContractError("timeout must be positive")
    workspace = workspace.expanduser().resolve()
    if workspace.is_relative_to(REPO):
        raise ContractError("never launch runtime Codex in the development checkout")
    manifest = json.loads((workspace / "runner.json").read_text(encoding="utf-8"))
    if manifest.get("kind") != "codex_plan_only" or manifest.get("workspace") != str(workspace):
        raise ContractError("invalid prepared workspace")
    if (workspace / "codex.started.json").exists():
        raise ContractError("already started; inspect prior run instead of submitting twice")
    executable = shutil.which("codex")
    if not executable:
        raise ContractError("Codex CLI is not installed; no automatic installation")
    # Fixed allowlisted command. User authentication stays in the existing CLI profile.
    argv = [executable, "--ask-for-approval", "never", "exec", "--sandbox", "workspace-write",
            "--json", "--skip-git-repo-check", "--cd", str(workspace),
            "--output-schema", str(workspace / "report.schema.json"),
            "--output-last-message", str(workspace / "final.json"),
            "Use $executor. Read context.json and ACE.md. Real EDA is unavailable; report limitations honestly."]
    (workspace / "codex.started.json").write_text(json.dumps({"argv": argv}), encoding="utf-8")
    timed_out = False
    with (workspace / "codex.events.jsonl").open("w", encoding="utf-8") as out, (workspace / "codex.stderr.log").open("w", encoding="utf-8") as err:
        proc = subprocess.Popen(argv, cwd=workspace, stdout=out, stderr=err, start_new_session=(os.name == "posix"))
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGTERM)
            else:
                proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    os.killpg(proc.pid, signal.SIGKILL)
                else:
                    proc.kill()
                proc.wait()
            code = proc.returncode
    events = []
    with (workspace / "codex.events.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    result = {"exit_code": code, "timed_out": timed_out,
              "thread_ids": [e["thread_id"] for e in events if e.get("type") == "thread.started" and "thread_id" in e],
              "usage": [e.get("usage", {}) for e in events if e.get("type") == "turn.completed"],
              "independently_verified": False}
    (workspace / "codex.result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
