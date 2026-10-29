"""Teaching contracts only; no upstream agent, LLM, environment, or learning is run.

ACE owns global playbook commits. EvoTest owns local strategy proposals. Each
episode captures immutable snapshots; real adapters must enforce this ownership.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import Protocol, Sequence


@dataclass(frozen=True)
class Rule:
    rule_id: str
    text: str
    scope: str = "global"
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlaybookSnapshot:
    version: int
    rules: tuple[Rule, ...]

    @property
    def snapshot_id(self) -> str:
        encoded = json.dumps(asdict(self), sort_keys=True, ensure_ascii=False).encode()
        return f"ace-v{self.version}-{hashlib.sha256(encoded).hexdigest()[:12]}"


@dataclass(frozen=True)
class PlaybookDelta:
    upserts: tuple[Rule, ...] = ()
    delete_ids: tuple[str, ...] = ()


class ACEPlaybookStore:
    """Single-writer contract, not an authentication or security boundary.

    The orchestrator permits only its ACE curator adapter to call commit().
    Production storage must add persistence, transactions and access control.
    """
    def __init__(self, initial: PlaybookSnapshot):
        if len({r.rule_id for r in initial.rules}) != len(initial.rules):
            raise ValueError("initial rule IDs must be unique")
        self._snapshot = initial

    def snapshot(self) -> PlaybookSnapshot:
        return self._snapshot

    def commit(self, delta: PlaybookDelta, *, expected_version: int) -> PlaybookSnapshot:
        if expected_version != self._snapshot.version:
            raise ValueError("stale playbook version: re-read before committing")
        ids = [r.rule_id for r in delta.upserts]
        if len(set(ids)) != len(ids) or set(ids).intersection(delta.delete_ids):
            raise ValueError("delta contains duplicate or conflicting rule IDs")
        rules = {r.rule_id: r for r in self._snapshot.rules}
        for rule_id in delta.delete_ids:
            rules.pop(rule_id, None)
        rules.update({r.rule_id: r for r in delta.upserts})
        self._snapshot = PlaybookSnapshot(
            self._snapshot.version + 1, tuple(rules[k] for k in sorted(rules))
        )
        return self._snapshot


@dataclass(frozen=True)
class LocalStrategy:
    config_id: str
    instructions: str
    temperature: float = 0.4


@dataclass(frozen=True)
class EpisodeContext:
    episode_id: str
    task_id: str
    strategy: LocalStrategy
    playbook: PlaybookSnapshot
    value_snapshot_id: str


@dataclass(frozen=True)
class State:
    state_id: str
    task_id: str
    observation: str


@dataclass(frozen=True)
class CandidateAction:
    action_id: str
    command: str
    prior_logit: float  # A logit/log-probability, NOT a probability or a percentage.


@dataclass(frozen=True)
class StateActionValue:
    state_id: str
    action_id: str
    q_value: float
    evidence_count: int


@dataclass(frozen=True)
class MemoryItem:
    memory_id: str
    content: str
    scope: str
    utility: float | None = None  # Reserved for memory utility, not action Q.


@dataclass(frozen=True)
class ScoredAction:
    action: CandidateAction
    advantage: float
    corrected_logit: float
    probability: float


@dataclass(frozen=True)
class ActionDecision:
    selected_action: CandidateAction
    scored_actions: tuple[ScoredAction, ...]
    injected_memory_ids: tuple[str, ...]  # Actual prompt contents, not retrieval hits.
    playbook_snapshot_id: str
    value_snapshot_id: str


@dataclass(frozen=True)
class Transition:
    transition_id: str
    episode_id: str
    step: int
    state: State
    decision: ActionDecision
    reward: float
    next_state: State
    terminal: bool


@dataclass(frozen=True)
class EpisodeEvent:
    event_id: str
    episode_id: str
    event_type: str
    transition_ids: tuple[str, ...]
    feedback: str


@dataclass(frozen=True)
class ToolOutcome:
    tool_name: str
    succeeded: bool
    error_type: str | None = None


class MemorySelector(Protocol):
    def select(self, state: State, candidates: Sequence[MemoryItem],
               limit: int) -> tuple[MemoryItem, ...]: ...


class ToolOutcomeObserver(Protocol):
    def observe(self, outcome: ToolOutcome, transition: Transition) -> None: ...


class ActionValueEstimator(Protocol):
    def estimate(self, state: State, candidates: Sequence[CandidateAction],
                 snapshot_id: str) -> tuple[StateActionValue, ...]: ...


class ACECurator(Protocol):
    def propose(self, snapshot: PlaybookSnapshot,
                event: EpisodeEvent) -> PlaybookDelta: ...


class EvoTestEvolver(Protocol):
    def propose(self, context: EpisodeContext,
                event: EpisodeEvent) -> tuple[LocalStrategy, ...]: ...


def choose_action(
    state: State, candidates: Sequence[CandidateAction],
    values: Sequence[StateActionValue], *, baseline_value: float, beta: float,
    injected_memory_ids: tuple[str, ...], context: EpisodeContext,
) -> ActionDecision:
    """Paper-style score demonstration: z' = z + beta * (Q - V).

    Missing evidence receives zero advantage. Softmax is shown for inspection;
    selection is deterministic argmax. No unseen-action exploration or real
    JitRL retrieval/credit assignment is implemented here.
    """
    if not candidates or len({a.action_id for a in candidates}) != len(candidates):
        raise ValueError("candidate actions must be nonempty with unique IDs")
    if state.task_id != context.task_id:
        raise ValueError("state and episode belong to different tasks")
    q = {v.action_id: v.q_value for v in values if v.state_id == state.state_id}
    advantages = [q.get(a.action_id, baseline_value) - baseline_value for a in candidates]
    logits = [a.prior_logit + beta * adv for a, adv in zip(candidates, advantages)]
    if not all(math.isfinite(x) for x in [baseline_value, beta, *logits]):
        raise ValueError("scores must be finite")
    if beta < 0:
        raise ValueError("beta must be nonnegative")
    weights = [math.exp(z - max(logits)) for z in logits]
    denominator = sum(weights)
    scored = tuple(
        ScoredAction(a, adv, z, w / denominator)
        for a, adv, z, w in zip(candidates, advantages, logits, weights)
    )
    selected = max(scored, key=lambda item: item.corrected_logit).action
    return ActionDecision(selected, scored, tuple(injected_memory_ids),
                          context.playbook.snapshot_id, context.value_snapshot_id)
