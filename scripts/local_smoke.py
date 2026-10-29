#!/usr/bin/env python3
"""Local checks only: no LLM, embedding or paid service calls."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    run = args.output or root / "runs" / ("local-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    run = run.resolve()
    run.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", PYTHON_DOTENV_DISABLED="1")
    checks = []
    def execute(label, command, cwd=root):
        proc = subprocess.run([str(x) for x in command], cwd=cwd, env=env,
                              capture_output=True, text=True, timeout=90)
        (run / (label + ".stdout.txt")).write_text(proc.stdout, encoding="utf-8")
        (run / (label + ".stderr.txt")).write_text(proc.stderr, encoding="utf-8")
        checks.append({"check": label, "passed": proc.returncode == 0, "exit_code": proc.returncode})
        print(f'{"PASS" if proc.returncode == 0 else "FAIL"} {label}', flush=True)
        return proc
    sources = []
    for entry in json.loads((root / "repos.lock.json").read_text())["repositories"]:
        repo = root / "upstream" / entry["name"]
        actual = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        origin = subprocess.check_output(["git", "-C", str(repo), "remote", "get-url", "origin"], text=True).strip()
        dirty = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True).strip()
        matched = actual == entry["commit"] and origin.rstrip("/").removesuffix(".git") == entry["url"].removesuffix(".git")
        sources.append({"name": entry["name"], "commit": actual, "origin_matches": matched, "clean": not dirty})
    checks.append({"check": "seven_source_checkouts", "passed": all(s["origin_matches"] and s["clean"] for s in sources)})
    execute("pip_check", [sys.executable, "-m", "pip", "check"])
    execute("preflight", [sys.executable, root / "scripts/preflight_evotest.py", "--repo",
                         root / "upstream/EvoTest", "--check-imports", "--json"])
    execute("contract_demo", [sys.executable, root / "integration/offline_contract_demo.py"])
    environment_code = """
import importlib.util, json
from pathlib import Path
repo = Path.cwd()
spec = importlib.util.spec_from_file_location("studied_environment", repo / "src/env.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
game = module.JerichoEnv(str(repo / "jericho-games/detective.z5"), seed=0, step_limit=2)
try:
    observation, initial = game.reset()
    after, reward, done, info = game.step("look")
    assert isinstance(observation, str) and observation
    assert isinstance(after, str) and after
    assert isinstance(info["valid"], list) and info["valid"]
    print(json.dumps({"reset": True, "step": True, "action": "look",
                      "valid_actions_available": bool(info["valid"]), "reward": reward,
                      "initial_score": initial.get("score"), "score": info.get("score"),
                      "seed_wiring_verified": False, "llm_calls": 0}))
finally:
    game.close()
"""
    execute("jericho_environment", [sys.executable, "-c", environment_code], root / "upstream/EvoTest")
    execute("evotest_cli", [sys.executable, "main.py", "--help"], root / "upstream/EvoTest")
    chip = root / "upstream/ChipMEM"
    state, output = run / "chipmem-state", run / "chipmem-output"
    common = ["--config", "experiments/config.example.json", "--state-directory", state, "--output-directory", output]
    execute("chipmem_validate", [sys.executable, "main.py", "validate", *common], chip)
    chip_run = execute("chipmem_synthetic", [sys.executable, "main.py", "run", *common], chip)
    summary = {
        "kind": "local_setup_no_model_smoke", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0], "checks": checks, "source_checkouts": sources,
        "model_calls": 0, "embedding_calls": 0, "dotenv_loading_disabled": True,
        "all_passed": all(item["passed"] for item in checks),
        "limits": ["Not an EvoTest+LLM episode.", "No ACE/JitRL/MemRL/GEPA/SkillOpt runtime exercised.",
                   "ChipMEM uses official scripted fixtures, not paper benchmarks.",
                   "Token encoding may download on first CLI import; this is not an air-gap test.",
                   "EvoTest upstream environment seed wiring remains unverified."],
    }
    if chip_run.returncode == 0:
        summary["chipmem_result"] = json.loads(chip_run.stdout)
    (run / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Summary: " + str(run / "summary.json"))
    return 0 if summary["all_passed"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
