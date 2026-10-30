"""Run with python -m evo_dcim. All default paths are offline and zero-model-call."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters import REPO, prepare_codex, run_codex, run_mock
from .core import Work
from .policies import ContractError


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def seeds() -> dict[str, str]:
    result = {"ace": (REPO / "templates/ACE.seed.md").read_text(encoding="utf-8")}
    for name in ("executor", "propose-structure", "propose-routing"):
        result[name] = (REPO / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    return result


def demo(root: str) -> dict:
    work = Work.create(root, load(str(REPO / "configs/work.mock.json")), seeds())
    sid = work.start_session()
    for scenario in ("improve", "blocked", "invalid"):
        eid = work.start_episode(sid, "Evaluate a synthetic design operation", "floorplan/congested")
        work.plan(sid, eid, [{"id": scenario, "source": "fixture", "operation": "synthetic_test",
                            "parameters": {"scenario": scenario}, "prior": 1.0}])
        run_mock(work, sid, eid)
    summary = work.close_session(sid)
    return {"work": str(work.root), "model_calls": 0, "eda_calls": 0,
            "mode": "mock", "summary": summary}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("demo", help="create and run a new synthetic work")
    d.add_argument("--root", required=True)
    init = sub.add_parser("init")
    init.add_argument("--work", required=True)
    init.add_argument("--config", default=str(REPO / "configs/work.mock.json"))
    for cmd in ("status", "repair-views", "session-start", "session-close", "episode-start", "plan", "mock-run", "preview-update", "publish-mock", "codex-prepare"):
        sp = sub.add_parser(cmd)
        sp.add_argument("--work", required=True)
        if cmd in {"session-close", "episode-start", "plan", "mock-run", "preview-update", "codex-prepare"}:
            sp.add_argument("--session", required=True)
        if cmd in {"plan", "mock-run", "codex-prepare"}:
            sp.add_argument("--episode", required=True)
        if cmd == "session-start":
            sp.add_argument("--checkpoint")
        if cmd == "episode-start":
            sp.add_argument("--intent", required=True)
            sp.add_argument("--state-key", required=True)
        if cmd == "plan":
            sp.add_argument("--candidates", required=True)
        if cmd == "preview-update":
            sp.add_argument("--edits", required=True)
        if cmd == "publish-mock":
            sp.add_argument("--proposal", required=True)
            sp.add_argument("--gate", required=True)
            sp.add_argument("--confirm-synthetic", action="store_true")
        if cmd == "codex-prepare":
            sp.add_argument("--destination", required=True)
    cp = sub.add_parser("codex-run")
    cp.add_argument("--workspace", required=True)
    cp.add_argument("--timeout", type=int, default=300)
    cp.add_argument("--execute", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    try:
        cmd = args.command
        if cmd == "demo":
            result = demo(args.root)
        elif cmd == "init":
            result = {"work": str(Work.create(args.work, load(args.config), seeds()).root)}
        elif cmd == "codex-run":
            result = run_codex(Path(args.workspace), args.timeout, args.execute)
        else:
            work = Work(args.work)
            if cmd == "status":
                s = work.read()
                work._guard(s)
                result = {k: s[k] for k in ("active", "head", "release")}
            elif cmd == "repair-views":
                work.export()
                result = {"restored_from_db": True, "jobs_resubmitted": 0}
            elif cmd == "session-start":
                result = {"session": work.start_session(args.checkpoint)}
            elif cmd == "session-close":
                result = work.close_session(args.session)
            elif cmd == "episode-start":
                result = {"episode": work.start_episode(args.session, args.intent, args.state_key)}
            elif cmd == "plan":
                result = work.plan(args.session, args.episode, load(args.candidates))
            elif cmd == "mock-run":
                result = run_mock(work, args.session, args.episode)
            elif cmd == "preview-update":
                result = work.preview_update(args.session, load(args.edits))
            elif cmd == "publish-mock":
                if not args.confirm_synthetic:
                    raise ContractError("--confirm-synthetic required; never real promotion")
                result = {"release": work.publish_mock(load(args.proposal), load(args.gate))}
            else:
                result = {"executed": False, "argv": prepare_codex(work, args.session, args.episode, Path(args.destination))}
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ContractError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
