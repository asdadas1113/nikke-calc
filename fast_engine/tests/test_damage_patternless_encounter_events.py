from unittest import TestCase

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.score import static_score_blockers


def _compile_case(source_name: str):
    members = tuple(str(x) for x in snapshot.SQUADS[source_name]["members"])
    return compile_moris_squad(spec.build_squad(list(members)))


class PatternlessEncounterEventScoreTests(TestCase):
    def test_enemy_death_effect_is_not_a_score_blocker(self):
        compiled = _compile_case("레이드_볼륨")
        blockers = static_score_blockers(compiled)
        self.assertNotIn("normal_delivery:볼륨:프리스타일:atk_pct", blockers)
        self.assertNotIn("skill_state_delivery:볼륨:프리스타일:atk_pct", blockers)

        effect = next(effect for effect in compiled.effects if effect.name == "프리스타일")
        self.assertTrue(TriggerDispatcher.is_executable_effect(effect))
        self.assertTrue(any(rule.event_key == "enemy_death" for rule in effect.triggers))

    def test_part_destroy_effect_is_not_a_score_blocker(self):
        compiled = _compile_case("레이드_이브레이븐")
        blockers = static_score_blockers(compiled)
        self.assertNotIn("skill_state_delivery:레이븐:일점 공격:dot_dmg_pct", blockers)

        effect = next(effect for effect in compiled.effects if effect.name == "일점 공격")
        self.assertTrue(TriggerDispatcher.is_executable_effect(effect))
        self.assertTrue(any(rule.event_key == "event:part_destroy" for rule in effect.triggers))

    def test_other_named_events_remain_fail_closed(self):
        compiled = _compile_case("스쿼드1")
        blockers = static_score_blockers(compiled)
        self.assertIn("normal_delivery:크라운:로얄 에타이어 4:atk_dmg_pct", blockers)
