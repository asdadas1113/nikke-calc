from pathlib import Path


def replace_once(path: str, old: str, new: str, label: str) -> None:
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"{label} anchor not found")
    p.write_text(text.replace(old, new, 1))


for path in (
    "fast_engine/tests/test_damage_full_charge_bullet_lifetime.py",
    "fast_engine/tests/test_damage_full_charge_hit_charge_speed.py",
    "fast_engine/tests/test_damage_stat_applied_charge_speed.py",
):
    replace_once(
        path,
        "self.assertEqual(certified, 3)",
        "self.assertEqual(certified, 4)",
        f"{path} certified frontier",
    )

replace_once(
    "fast_engine/tests/test_damage_state_end_named_stack.py",
    "def test_real_asuka_damage_and_remove_open_without_little_mermaid_leak(self):",
    "def test_real_asuka_damage_and_remove_coexist_with_owned_little_mermaid_lifecycle(self):",
    "state-end test name",
)
replace_once(
    "fast_engine/tests/test_damage_state_end_named_stack.py",
    '''        self.assertTrue(\n            any("리틀 머메이드:거품 난사" in blocker for blocker in blockers),\n            blockers,\n        )\n''',
    '''        # Little Mermaid is now opened only by its own separately proven\n        # replacement + squad-ammo lifecycle; Asuka state-end ownership must not\n        # be the reason it becomes executable. At the integrated public fixture\n        # both independent proofs are present, so neither blocker remains.\n        self.assertFalse(\n            any("리틀 머메이드:거품 난사" in blocker for blocker in blockers),\n            blockers,\n        )\n''',
    "state-end Little Mermaid frontier expectation",
)
