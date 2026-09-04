from pathlib import Path

score_path = Path("fast_engine/engine/score.py")
score_text = score_path.read_text(encoding="utf-8")
old = '_PATTERNLESS_UNREACHABLE_EVENT_KEYS = frozenset({"received_hit"})'
new = '''_PATTERNLESS_UNREACHABLE_EVENT_KEYS = frozenset({
    "received_hit",
    "enemy_death",
    "event:part_destroy",
})'''
if score_text.count(old) != 1:
    raise SystemExit("expected exactly one patternless event set")
score_path.write_text(score_text.replace(old, new, 1), encoding="utf-8")
print("patched", score_path)

board_test = Path("fast_engine/tests/test_damage_patternless_board.py")
board_text = board_test.read_text(encoding="utf-8")
stale = '        "normal_delivery:볼륨:프리스타일:atk_pct",\n'
if board_text.count(stale) != 1:
    raise SystemExit("expected exactly one stale Volume blocker expectation")
board_test.write_text(board_text.replace(stale, "", 1), encoding="utf-8")
print("updated", board_test)

focused = Path("fast_engine/tests/test_patternless_encounter_events.py")
focused.write_text('''from context import snapshot, spec\nfrom fast_engine.engine.compiler import compile_moris_squad\nfrom fast_engine.engine.dispatcher import TriggerDispatcher\nfrom fast_engine.engine.score import static_score_blockers\n\n\ndef _compile_case(source_name: str):\n    members = tuple(str(x) for x in snapshot.SQUADS[source_name]["members"])\n    return compile_moris_squad(spec.build_squad(list(members)))\n\n\ndef test_patternless_enemy_death_effect_is_not_a_score_blocker():\n    compiled = _compile_case("레이드_볼륨")\n    blockers = static_score_blockers(compiled)\n    assert "normal_delivery:볼륨:프리스타일:atk_pct" not in blockers\n    assert "skill_state_delivery:볼륨:프리스타일:atk_pct" not in blockers\n\n    effect = next(effect for effect in compiled.effects if effect.name == "프리스타일")\n    assert TriggerDispatcher.is_executable_effect(effect)\n    assert any(rule.event_key == "enemy_death" for rule in effect.triggers)\n\n\ndef test_patternless_part_destroy_effect_is_not_a_score_blocker():\n    compiled = _compile_case("레이드_이브레이븐")\n    blockers = static_score_blockers(compiled)\n    assert "skill_state_delivery:레이븐:일점 공격:dot_dmg_pct" not in blockers\n\n    effect = next(effect for effect in compiled.effects if effect.name == "일점 공격")\n    assert TriggerDispatcher.is_executable_effect(effect)\n    assert any(rule.event_key == "event:part_destroy" for rule in effect.triggers)\n\n\ndef test_other_named_events_remain_fail_closed():\n    compiled = _compile_case("스쿼드1")\n    blockers = static_score_blockers(compiled)\n    assert "normal_delivery:크라운:로얄 에타이어 4:atk_dmg_pct" in blockers\n''', encoding="utf-8")
print("created", focused)
