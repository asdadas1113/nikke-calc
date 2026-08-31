from __future__ import annotations

import unittest
from types import SimpleNamespace

from optimizer import CacheIdentity, MorisEvaluator, SearchBudget
from optimizer.reference_pipeline import prepare_external_references
from optimizer.seed_sources import CompositionOrderKnowledge, ExternalCompositionEvidence


def make_evaluator(scores):
    table = {tuple(team): float(score) for team, score in scores.items()}

    def build_squad(names, characters):
        return tuple(names)

    def build_config(squad, config):
        return dict(config)

    def simulate(squad, **kwargs):
        team = tuple(squad)
        if team not in table:
            raise AssertionError(f"unexpected synthetic simulation: {team}")
        return SimpleNamespace(squad_total=table[team])

    return MorisEvaluator(
        build_squad,
        build_config,
        simulate,
        cache_identity=CacheIdentity("engine", "account"),
    )


class ReferencePipelineTests(unittest.TestCase):
    def test_common_setup_yields_seed_hypothesis_and_moris_selected_reference(self):
        row = ExternalCompositionEvidence(
            members=("A", "B"),
            order_knowledge=CompositionOrderKnowledge.UNKNOWN_ORDER,
            source="external:one",
        )
        evaluator = make_evaluator({("A", "B"): 10, ("B", "A"): 100})

        prepared = prepare_external_references(
            evaluator,
            (row,),
            owned_roster=("A", "B"),
            budget=SearchBudget(2),
            max_placements_per_composition=2,
            team_size=2,
        )

        self.assertEqual(prepared.references, (("B", "A"),))
        self.assertEqual(prepared.common_simulate_calls, 2)
        self.assertEqual(len(prepared.hypotheses.seeds.core_seeds), 1)
        self.assertEqual(set(prepared.hypotheses.seeds.core_seeds[0].members), {"A", "B"})

    def test_unowned_evidence_consumes_no_common_moris_calls(self):
        row = ExternalCompositionEvidence(
            members=("A", "X"),
            order_knowledge=CompositionOrderKnowledge.UNKNOWN_ORDER,
            source="external:missing",
        )
        evaluator = make_evaluator({})

        prepared = prepare_external_references(
            evaluator,
            (row,),
            owned_roster=("A", "B"),
            budget=SearchBudget(0),
            max_placements_per_composition=2,
            team_size=2,
        )

        self.assertEqual(prepared.references, ())
        self.assertEqual(prepared.common_simulate_calls, 0)
        self.assertEqual(
            prepared.hypotheses.skipped_before_adaptation[0].reason,
            "unowned-members:X",
        )


if __name__ == "__main__":
    unittest.main()
