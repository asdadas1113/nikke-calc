from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"anchor not found: {path}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# Comparison-critical skill-damage gaps must block before a 180s Fast run.
replace_once(
    "fast_engine/engine/score.py",
    '''def static_score_blockers(squad: CompiledSquad) -> tuple[str, ...]:\n    blockers = list(static_normal_score_blockers(squad))\n    for effect in squad.effects:\n''',
    '''def static_score_blockers(squad: CompiledSquad) -> tuple[str, ...]:\n    blockers = list(static_normal_score_blockers(squad))\n\n    # Mirror the damage sink's compile-time support decision before running the\n    # combat timeline. Unsupported comparison-critical skill damage must fail\n    # closed here instead of burning a full Fast evaluation and only appearing\n    # later in FastScore.unsupported. Runtime-dependent gauge checks remain safe:\n    # SimpleDamageScoreSink treats an unattached runtime as compile-time proof.\n    from .damage_runtime import SimpleDamageScoreSink\n    from .model import EnemyStaticProfile\n\n    damage_sink = SimpleDamageScoreSink(\n        squad, EnemyStaticProfile(defense=0.0, duration=1.0)\n    )\n    for effect in squad.effects:\n        if (\n            effect.effect_type == "damage"\n            and not _is_patternless_unreachable(effect)\n            and not damage_sink.supports(effect)\n        ):\n            owner = squad.members[effect.actor].name\n            blockers.append(\n                f"skill_damage:{owner}:"\n                f"{effect.name or effect.stat or '?'}:{effect.stat or '?'}"\n            )\n\n    for effect in squad.effects:\n''',
)

# Lock the public Red Hood team to the new fail-closed boundary: weapon-change
# and Mint max-ammo are supported, while Rapi's unrelated damage gaps are static.
replace_once(
    "fast_engine/tests/test_dynamic_weapon_change.py",
    '''        squad, compiled = self._team("레이드_레드후드퀀시")\n        self.assertEqual(static_score_blockers(compiled), ())\n        cfg = spec.build_config(squad, {\n            "duration": 30.0,\n            "first_burst_time": 3.0,\n            "rng_mode": "expected",\n        })\n        policy = compile_burst_policy(squad, compiled, cfg)\n        score = score_static_squad(\n            compiled,\n            policy,\n            EnemyStaticProfile(defense=31784.0, duration=30.0),\n        )\n        self.assertGreater(score.squad_total, 0.0)\n        self.assertTrue(score.unsupported)\n        self.assertTrue(all(item.startswith("skill_damage:라피 : 레드 후드:") for item in score.unsupported))\n        self.assertFalse(any("weapon_change" in item or "max_ammo" in item for item in score.unsupported))\n''',
    '''        squad, compiled = self._team("레이드_레드후드퀀시")\n        blockers = static_score_blockers(compiled)\n        rapi_damage = tuple(\n            item for item in blockers\n            if item.startswith("skill_damage:라피 : 레드 후드:")\n        )\n        self.assertEqual(len(rapi_damage), 4)\n        self.assertFalse(any("weapon_change" in item or "max_ammo" in item for item in blockers))\n        cfg = spec.build_config(squad, {\n            "duration": 30.0,\n            "first_burst_time": 3.0,\n            "rng_mode": "expected",\n        })\n        policy = compile_burst_policy(squad, compiled, cfg)\n        with self.assertRaises(NotImplementedError):\n            score_static_squad(\n                compiled,\n                policy,\n                EnemyStaticProfile(defense=31784.0, duration=30.0),\n            )\n''',
)

# Preserve the standardized public 24-team universe now that snapshot contains
# additional jig-only cases.
replace_once(
    "fast_engine/research/public_ranking_probe.py",
    '''    for name, case in snapshot.SQUADS.items():\n        members = tuple(str(member) for member in case["members"])\n''',
    '''    for name, case in snapshot.SQUADS.items():\n        if str(name).startswith("지그_"):\n            continue\n        members = tuple(str(member) for member in case["members"])\n''',
)
