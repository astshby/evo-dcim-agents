#!/usr/bin/env bash
# Short upstream baseline only: this script does not implement ACE or JitRL.
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: run_evotest_baseline.sh [--dry-run] /absolute/path/to/EvoTest

Required environment:
  EVOTEST_ACTOR_MODEL     Actor model ID available from your provider
  EVOTEST_EVOLVER_MODEL   Evolver model ID available from your provider

Optional environment:
  EVOTEST_PYTHON          Python executable (default: python)
  EVOTEST_GAME            Game name (default: detective)
  EVOTEST_ROM_DIR         ROM directory (default: <repo>/jericho-games)
  EVOTEST_OUTPUT_PARENT   Parent for a fresh run directory (default: <repo>/output)

Real run: preflight, then 2 episodes with at most 20 steps each.
--dry-run prints the command only: no API calls, imports, or run directories.
Credentials are handled by the upstream client; this script never reads .env.
USAGE
}

evotest_dry_run=0
evotest_repo_arg=""
while (($#)); do
  case "$1" in
    --dry-run) evotest_dry_run=1 ;;
    --help|-h) usage; exit 0 ;;
    --*) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    *)
      if [[ -n "$evotest_repo_arg" ]]; then
        printf 'Provide exactly one EvoTest checkout path.\n' >&2
        exit 2
      fi
      evotest_repo_arg="$1"
      ;;
  esac
  shift
done
if [[ -z "$evotest_repo_arg" ]]; then
  usage >&2
  exit 2
fi
: "${EVOTEST_ACTOR_MODEL:?Set EVOTEST_ACTOR_MODEL explicitly}"
: "${EVOTEST_EVOLVER_MODEL:?Set EVOTEST_EVOLVER_MODEL explicitly}"
evotest_repo="$(cd -- "$evotest_repo_arg" && pwd -P)"
evotest_scripts="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
evotest_python="${EVOTEST_PYTHON:-python}"
evotest_game="${EVOTEST_GAME:-detective}"
evotest_rom_dir="${EVOTEST_ROM_DIR:-$evotest_repo/jericho-games}"
evotest_output_parent="${EVOTEST_OUTPUT_PARENT:-$evotest_repo/output}"
if [[ "$evotest_rom_dir" != /* ]]; then
  evotest_rom_dir="$PWD/$evotest_rom_dir"
fi
if [[ "$evotest_output_parent" != /* ]]; then
  evotest_output_parent="$PWD/$evotest_output_parent"
fi
if [[ "$evotest_python" == */* && "$evotest_python" != /* ]]; then
  evotest_python="$PWD/$evotest_python"
fi

if [[ "$evotest_dry_run" == 1 ]]; then
  evotest_run_dir="$evotest_output_parent/baseline.DRY_RUN"
else
  "$evotest_python" "$evotest_scripts/preflight_evotest.py" \
    --repo "$evotest_repo" --game "$evotest_game" --rom-dir "$evotest_rom_dir" --check-imports
  mkdir -p -- "$evotest_output_parent"
  evotest_run_dir="$(mktemp -d "$evotest_output_parent/baseline.XXXXXXXX")"
fi

evotest_command=(
  "$evotest_python" "$evotest_repo/main.py"
  --game_name "$evotest_game"
  --rom_path "$evotest_rom_dir"
  --agent_type our
  --llm_model "$EVOTEST_ACTOR_MODEL"
  --evolution_llm_model "$EVOTEST_EVOLVER_MODEL"
  --eval_runs 2
  --env_step_limit 20
  --output_path "$evotest_run_dir"
  --enable_cross_mem
)
printf 'Working directory: %s\n' "$evotest_repo"
printf 'Command: '
printf '%q ' "${evotest_command[@]}"
printf '\n'
if [[ "$evotest_dry_run" == 1 ]]; then
  printf 'Dry run only; readiness and credentials were not checked.\n'
  exit 0
fi
cd -- "$evotest_repo"
exec "${evotest_command[@]}"
