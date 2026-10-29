#!/usr/bin/env python3
"""Check an EvoTest checkout without importing its agents or reading credentials."""

from __future__ import annotations

import argparse
import ast
import importlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys


AUDITED_COMMIT = "f92474ce83c7aec69e45c30ccfaf2b69e66823de"
DEPENDENCIES = {
    "numpy": "numpy",
    "openai": "openai",
    "tiktoken": "tiktoken",
    "dotenv": "python-dotenv",
    "jericho": "jericho",
    "sklearn": "scikit-learn",
}
REQUIRED_FILES = (
    "main.py", "requirements_rag.txt", "src/evaluation.py", "src/env.py",
    "src/our_agent.py", "src/openai_helpers.py", "src/cross_episode_memory.py",
    "src/utils.py", "src/memory_agent.py", "src/summary_agent.py",
    "src/rag_agent.py", "src/naive_agent.py",
)


def check(label: str, ok: bool, detail: str, *, warning: bool = False) -> dict:
    return {"check": label, "status": "ok" if ok else ("warning" if warning else "error"),
            "detail": detail}


def rom_filename(repo: Path, game: str) -> str:
    """Read the literal ROM mapping; never execute upstream utils.py."""
    tree = ast.parse((repo / "src/utils.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "rom_dict"
            for target in node.targets
        ):
            mapping = ast.literal_eval(node.value)
            name = mapping.get(game)
            if isinstance(name, str) and Path(name).name == name:
                return name
    raise ValueError("Game is absent from the literal upstream ROM mapping")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True, help="Local EvoTest checkout")
    parser.add_argument("--game", default="detective")
    parser.add_argument("--rom-dir", type=Path, help="Default: <repo>/jericho-games")
    parser.add_argument("--check-imports", action="store_true",
                        help="Also import dependency packages, never upstream agent modules")
    parser.add_argument("--json", action="store_true", help="Machine-readable report")
    args = parser.parse_args()
    repo = args.repo.expanduser().resolve()
    results = [check("python", sys.version_info >= (3, 10),
                     f"Python {sys.version_info.major}.{sys.version_info.minor}; require >=3.10")]
    results.append(check("repo", repo.is_dir(), str(repo)))

    for relative in REQUIRED_FILES:
        path = repo / relative
        if not path.is_file():
            results.append(check(f"file:{relative}", False, "Missing"))
            continue
        try:
            if path.suffix == ".py":
                ast.parse(path.read_text(encoding="utf-8"), filename=relative)
            detail = "Present; Python syntax checked" if path.suffix == ".py" else "Present"
            results.append(check(f"file:{relative}", True, detail))
        except (OSError, UnicodeError, SyntaxError) as exc:
            results.append(check(f"file:{relative}", False, type(exc).__name__))

    for module, distribution in DEPENDENCIES.items():
        try:
            installed = importlib.util.find_spec(module) is not None
            detail = "Not installed"
            if installed:
                try:
                    detail = importlib.metadata.version(distribution)
                except importlib.metadata.PackageNotFoundError:
                    detail = "Importable module; distribution version unavailable"
                if args.check_imports:
                    importlib.import_module(module)
                    detail += "; import succeeded"
            results.append(check(f"dependency:{distribution}", installed, detail))
        except Exception as exc:
            results.append(check(f"dependency:{distribution}", False,
                                 f"Import check failed: {type(exc).__name__}"))

    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", args.game):
            raise ValueError("Invalid game name")
        name = rom_filename(repo, args.game)
        rom_dir = args.rom_dir.expanduser().resolve() if args.rom_dir else repo / "jericho-games"
        rom = rom_dir / name
        with rom.open("rb") as stream:
            header = stream.read(64)
        valid_header = len(header) == 64 and 1 <= header[0] <= 8
        results.append(check("rom", valid_header,
                             f"{rom}; header checked only, not an environment rollout"))
    except (OSError, UnicodeError, ValueError, SyntaxError) as exc:
        results.append(check("rom", False, f"Missing/unrecognized ROM for {args.game}: {type(exc).__name__}"))

    try:
        proc = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=5, check=False)
        commit = proc.stdout.strip() if proc.returncode == 0 else "unavailable"
        results.append(check("upstream_commit", commit == AUDITED_COMMIT,
                             f"HEAD={commit}; audited={AUDITED_COMMIT}", warning=True))
    except (OSError, subprocess.TimeoutExpired) as exc:
        results.append(check("upstream_commit", False, type(exc).__name__, warning=True))

    ready = all(item["status"] != "error" for item in results)
    report = {
        "ready_for_manual_api_run": ready,
        "api_calls_made": False,
        "credentials_read": False,
        "upstream_modules_imported": False,
        "checks": results,
        "limits": [
            "No API credential or model-availability check.",
            "No token-encoding download, game episode, or framework integration was run.",
            "A ROM header check does not establish compatibility with the installed Jericho version.",
        ],
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for item in results:
            print(f"[{item['status'].upper()}] {item['check']}: {item['detail']}")
        print("No credentials read; no API calls; upstream agent modules were not imported.")
        print("Result: preflight passed" if ready else "Result: preflight blocked; see ERROR entries")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
