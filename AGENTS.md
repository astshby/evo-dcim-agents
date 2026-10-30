# Public development instructions

This repository develops a DCIM agent controller. You are maintaining framework code,
not running an authorized physical-design experiment. Start with `docs/HANDOFF.md`,
`docs/UPDATE_POLICY.md`, and `docs/IMPLEMENTATION_STATUS.md`.

## Non-negotiable boundaries

- One work = one fixed PDK/environment/objective configuration. Session memories belong to that work.
- Episode memory is a compact state-transition card with evidence references, not a full chat replay.
- Session interior: facts and numeric statistics may change. ACE and Skill text may change only after session close.
- Separate tool success, physical validity, PPA benefit and transferable knowledge. Unknown is not failure.
- Use upstream pinned implementations as references. Record deviations; do not claim full paper reproduction.
- Mock/replay evidence never becomes real PPA evidence or source-verified production knowledge.
- No automatic paid calls, dependency installation, real EDA, secrets inspection or remote jobs in tests.
- Do not copy proprietary PDK, cell libraries, credentials, auth.json or license files into Git or model input.
- Never replace independent evaluation with an agent's own success claim.
- Avoid new frameworks or heavyweight dependencies unless the next acceptance target requires them.

## Validation and handoff

Run `python -m unittest discover -s tests -v` and a new-path `python -m evo_dcim demo --root ...`.
Update implementation status and development log with what actually ran and what did not.
Do not describe scaffolding, fake executables or synthetic metrics as real integration.

Runtime instructions are `templates/AGENTS.runtime.md`; only that template is copied to
runtime workspaces. Do not copy developer instructions or this checkout to runtime.
A local `AGENTS.override.md` is ignored by Git; if used, explicitly read this file too,
because Codex chooses the override instead of same-directory AGENTS.md.
