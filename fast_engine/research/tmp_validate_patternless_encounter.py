from __future__ import annotations

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.score import static_score_blockers


def compile_case(name: str):
    members = tuple(str(x) for x in snapshot.SQUADS[name]["members"])
    return members, compile_moris_squad(spec.build_squad(list(members)))


def main():
    volume_members, volume = compile_case("레이드_볼륨")
    raven_members, raven = compile_case("레이드_이브레이븐")
    crown_members, crown = compile_case("스쿼드1")

    volume_blockers = static_score_blockers(volume)
    raven_blockers = static_score_blockers(raven)
    crown_blockers = static_score_blockers(crown)

    volume_target = "normal_delivery:볼륨:프리스타일:atk_pct"
    volume_skill_target = "skill_state_delivery:볼륨:프리스타일:atk_pct"
    raven_target = "skill_state_delivery:레이븐:일점 공격:dot_dmg_pct"
    crown_guard = "normal_delivery:크라운:로얄 에타이어 4:atk_dmg_pct"

    print("VOLUME", volume_members)
    print("volume_target_present", volume_target in volume_blockers)
    print("volume_skill_target_present", volume_skill_target in volume_blockers)
    print("RAVEN", raven_members)
    print("raven_target_present", raven_target in raven_blockers)
    print("CROWN_GUARD", crown_members)
    print("crown_guard_present", crown_guard in crown_blockers)

    assert volume_target not in volume_blockers
    assert volume_skill_target not in volume_blockers
    assert raven_target not in raven_blockers
    assert crown_guard in crown_blockers

    # This slice is score-certification only: the underlying effects remain
    # executable dispatcher effects and are not rewritten into generic no-ops.
    volume_effect = next(e for e in volume.effects if e.name == "프리스타일")
    raven_effect = next(e for e in raven.effects if e.name == "일점 공격")
    assert TriggerDispatcher.is_executable_effect(volume_effect)
    assert TriggerDispatcher.is_executable_effect(raven_effect)
    assert any(rule.event_key == "enemy_death" for rule in volume_effect.triggers)
    assert any(rule.event_key == "event:part_destroy" for rule in raven_effect.triggers)


if __name__ == "__main__":
    main()
