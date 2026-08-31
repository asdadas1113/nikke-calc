from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer.evaluator import CacheIdentity, MorisEvaluator


class EvaluatorRawRetentionTests(unittest.TestCase):
    def make_evaluator(self, *, retain_raw: bool = False, use_cache: bool = True):
        calls = []

        def build_squad(names, characters):
            return tuple(names)

        def build_config(squad, config):
            return dict(config)

        def simulate(squad, *, config, enemy, seed, verbose):
            result = SimpleNamespace(squad_total=123.5, marker=object())
            calls.append(result)
            return result

        evaluator = MorisEvaluator(
            build_squad,
            build_config,
            simulate,
            cache_identity=(
                CacheIdentity("engine", "account") if use_cache else None
            ),
            use_cache=use_cache,
            retain_raw=retain_raw,
        )
        return evaluator, calls

    def test_default_drops_raw_for_fresh_and_cached_evaluations(self):
        evaluator, calls = self.make_evaluator()

        first = evaluator.evaluate(("A", "B"))
        second = evaluator.evaluate(("A", "B"))

        self.assertFalse(evaluator.retain_raw)
        self.assertIsNone(first.raw)
        self.assertIsNone(second.raw)
        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(first.score, 123.5)
        self.assertEqual(second.score, 123.5)
        self.assertEqual(len(calls), 1)
        self.assertEqual(evaluator.stats.simulate_calls, 1)
        self.assertEqual(evaluator.stats.cache_hits, 1)

    def test_retain_raw_opt_in_preserves_previous_behavior(self):
        evaluator, calls = self.make_evaluator(retain_raw=True)

        first = evaluator.evaluate(("A", "B"))
        second = evaluator.evaluate(("A", "B"))

        self.assertTrue(evaluator.retain_raw)
        self.assertIs(first.raw, calls[0])
        self.assertIs(second.raw, calls[0])
        self.assertTrue(second.cache_hit)
        self.assertEqual(len(calls), 1)

    def test_no_cache_still_obeys_raw_policy(self):
        score_only, score_calls = self.make_evaluator(use_cache=False)
        diagnostic, diagnostic_calls = self.make_evaluator(
            use_cache=False,
            retain_raw=True,
        )

        score_result = score_only.evaluate(("A", "B"))
        diagnostic_result = diagnostic.evaluate(("A", "B"))

        self.assertIsNone(score_result.raw)
        self.assertIs(diagnostic_result.raw, diagnostic_calls[0])
        self.assertEqual(len(score_calls), 1)
        self.assertEqual(len(diagnostic_calls), 1)
        self.assertEqual(score_only.cache_size, 0)
        self.assertEqual(diagnostic.cache_size, 0)


if __name__ == "__main__":
    unittest.main()
