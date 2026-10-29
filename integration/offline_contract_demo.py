"""One scripted episode showing contracts, not model or benchmark performance."""
from dataclasses import asdict
import json
import math

from contracts import (
    ACEPlaybookStore, ActionValueEstimator, CandidateAction, EpisodeContext,
    EpisodeEvent, LocalStrategy, MemoryItem, MemorySelector, PlaybookDelta,
    PlaybookSnapshot, Rule, State, StateActionValue, ToolOutcome,
    ToolOutcomeObserver, Transition, choose_action,
)


class ScriptedMemorySelector:
    def select(self, state, candidates, limit):
        return tuple(item for item in candidates if item.scope == state.task_id)[:limit]


class ScriptedValues:
    def estimate(self, state, candidates, snapshot_id):
        # Hand-written values illustrate the interface; no learning takes place.
        return (
            StateActionValue(state.state_id, "inspect", 0.2, 2),
            StateActionValue(state.state_id, "try_route", 1.2, 3),
        )


class RecordingObserver:
    """An optional hook; does not implement ChipMEM or Bayesian updating."""
    def __init__(self):
        self.events = []

    def observe(self, outcome, transition):
        self.events.append({"tool": outcome.tool_name,
                            "succeeded": outcome.succeeded,
                            "transition_id": transition.transition_id})


class ScriptedCurator:
    def propose(self, snapshot, event):
        # Fixed demonstration text, not a real ACE reflection or LLM result.
        return PlaybookDelta(upserts=(Rule(
            "rule-002", "Record the starting state and observed outcome together.",
            scope="toy-task", evidence_ids=(event.event_id,),
        ),))


class ScriptedEvolver:
    def propose(self, context, event):
        # Local strategy changes do not mutate the global playbook.
        return (LocalStrategy("strategy-child", "Compare alternatives before choosing."),)


def main():
    store = ACEPlaybookStore(PlaybookSnapshot(1, (
        Rule("rule-001", "Use observed feedback as evidence.", scope="toy-task"),
    )))
    context = EpisodeContext(
        "episode-001", "toy-task", LocalStrategy("strategy-parent", "Inspect before acting."),
        store.snapshot(), "scripted-values-v1",
    )
    original_id = context.playbook.snapshot_id
    state = State("state-0", "toy-task", "A scripted decision point; no environment is running.")
    memories = (
        MemoryItem("memory-used", "A scripted relevant record.", "toy-task"),
        MemoryItem("memory-not-injected", "Retrieved but excluded by the context budget.", "toy-task"),
    )
    memory_selector: MemorySelector = ScriptedMemorySelector()
    retrieved = memory_selector.select(state, memories, limit=2)
    injected = retrieved[:1]  # A toy context budget: retrieval != actual injection.
    candidates = (
        CandidateAction("inspect", "inspect the current state", math.log(0.7)),
        CandidateAction("try_route", "try a scripted alternative route", math.log(0.3)),
    )
    estimator: ActionValueEstimator = ScriptedValues()
    values = estimator.estimate(state, candidates, context.value_snapshot_id)
    decision = choose_action(
        state, candidates, values, baseline_value=0.5, beta=1.5,
        injected_memory_ids=tuple(item.memory_id for item in injected), context=context,
    )
    transition = Transition(
        "transition-001", context.episode_id, 0, state, decision,
        reward=0.25,  # Scripted number, not a measured agent performance result.
        next_state=State("state-1", "toy-task", "The scripted demonstration is complete."),
        terminal=True,
    )
    observer: ToolOutcomeObserver = RecordingObserver()
    observer.observe(ToolOutcome("scripted-tool", succeeded=True), transition)
    event = EpisodeEvent(
        "event-001", context.episode_id, "episode_completed", (transition.transition_id,),
        "Scripted feedback only; no LLM, tool backend, or game was invoked.",
    )
    children = ScriptedEvolver().propose(context, event)
    # The orchestrator routes the global write solely through its ACE curator.
    delta = ScriptedCurator().propose(context.playbook, event)
    next_snapshot = store.commit(delta, expected_version=context.playbook.version)

    assert context.playbook.snapshot_id == original_id
    assert len(context.playbook.rules) == 1 and len(next_snapshot.rules) == 2
    assert decision.injected_memory_ids == ("memory-used",)
    assert decision.selected_action.action_id == "try_route"
    print(json.dumps({
        "mode": "offline_contract_demo",
        "model_calls": 0,
        "upstream_frameworks_executed": [],
        "inputs_are_scripted": True,
        "episode_context": asdict(context),
        "episode_event": asdict(event),
        "episode_snapshot_still_frozen": context.playbook.snapshot_id,
        "next_episode_snapshot": next_snapshot.snapshot_id,
        "retrieved_memory_ids": [m.memory_id for m in retrieved],
        "actually_injected_memory_ids": list(decision.injected_memory_ids),
        "decision": asdict(decision),
        "transition": asdict(transition),
        "local_candidate_strategies": [asdict(item) for item in children],
        "global_rule_count_before": len(context.playbook.rules),
        "global_rule_count_after": len(next_snapshot.rules),
        "observer_events": observer.events,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
