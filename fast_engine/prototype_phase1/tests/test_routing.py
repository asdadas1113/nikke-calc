from __future__ import annotations

from pathlib import Path
import os
import sys
import unittest

PROJ = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
ROOT = Path(os.environ.get('MORIS_ROOT', str(REPO_ROOT)))
sys.path.insert(0, str(PROJ))

from fast_engine.catalog import FastCatalog
from fast_engine.routing import FastSupportProfile, route_team


class RoutingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = FastCatalog.from_moris(ROOT)
        cls.by_name = cls.catalog.by_name
        cls.full = FastSupportProfile.structural_full_generic(cls.catalog.characters)

    def test_catalog_compiles_all_current_moris_character_keys(self):
        self.assertEqual(len(self.catalog.characters), 202)

    def test_structural_full_generic_routes_non_special_team_to_fast(self):
        team = ('토브', '블랑', '도로시 : 세렌디피티', '루주', '드레이크')
        decision = route_team(team, self.by_name, self.full)
        self.assertTrue(decision.fast_exact, decision.blockers)

    def test_ain_routes_to_moris_due_to_feather_refresh(self):
        team = ('아인', '리타', '크라운', '헬름', '앨리스')
        decision = route_team(team, self.by_name, self.full)
        self.assertFalse(decision.fast_exact)
        self.assertTrue(any(b.stat == 'feather_refresh' for b in decision.blockers), decision.blockers)

    def test_missing_c_subsystem_routes_with_explicit_blocker(self):
        profile = FastSupportProfile(c_subsystems=frozenset({'arithmetic'}))
        decision = route_team(('리타',), self.by_name, profile)
        self.assertFalse(decision.fast_exact)
        self.assertTrue(any(b.reason.startswith('unimplemented_subsystem:') for b in decision.blockers))

    def test_unknown_character_never_silently_fast_routes(self):
        decision = route_team(('없는 캐릭터',), self.by_name, self.full)
        self.assertFalse(decision.fast_exact)
        self.assertEqual(decision.blockers[0].reason, 'unknown_character')


if __name__ == '__main__':
    unittest.main(verbosity=2)
