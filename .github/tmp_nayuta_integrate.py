from __future__ import annotations

from pathlib import Path

p = Path('.github/tmp_nayuta_apply.py')
s = p.read_text(encoding='utf-8')

if '_moris_frame_observed_actors' in s:
    print('Nayuta helper already integrated')
    raise SystemExit(0)

old = '''        expected_target=("all_enemies" if stat == "damage" else "same_target")\\n        if not (\\n            consumer.actor == actor\\n            and consumer.effect_type == "damage"\\n            and stat in {"damage","bonus_damage"}\\n            and stat not in seen\\n            and target_mode == expected_target\\n'''
new = '''        if not (\\n            consumer.actor == actor\\n            and consumer.effect_type == "damage"\\n            and stat in {"damage","bonus_damage"}\\n            and stat not in seen\\n            and target_mode == "enemy"\\n'''
if old not in s:
    raise SystemExit('helper proof anchor missing')
s = s.replace(old, new, 1)

anchor = "replace_once(p,old,new)\n\n# dynamic_weapon.py: compose base rapid suspension with dormant charge session.\n"
frame_patch = """replace_once(p,old,new)
old='''        \"_squad_ammo_generation\", \"_squad_ammo_scheduled_time\",\\n        \"_squad_ammo_dispatched_count\",\\n    )\\n'''
new='''        \"_squad_ammo_generation\", \"_squad_ammo_scheduled_time\",\\n        \"_squad_ammo_dispatched_count\", \"_moris_frame_observed_actors\",\\n    )\\n'''
replace_once(p,old,new)
old='''        self._squad_ammo_generation = 0\\n        self._squad_ammo_scheduled_time: float | None = None\\n        self._squad_ammo_dispatched_count = 0\\n\\n    def attach_score_sink'''
new='''        self._squad_ammo_generation = 0\\n        self._squad_ammo_scheduled_time: float | None = None\\n        self._squad_ammo_dispatched_count = 0\\n        self._moris_frame_observed_actors: set[int] = set()\\n\\n    def _weapon(self, actor: int, now: float) -> dict:\\n        weapon=super()._weapon(actor,now)\\n        if actor not in self._moris_frame_observed_actors or weapon.get(\"_moris_frame_observed\"):\\n            return weapon\\n        marked=dict(weapon)\\n        marked[\"_moris_frame_observed\"]=True\\n        return marked\\n\\n    def attach_score_sink'''
replace_once(p,old,new)
old='''        full=self._full_ammo(int(actor),float(now))\\n        st.ammo=full\\n'''
new='''        self._moris_frame_observed_actors.add(int(actor))\\n        full=self._full_ammo(int(actor),float(now))\\n        st.ammo=full\\n'''
replace_once(p,old,new)

# dynamic_weapon.py: compose base rapid suspension with dormant charge session.
"""
if anchor not in s:
    raise SystemExit('helper dynamic rapid insertion anchor missing')
s = s.replace(anchor, frame_patch, 1)

s = s.replace(
    'from fast_engine.engine.burst import BurstPolicy\n',
    'from fast_engine.engine.burst import BurstPolicy, BurstSignal\n',
    1,
)
s = s.replace(
    'from fast_engine.engine.compiler import compile_moris_squad\n',
    'from fast_engine.engine.compiler import compile_moris_squad\nfrom fast_engine.engine.conditions import SignalContext\n',
    1,
)
s = s.replace(
    'from fast_engine.engine.model import EnemyStaticProfile, CompiledSquad\n',
    'from fast_engine.engine.model import EnemyStaticProfile, CompiledSquad\nfrom fast_engine.engine.scheduler import EventKind\n',
    1,
)

start = s.index('    def test_first_public_session_matches_moris_five_skill_shots_and_live_full_resume(self):')
end = s.index('    def test_skill_mode_scoring_excludes_normal_attack_bonus_but_keeps_charge_and_core(self):', start)
method = '''    def test_first_public_session_matches_moris_five_skill_shots_and_live_full_resume(self):
        team="스쿼드2"
        case=snapshot.SQUADS[team]
        moris_squad=spec.build_squad(list(case["members"]))
        cfg=spec.build_config(moris_squad,{"duration":13.25,"first_burst_time":3.0})
        moris=simulate(moris_squad,config=cfg,enemy={"def":0,"code":"","core_px":0,"has_parts":False},seed=42,verbose=True)
        moris_times=[h.t for h in moris.hits if h.caster=="나유타" and h.skill_name=="기억 연소"]
        moris_resume=[h.t for h in moris.hits if h.caster=="나유타" and _is_normal(h) and h.t>=13.19]
        self.assertEqual(len(moris_times),5)
        self.assertEqual(len(moris_resume),1)
        self.assertAlmostEqual(moris_resume[0],13.2,places=6)
        self.assertTrue(all(not _is_normal(h) for h in moris.hits if h.caster=="나유타" and h.skill_name=="기억 연소"))

        squad=compile_moris_squad(moris_squad)
        actor,effect=wc_of(squad)
        privaty_ammo=next(e for e in squad.effects if e.name=="EX 매거진 3")
        runtime=BurstRuntime(squad,BurstPolicy(duration=13.25,first_burst_time=3.0),EnemyStaticProfile(defense=0.0,duration=13.25,core_px=0.0))
        mode_times=[]
        base_blocks=[]
        runtime.weapons.attach_score_shot_sink((actor,),lambda a,t: mode_times.append(t))
        runtime.weapons.attach_score_block_sink((actor,),lambda a,c,t: base_blocks.append((c,t)))
        # Do not call BurstRuntime.start/run here: this public roster contains an
        # unrelated Privaty static-last-bullet safety blocker. Exercise only the
        # exact weapon/effect/scheduler slice owned by this checkpoint.
        runtime.weapons.start(0.0)

        def process_before(limit):
            while runtime.scheduler and (runtime.scheduler.peek_time() or 0.0) < limit-1e-9:
                event=runtime.scheduler.pop()
                if event.kind is EventKind.WEAPON_BOUNDARY:
                    runtime.weapons.handle_boundary(event)
                    runtime.weapons.sync(event.time)
                elif event.kind is EventKind.PRE_SHOT_BOUNDARY:
                    runtime.weapons.handle_pre_shot_boundary(event)
                    runtime.weapons.sync(event.time)
                elif event.kind is EventKind.STATE_EXPIRE:
                    runtime.dispatcher.handle_expiry(event)
                    runtime.weapons.sync(event.time)
                elif event.kind is EventKind.STATE_END_NOTIFY:
                    owner,name=event.payload
                    runtime.dispatcher.dispatch(
                        BurstSignal(event.time,f"event:state_end:{name}",int(owner),int(owner)),
                        context=SignalContext(),
                    )
                    runtime.weapons.sync(event.time)
                else:
                    runtime.weapons.advance_to(event.time,inclusive=False)
            runtime.weapons.advance_to(limit,inclusive=False)

        process_before(3.2)
        runtime.dispatcher.effects.activate_group(effect,(actor,),3.2,runtime.scheduler)
        runtime.weapons.sync(3.2)
        process_before(3.4)
        runtime.dispatcher.effects.activate_group(privaty_ammo,(actor,),3.4,runtime.scheduler)
        runtime.weapons.sync(3.4)
        process_before(13.25)

        self.assertEqual(len(mode_times),5)
        for actual,expected in zip(mode_times,moris_times):
            self.assertAlmostEqual(actual,expected,places=6)
        rapid=runtime.weapons._rapid_reload
        self.assertEqual(rapid._full_ammo(actor,13.2),215)
        self.assertEqual(rapid._states[actor].ammo,214)
        self.assertAlmostEqual(rapid._states[actor].last_shot,13.2,places=6)
        self.assertAlmostEqual(rapid._states[actor].phase_end,13.25,places=6)
        self.assertFalse(runtime.weapons.is_skill_weapon_mode(actor,13.2))
        self.assertEqual(runtime.weapons._states[actor].phase,"dormant")

'''
s = s[:start] + method + s[end:]
p.write_text(s, encoding='utf-8')
print('integrated diagnosed Nayuta proof/timing fixes into WIP helper')
