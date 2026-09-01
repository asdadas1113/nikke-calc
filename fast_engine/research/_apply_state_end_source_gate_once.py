from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}")
    p.write_text(text.replace(old, new, 1))


marker = '''def _ammo_charge_named_event_safe(squad: CompiledSquad, effect) -> bool:
'''
helper = '''def _timed_self_state_end_source_score_safe(squad: CompiledSquad, effect) -> bool:
    """Prove every state-end trigger comes from Fast's certified source bridge.

    Dispatcher may parse a narrow ``event:state_end:*`` consumer, but score
    certification must additionally prove that the named source state is one
    Fast actually emits: an executable finite-duration self buff owned by the
    same actor, with an ordinary time lifetime.  Any ambiguous/unsupported
    provider keeps the consumer fail-closed.
    """

    keys = tuple(
        rule.event_key
        for rule in effect.triggers
        if (rule.event_key or "").startswith("event:state_end:")
    )
    if not keys:
        return True
    if len(keys) != len(effect.triggers):
        return False

    for key in keys:
        name = key[len("event:state_end:"):]
        if not name:
            return False
        providers = tuple(
            provider
            for provider in squad.members[effect.actor].effects
            if provider.effect_id != effect.effect_id and provider.name == name
        )
        if not providers:
            return False
        for provider in providers:
            if (
                provider.effect_type != "buff"
                or provider.target_spec.mode.value != "self"
                or provider.duration is None
                or float(provider.duration) < 0.0
                or provider.parameters.get("duration_bullets") is not None
                or not TriggerDispatcher.is_executable_effect(provider)
            ):
                return False
    return True


''' + marker
replace_once("fast_engine/engine/score.py", marker, helper)

for anchor in (
    '''    if not TriggerDispatcher.is_executable_effect(effect):
        return False
    mg_targets = tuple(
''',
    '''    if not TriggerDispatcher.is_executable_effect(effect):
        return False
    targets = _possible_ally_targets(squad, effect)
    return bool(targets) and all(_reload_recipient_score_safe(squad, actor) for actor in targets)
''',
    '''    if not TriggerDispatcher.is_executable_effect(effect):
        return False
    targets = _possible_ally_targets(squad, effect)
    return bool(targets) and all(_rapid_actor_score_safe(squad, actor) for actor in targets)
''',
):
    if anchor not in Path("fast_engine/engine/score.py").read_text():
        raise SystemExit(f"score.py anchor missing: {anchor[:60]!r}")

replace_once(
    "fast_engine/engine/score.py",
    '''    if not TriggerDispatcher.is_executable_effect(effect):
        return False
    mg_targets = tuple(
''',
    '''    if not TriggerDispatcher.is_executable_effect(effect):
        return False
    if not _timed_self_state_end_source_score_safe(squad, effect):
        return False
    mg_targets = tuple(
''',
)
replace_once(
    "fast_engine/engine/score.py",
    '''    if not TriggerDispatcher.is_executable_effect(effect):
        return False
    targets = _possible_ally_targets(squad, effect)
    return bool(targets) and all(_reload_recipient_score_safe(squad, actor) for actor in targets)
''',
    '''    if not TriggerDispatcher.is_executable_effect(effect):
        return False
    if not _timed_self_state_end_source_score_safe(squad, effect):
        return False
    targets = _possible_ally_targets(squad, effect)
    return bool(targets) and all(_reload_recipient_score_safe(squad, actor) for actor in targets)
''',
)
replace_once(
    "fast_engine/engine/score.py",
    '''    if not TriggerDispatcher.is_executable_effect(effect):
        return False
    targets = _possible_ally_targets(squad, effect)
    return bool(targets) and all(_rapid_actor_score_safe(squad, actor) for actor in targets)
''',
    '''    if not TriggerDispatcher.is_executable_effect(effect):
        return False
    if not _timed_self_state_end_source_score_safe(squad, effect):
        return False
    targets = _possible_ally_targets(squad, effect)
    return bool(targets) and all(_rapid_actor_score_safe(squad, actor) for actor in targets)
''',
)

# Regression: a state-end consumer whose named provider is not part of the
# timed-self bridge must remain a cadence blocker.  Also directly exercise the
# Moris rule that force_reload is ignored while a reload is already running.
p = Path("fast_engine/tests/test_damage_state_end_force_reload.py")
text = p.read_text()
insert = '''    def test_asuka_state_end_cadence_bundle_is_certified(self):
'''
new_tests = '''    def test_unsupported_state_end_provider_keeps_force_reload_blocked(self):
        from dataclasses import replace

        provider = replace(
            _provider(),
            target="all_allies",
            target_spec=compile_target(
                "all_allies",
                actor_by_name={"synthetic-reload": 0},
            ),
        )
        force = _force()
        effects = (provider, force)
        member = _member(effects, fire_mode="auto", weapon_type="AR")
        squad = CompiledSquad(
            (member,),
            TriggerIndex.from_effects(effects, actor_count=1),
        )
        self.assertIn(
            "cadence:synthetic-reload:force:force_reload",
            static_normal_score_blockers(squad),
        )

    def test_force_reload_is_ignored_while_already_reloading(self):
        force = _force()
        effects = (force,)
        member = _member(effects, fire_mode="auto", weapon_type="AR")
        from dataclasses import replace
        weapon = dict(member.weapon)
        weapon.update(max_ammo=1, fire_rate=2.0, reload_time=2.0, reload_start_delay=0.0)
        member = replace(member, weapon=weapon)
        squad = CompiledSquad(
            (member,),
            TriggerIndex.from_effects(effects, actor_count=1),
        )
        runtime = BurstRuntime(
            squad,
            BurstPolicy(duration=3.0, first_burst_time=10.0),
            EnemyStaticProfile(defense=0.0, duration=3.0),
        )
        observer = StaticNormalAttackObserver(runtime, duration=3.0)
        runtime.start(duration=3.0)
        # First shot at 0.0 leaves reload_wait; advance through the 0.5 reload
        # probe so a 2.0s reload is already fixed to end at 2.5.
        runtime.weapons.advance_to(0.6, inclusive=True)
        st = runtime.weapons._rapid_reload._states[0]
        self.assertEqual(st.phase, "reloading")
        before = st.phase_end
        self.assertTrue(runtime.weapons.apply_force_reload((0,), 1.0))
        self.assertEqual(st.phase, "reloading")
        self.assertEqual(st.phase_end, before)

''' + insert
if new_tests not in text:
    if text.count(insert) != 1:
        raise SystemExit(f"test insert anchor count={text.count(insert)}")
    p.write_text(text.replace(insert, new_tests, 1))
