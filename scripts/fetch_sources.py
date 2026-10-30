"""Default: print plan. --fetch explicitly downloads pinned research sources."""
from __future__ import annotations
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="+")
    parser.add_argument("--destination", default=str(ROOT / "upstream"))
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    repos = json.loads((ROOT / "repos.lock.json").read_text(encoding="utf-8"))["repositories"]
    names = {r["name"] for r in repos}
    if args.only and set(args.only) - names:
        parser.error("unknown repository name")
    for repo in repos:
        if args.only and repo["name"] not in args.only:
            continue
        path = Path(args.destination).expanduser().resolve() / repo["name"]
        commands = [["git", "clone", "--no-checkout", repo["url"], str(path)],
                    ["git", "-C", str(path), "checkout", "--detach", repo["commit"]]]
        print(json.dumps({"name": repo["name"], "commands": commands, "execute": args.fetch}, ensure_ascii=False))
        if args.fetch:
            if path.exists():
                parser.error(f"refusing existing path: {path}")
            path.parent.mkdir(parents=True, exist_ok=True)
            for command in commands:
                subprocess.run(command, check=True, timeout=180)
            actual = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
            if actual != repo["commit"]:
                raise RuntimeError(f"pin verification failed: {repo['name']}")


if __name__ == "__main__":
    main()
