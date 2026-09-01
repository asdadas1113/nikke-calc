from pathlib import Path

p = Path("fast_engine/tests/test_damage_state_end_force_reload.py")
text = p.read_text()
old = '''    def test_force_reload_is_ignored_while_already_reloading(self):
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
'''
new = '''    def test_force_reload_is_ignored_while_already_reloading(self):
        effects = ()
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
        runtime.weapons.attach_score_block_sink((0,), lambda _actor, _count, _time: None)
        runtime.start(duration=3.0)
'''
if new not in text:
    if text.count(old) != 1:
        raise SystemExit(f"direct force-reload test anchor count={text.count(old)}")
    p.write_text(text.replace(old, new, 1))
