from __future__ import annotations

import unittest

from fast_engine.engine.targets import TargetMode, compile_target


class TargetGrammarSafetyTests(unittest.TestCase):
    def test_burst3_requires_exact_owned_grammar(self):
        actor_by_name = {"리타": 0}

        exact = compile_target("allies_burst3", actor_by_name=actor_by_name)
        persona = compile_target(
            "allies_burst3_persona_excl_self", actor_by_name=actor_by_name
        )
        unknown = compile_target(
            "allies_burst3_future_suffix", actor_by_name=actor_by_name
        )
        numeric_suffix = compile_target("allies_burst30", actor_by_name=actor_by_name)

        self.assertEqual(exact.mode, TargetMode.BURST3)
        for spec in (persona, unknown, numeric_suffix):
            self.assertEqual(spec.mode, TargetMode.UNSUPPORTED)
            self.assertFalse(spec.runtime_supported)


if __name__ == "__main__":
    unittest.main()
