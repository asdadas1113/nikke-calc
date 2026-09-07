from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p=Path(path); s=p.read_text(encoding='utf-8')
    if old not in s:
        raise SystemExit(f'anchor missing in {path}: {old[:120]!r}')
    p.write_text(s.replace(old,new,1),encoding='utf-8')

# Snow White's exact one-shot SR mode is now intentionally owned. Preserve the
# neighboring safety assertion on the still-unowned reverse/warmup families.
replace_once(
    'fast_engine/tests/test_damage_moran_weapon_change_lifecycle.py',
'''    def test_other_class_changing_weapon_changes_remain_blocked(self):
        found = False
        for name, case in snapshot.SQUADS.items():
            if str(name).startswith("지그_") or "스노우 화이트" not in case["members"]:
                continue
            compiled = compile_moris_squad(spec.build_squad(list(case["members"])))
            if any(blocker.startswith("weapon_change:스노우 화이트:") for blocker in static_score_blockers(compiled)):
                found = True
                break
        self.assertTrue(found)
''',
'''    def test_unowned_class_changing_weapon_changes_remain_blocked(self):
        for name, blocker in (
            ("레이드_네온벨벳", "weapon_change:벨벳:깔끔한 마무리"),
            ("레이드_작열짬", "weapon_change:모더니아:섬멸 모드"),
        ):
            with self.subTest(name=name):
                case = snapshot.SQUADS[name]
                compiled = compile_moris_squad(spec.build_squad(list(case["members"])))
                self.assertIn(blocker, static_score_blockers(compiled))
''')

# EX 매거진 2 was already a generic dynamic-reload mechanic; its only blocker in
# 스쿼드2 was an unsafe recipient cadence. Owning Zwei's exact cross-mode cadence
# resolves that recipient dependency. EX 매거진 3 and all other public pairs stay
# fail-closed, so encode the precise transitive frontier change rather than masking it.
replace_once(
    'fast_engine/tests/test_dynamic_charge_max_ammo_semantics.py',
'''    def test_privaty_public_pairs_remain_fail_closed_behind_recipient_dependencies(self):
        names=("스쿼드2","레이드_아니스서머메이든","레이드_라피앨리스","레이드_트리나홍련")
        for name in names:
            with self.subTest(name=name):
                case=snapshot.SQUADS[name]
                compiled=compile_moris_squad(spec.build_squad(list(case["members"])))
                blockers=static_score_blockers(compiled)
                self.assertIn("cadence:프리바티:EX 매거진 2:reload_speed_pct",blockers)
                self.assertIn("cadence:프리바티:EX 매거진 3:max_ammo_pct",blockers)
''',
'''    def test_privaty_public_pairs_remain_fail_closed_behind_remaining_recipient_dependencies(self):
        names=("스쿼드2","레이드_아니스서머메이든","레이드_라피앨리스","레이드_트리나홍련")
        for name in names:
            with self.subTest(name=name):
                case=snapshot.SQUADS[name]
                compiled=compile_moris_squad(spec.build_squad(list(case["members"])))
                blockers=static_score_blockers(compiled)
                reload_blocker="cadence:프리바티:EX 매거진 2:reload_speed_pct"
                if name == "스쿼드2":
                    self.assertNotIn(reload_blocker,blockers)
                else:
                    self.assertIn(reload_blocker,blockers)
                self.assertIn("cadence:프리바티:EX 매거진 3:max_ammo_pct",blockers)
''')

# Keep the transitive recipient-dependency change visible in the new checkpoint.
p=Path('fast_engine/tests/test_damage_single_charge_weapon_change.py')
s=p.read_text(encoding='utf-8')
anchor='''    def test_neighboring_shapes_fail_closed(self):
'''
insert='''    def test_squad2_resolves_only_privaty_reload_recipient_dependency(self):
        blockers=static_normal_score_blockers(compiled("스쿼드2"))
        self.assertNotIn("cadence:프리바티:EX 매거진 2:reload_speed_pct",blockers)
        self.assertIn("cadence:프리바티:EX 매거진 3:max_ammo_pct",blockers)

''' + anchor
if anchor not in s:
    raise SystemExit('single-charge test anchor missing')
p.write_text(s.replace(anchor,insert,1),encoding='utf-8')

print('updated stale neighboring expectations with exact remaining fail-closed scope')
