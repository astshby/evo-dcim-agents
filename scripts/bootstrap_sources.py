#!/usr/bin/env python3
"""Clone audited upstream commits. Existing checkouts are never changed."""
import argparse
import json
import pathlib
import subprocess
import sys


def run(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, text=True, check=True, capture_output=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parents[1] / 'repos.lock.json')
    parser.add_argument('--dest', type=pathlib.Path, default=pathlib.Path('upstream'))
    parser.add_argument('--only', nargs='+', default=['EvoTest', 'ACE', 'JitRL'])
    parser.add_argument('--plan', action='store_true', help='Print the intended checkouts without network or writes.')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    repos = {r['name']: r for r in manifest['repositories']}
    unknown = set(args.only) - set(repos)
    if unknown:
        parser.error('Unknown repositories: ' + ', '.join(sorted(unknown)))
    for name in args.only:
        repo = repos[name]
        dest = args.dest.resolve() / name
        if args.plan:
            print(json.dumps({'name': name, 'url': repo['url'], 'commit': repo['commit'], 'destination': str(dest)}, ensure_ascii=False))
            continue
        if dest.exists():
            try:
                origin = run('git', 'remote', 'get-url', 'origin', cwd=dest).stdout.strip()
                head = run('git', 'rev-parse', 'HEAD', cwd=dest).stdout.strip()
            except subprocess.CalledProcessError:
                raise RuntimeError(f'{dest} exists but is not a readable Git checkout; nothing was changed.')
            if origin.removesuffix('.git').rstrip('/') != repo['url'].removesuffix('.git').rstrip('/') or head != repo['commit']:
                raise RuntimeError(f'{dest} already exists with a different origin/commit; inspect it manually. Nothing was changed.')
            print(f'KEEP {name}: already at {head}; local edits are preserved.')
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f'CLONE {name} at {repo["commit"]}', flush=True)
        run('git', 'clone', '--no-checkout', repo['url'], str(dest))
        run('git', 'checkout', '--detach', repo['commit'], cwd=dest)
        print(f'READY {dest}')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, OSError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            print(exc.stderr.strip(), file=sys.stderr)
        raise SystemExit(1)
