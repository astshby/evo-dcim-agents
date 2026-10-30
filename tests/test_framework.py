from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evo_dcim.__main__ import load, seeds
from evo_dcim.adapters import REPO, UnavailableEDA, prepare_codex, run_codex, run_mock
from evo_dcim.core import Work
from evo_dcim.policies import ContractError, action_key, apply_edits, assess, jit_scores, memory_update


def candidate(scenario="improve", prior=1.0):
    return {"id": scenario, "source": "test", "operation": "synthetic_test", "parameters": {"scenario": scenario}, "prior": prior}


class FrameworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = load(str(REPO / "configs/work.mock.json"))
        self.root = Path(self.temp.name) / "work"
        self.work = Work.create(self.root, self.config, seeds())

    def episode(self, scenario="improve", sid=None):
        sid = sid or self.work.start_session()
        eid = self.work.start_episode(sid, "test operation", "floorplan/congested")
        self.work.plan(sid, eid, [candidate(scenario)])
        return sid, eid

    def completed(self, scenario="improve"):
        sid, eid = self.episode(scenario)
        result = run_mock(self.work, sid, eid)
        return sid, eid, result

    def test_demo_improvement_is_synthetic(self):
        sid, eid, result = self.completed()
        self.assertEqual(result["decision"], "adopt")
        s = self.work.read()
        self.assertEqual(s["checkpoints"][s["head"]]["metrics"]["area"], 95.0)
        self.assertFalse(s["checkpoints"][s["head"]]["verified"])
        self.assertEqual(s["memories"][0]["utility"], 0)
        self.assertEqual(s["release"], 0)

    def test_blocked_does_not_punish_action_or_memory(self):
        self.completed("blocked")
        s = self.work.read()
        self.assertEqual(s["action_history"], [])
        self.assertEqual(s["memories"], [])
        self.assertEqual(s["tool_stats"]["MockEDA"]["failure"], 1)

    def test_invalid_not_adopted(self):
        _, _, result = self.completed("invalid")
        self.assertEqual(result["reward"], -1)
        self.assertEqual(self.work.read()["head"], "D0000")

    def test_regression_retained_not_adopted(self):
        _, _, result = self.completed("regress")
        self.assertEqual(result["decision"], "keep_branch")
        self.assertEqual(self.work.read()["head"], "D0000")

    def test_neutral_reward(self):
        _, _, result = self.completed("neutral")
        self.assertEqual(result["reward"], 0)

    def test_idempotent_settlement(self):
        sid, eid, _ = self.completed()
        s = self.work.read()
        evaluation = s["sessions"][sid]["episodes"][eid]["evaluation"]
        self.work.settle(sid, eid, evaluation)
        self.assertEqual(self.work.read(), s)
        evaluation["metrics"]["area"] = 90
        with self.assertRaises(ContractError):
            self.work.settle(sid, eid, evaluation)

    def test_memory_injection_is_not_same_episode_credit(self):
        sid, _, _ = self.completed()
        eid = self.work.start_episode(sid, "next", "floorplan/congested")
        self.work.plan(sid, eid, [candidate()])
        run_mock(self.work, sid, eid)
        memories = self.work.read()["memories"]
        self.assertEqual(memories[0]["uses"], 1)
        self.assertGreater(memories[0]["utility"], 0)
        self.assertEqual(memories[1]["uses"], 0)

    def test_pending_not_automatically_failed(self):
        sid, eid, outcome = self.completed("pending")
        self.assertIsNone(outcome["reward"])
        self.assertEqual(self.work.read()["action_history"], [])
        self.work.close_session(sid)
        next_sid = self.work.start_session()
        s = self.work.read()
        result = copy.deepcopy(s["sessions"][sid]["episodes"][eid]["evaluation"])
        result["execution"] = "completed"
        result["metrics"]["area"] = 90
        result = self.work.settle(sid, eid, result)
        self.assertEqual(result["decision"], "keep_branch")
        self.assertEqual(self.work.read()["sessions"][next_sid]["head"], "D0000")

    def test_session_text_freeze(self):
        sid, _ = self.episode()
        with self.assertRaises(ContractError):
            self.work.preview_update(sid, [{"target": "ace", "op": "append", "new": "test"}])
        (self.root / "mem/ACE.md").write_text("tampered", encoding="utf-8")
        with self.assertRaises(ContractError):
            self.work.start_episode(sid, "new", "state")
        self.work.export()
        self.assertNotEqual((self.root / "mem/ACE.md").read_text(), "tampered")

    def test_work_configuration_is_fixed(self):
        path = self.root / "work.json"
        c = json.loads(path.read_text())
        c["pdk"] = "another-pdk"
        path.write_text(json.dumps(c))
        with self.assertRaises(ContractError):
            self.work.start_session()

    def test_one_session_and_one_live_episode(self):
        sid, _ = self.episode()
        with self.assertRaises(ContractError):
            self.work.start_session()
        with self.assertRaises(ContractError):
            self.work.start_episode(sid, "second", "state")
        with self.assertRaises(ContractError):
            self.work.close_session(sid)

    def test_duplicate_and_invalid_candidate_rejected(self):
        sid = self.work.start_session()
        eid = self.work.start_episode(sid, "test", "s")
        with self.assertRaises(ContractError):
            self.work.plan(sid, eid, [candidate(), candidate()])
        c = candidate()
        c["prior"] = float("nan")
        with self.assertRaises(ContractError):
            self.work.plan(sid, eid, [c])

    def test_step_budget_and_duplicate_completion(self):
        sid, eid = self.episode()
        for i in range(self.config["limits"]["steps_per_episode"]):
            step = self.work.begin_step(sid, eid, "fake")
            self.work.complete_step(sid, eid, step, False, "test")
            self.work.complete_step(sid, eid, step, False, "test")
            self.work.request_repair(sid, eid)
        with self.assertRaises(ContractError):
            self.work.begin_step(sid, eid, "fake")
        self.assertEqual(self.work.read()["tool_stats"]["fake"]["failure"], 4)

    def test_mock_promotion_is_session_bound_and_hash_bound(self):
        sid, _, _ = self.completed()
        self.work.close_session(sid)
        edits = [{"target": "ace", "op": "append", "new": "Synthetic test only."}]
        proposal = self.work.preview_update(sid, edits)
        gate = {"mode": "mock", "candidate_hash": proposal["candidate_hash"], "base_hash": proposal["base_hash"],
                "passed": True, "no_regression": True, "evidence_ref": "unit-test-fixture"}
        bad = dict(gate, candidate_hash="wrong")
        with self.assertRaises(ContractError):
            self.work.publish_mock(proposal, bad)
        self.assertEqual(self.work.publish_mock(proposal, gate), 1)
        with self.assertRaises(ContractError):
            self.work.publish_mock(proposal, gate)
        self.assertEqual(len(self.work.read()["publications"]), 1)

    def test_failed_gate_rejected(self):
        sid, _, _ = self.completed()
        self.work.close_session(sid)
        p = self.work.preview_update(sid, [{"target": "ace", "op": "append", "new": "test"}])
        with self.assertRaises(ContractError):
            self.work.publish_mock(p, {"mode": "mock", "passed": False})

    def test_real_execution_and_promotion_fail_closed(self):
        self.assertFalse(UnavailableEDA().capabilities()["available"])
        with self.assertRaises(ContractError):
            UnavailableEDA().execute()
        c = copy.deepcopy(self.config)
        c["mode"] = "real"
        other = Work.create(Path(self.temp.name) / "real", c, seeds())
        sid = other.start_session()
        eid = other.start_episode(sid, "test", "s")
        other.plan(sid, eid, [candidate()])
        with self.assertRaises(ContractError):
            run_mock(other, sid, eid)
        with self.assertRaises(ContractError):
            other.settle(sid, eid, {"mode": "real"})

    def test_runtime_and_development_instructions_separate(self):
        sid, eid = self.episode()
        dest = Path(self.temp.name) / "runtime"
        argv = prepare_codex(self.work, sid, eid, dest)
        self.assertIn("--output-schema", argv)
        self.assertIn("--sandbox", argv)
        self.assertFalse((dest / "AGENTS.override.md").exists())
        self.assertFalse((dest / ".agents/skills/maintain-framework").exists())
        self.assertIn("Released runtime", (dest / "AGENTS.md").read_text())
        with self.assertRaises(ContractError):
            prepare_codex(self.work, sid, eid, dest)
        with self.assertRaises(ContractError):
            prepare_codex(self.work, sid, eid, self.root / "runtime")
        with self.assertRaises(ContractError):
            prepare_codex(self.work, sid, eid, REPO / "work/runtime")
        with self.assertRaises(ContractError):
            run_codex(dest, 10, False)

    def test_codex_missing_is_explicit_not_faked(self):
        sid, eid = self.episode()
        dest = Path(self.temp.name) / "runtime"
        prepare_codex(self.work, sid, eid, dest)
        with patch("evo_dcim.adapters.shutil.which", return_value=None):
            with self.assertRaises(ContractError):
                run_codex(dest, 10, True)

    def test_conflicting_runtime_parent_rejected(self):
        sid, eid = self.episode()
        parent = Path(self.temp.name) / "parent"
        parent.mkdir()
        (parent / "AGENTS.override.md").write_text("dev")
        with self.assertRaises(ContractError):
            prepare_codex(self.work, sid, eid, parent / "runtime")

    def test_work_survives_process_reconstruction(self):
        sid, _, _ = self.completed()
        other = Work(self.root)
        other.close_session(sid)
        other.export()
        self.assertEqual(other.read()["head"], "D0001")
        self.assertTrue((self.root / f"sessions/{sid}/report.md").exists())

    @unittest.skipUnless(os.name == "posix", "fake executable fixture uses a POSIX shebang")
    def test_codex_runner_with_fake_executable_not_real_model(self):
        sid, eid = self.episode()
        dest = Path(self.temp.name) / "runtime"
        prepare_codex(self.work, sid, eid, dest)
        fake = Path(self.temp.name) / "fake-codex"
        fake.write_text("#!" + sys.executable + "\nimport json\n"
                        "print(json.dumps({'type':'thread.started','thread_id':'fixture-only'}))\n"
                        "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':7}}))\n")
        fake.chmod(0o700)
        manifest_path = dest / "runner.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["argv"] = ["this-must-never-be-executed"]
        manifest_path.write_text(json.dumps(manifest))
        with patch("evo_dcim.adapters.shutil.which", return_value=str(fake)):
            result = run_codex(dest, 10, True)
        self.assertEqual(result["thread_ids"], ["fixture-only"])
        self.assertEqual(result["usage"], [{"input_tokens": 7}])
        self.assertFalse(result["independently_verified"])
        self.assertEqual(self.work.read()["sessions"][sid]["episodes"][eid]["state"], "PLANNED")
        with self.assertRaises(ContractError):
            run_codex(dest, 10, True)

    def test_late_old_policy_result_does_not_repopulate_current_statistics(self):
        sid, eid, _ = self.completed("pending")
        self.work.close_session(sid)
        p = self.work.preview_update(sid, [{"target": "ace", "op": "append", "new": "new mock rule"}])
        self.work.publish_mock(p, {"mode": "mock", "candidate_hash": p["candidate_hash"],
            "base_hash": p["base_hash"], "passed": True, "no_regression": True, "evidence_ref": "fixture"})
        result = copy.deepcopy(self.work.read()["sessions"][sid]["episodes"][eid]["evaluation"])
        result["execution"] = "completed"
        result["metrics"]["area"] = 90
        self.work.settle(sid, eid, result)
        self.assertEqual(self.work.read()["action_history"], [])
        self.assertEqual(self.work.read()["memories"], [])

    def test_reject_nonempty_work(self):
        with self.assertRaises(ContractError):
            Work.create(self.root, self.config, seeds())


class PolicyTests(unittest.TestCase):
    def test_upstream_additive_subset(self):
        a, b = candidate("improve", 0.7), candidate("regress", 0.3)
        history = [{"state_key": "s", "action_key": action_key(a), "reward": 0.2},
                   {"state_key": "s", "action_key": action_key(b), "reward": 0.8}]
        values = jit_scores([a, b], history, "s", 50)
        self.assertAlmostEqual(values[0]["score"], -0.8)
        self.assertAlmostEqual(values[1]["score"], 1.8)
        self.assertTrue(all(x["observations"] == 0 for x in jit_scores([a, b], history, "other", 1)))

    def test_memory_single_step_update(self):
        self.assertAlmostEqual(memory_update(0.2, 1.0, 0.1), 0.28)

    def test_bounded_edits(self):
        bundle = {"ace": "a\nb\n", "executor": "hello"}
        self.assertEqual(apply_edits(bundle, [{"target": "ace", "op": "replace", "old": "a", "new": "c"}], 1)["ace"], "c\nb\n")
        with self.assertRaises(ContractError):
            apply_edits(bundle, [{"target": "config", "op": "append", "new": "x"}], 1)
        with self.assertRaises(ContractError):
            apply_edits(bundle, [{"target": "ace", "op": "replace", "old": "absent", "new": "x"}], 1)
        with self.assertRaises(ContractError):
            apply_edits(bundle, [], 1)

    def test_evaluation_provenance_and_missing_checks(self):
        config = load(str(REPO / "configs/work.mock.json"))
        result = {"mode": "real", "execution": "completed"}
        with self.assertRaises(ContractError):
            assess(config, config["baseline"], result)
        result.update(mode="mock", stage=config["stage"], corner=config["corner"])
        self.assertEqual(assess(config, config["baseline"], result)["decision"], "pending")
        result["checks"] = {k: "pass" for k in config["required_checks"]}
        result["metrics"] = {"area": float("nan"), "delay": 10, "power": 20}
        with self.assertRaises(ContractError):
            assess(config, config["baseline"], result)


if __name__ == "__main__":
    unittest.main()
