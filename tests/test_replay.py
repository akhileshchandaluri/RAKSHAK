"""Replay engine: deterministic frames, decision records, and the story's headline contrasts."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from replay import PRESETS, build_replay  # noqa: E402
from simulation import ScenarioRequest  # noqa: E402

_cache = {}


def replay(name):
    if name not in _cache:
        _cache[name] = build_replay(ScenarioRequest.model_validate(PRESETS[name]))
    return _cache[name]


class ReplayTests(unittest.TestCase):
    def test_frames_are_regular_and_state_codes_valid(self):
        r = replay("aufls")
        times = [f["t"] for f in r["frames"]]
        self.assertTrue(all(abs((b - a) - r["frame_dt"]) < 0.06 for a, b in zip(times, times[1:])))
        n = len(r["buildings"])
        for f in r["frames"]:
            for i, code in f["c"]:
                self.assertTrue(0 <= i < n)
                self.assertIn(code, (0, 1, 2, 3))
            self.assertEqual(len(f["k"]), len(r["campus_ids"]))

    def test_deterministic(self):
        a = build_replay(ScenarioRequest.model_validate(PRESETS["npmrd"]))
        self.assertEqual(a["frames"], replay("npmrd")["frames"])
        self.assertEqual(a["decisions"], replay("npmrd")["decisions"])

    def test_story_contrasts(self):
        aufls, npmrd = replay("aufls"), replay("npmrd")
        self.assertLessEqual(aufls["nadir"], 49.4 + 1e-3)      # AUFLS stage 1 is reached
        self.assertGreater(npmrd["nadir"], 49.4)
        self.assertTrue(npmrd["decisions"], "the predictive policy must record its reasoning")
        d = npmrd["decisions"][0]
        self.assertIn("t", d)

    def test_prearming_survives_bad_comms(self):
        central, hybrid = replay("npmrd_comms"), replay("hybrid_comms")
        self.assertGreater(hybrid["nadir"], 49.4)
        self.assertGreaterEqual(hybrid["nadir"], central["nadir"])


if __name__ == "__main__":
    unittest.main()
