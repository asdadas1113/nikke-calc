from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def replace_once(rel,old,new):
    p=ROOT/rel
    s=p.read_text()
    n=s.count(old)
    if n!=1:
        raise RuntimeError(f'{rel}: expected one replacement, got {n}: {old[:120]!r}')
    p.write_text(s.replace(old,new,1))

# dynamic_rapid.py — preserve the sparse rapid threshold planner, but let
# already-owned external charge shots contribute to its actual global count.
replace_once(
    'fast_engine/engine/dynamic_rapid.py',
    '''        "_squad_ammo_dispatched_count", "_moris_frame_observed_actors",\n        "_event_count_getter",\n''',
    '''        "_squad_ammo_dispatched_count", "_squad_ammo_external_count",\n        "_squad_ammo_external_actors", "_moris_frame_observed_actors",\n        "_event_count_getter",\n''',
)
replace_once(
    'fast_engine/engine/dynamic_rapid.py',
    '''        self._squad_ammo_dispatched_count = 0\n        self._moris_frame_observed_actors: set[int] = set()\n''',
    '''        self._squad_ammo_dispatched_count = 0\n        self._squad_ammo_external_count = 0\n        self._squad_ammo_external_actors: frozenset[int] = frozenset()\n        self._moris_frame_observed_actors: set[int] = set()\n''',
)
replace_once(
    'fast_engine/engine/dynamic_rapid.py',
    '''    def attach_squad_ammo_thresholds(self, thresholds: tuple[int, ...]) -> None:\n        if self._states:\n            raise RuntimeError("Fast squad-ammo thresholds must be attached before weapon start")\n        values=tuple(sorted({int(value) for value in thresholds if int(value)>0}))\n        if values and set(self.actors) != set(range(len(self.squad.members))):\n            raise NotImplementedError("Fast squad-ammo first slice requires every squad actor on rapid runtime")\n        self._squad_ammo_thresholds=values\n''',
    '''    def attach_squad_ammo_thresholds(\n        self,\n        thresholds: tuple[int, ...],\n        *,\n        external_actors: tuple[int, ...] | frozenset[int] = (),\n    ) -> None:\n        if self._states:\n            raise RuntimeError("Fast squad-ammo thresholds must be attached before weapon start")\n        values=tuple(sorted({int(value) for value in thresholds if int(value)>0}))\n        external=frozenset(int(actor) for actor in external_actors)\n        all_actors=set(range(len(self.squad.members)))\n        if values and (set(self.actors) | set(external)) != all_actors:\n            raise NotImplementedError("Fast squad-ammo requires every actor on an owned cadence runtime")\n        if set(self.actors) & set(external):\n            raise ValueError("Fast squad-ammo external actors overlap rapid runtime")\n        self._squad_ammo_thresholds=values\n        self._squad_ammo_external_actors=external\n''',
)
replace_once(
    'fast_engine/engine/dynamic_rapid.py',
    '''        current=sum(st.hit_count for st in probes.values())\n''',
    '''        current=sum(st.hit_count for st in probes.values()) + self._squad_ammo_external_count\n''',
)
replace_once(
    'fast_engine/engine/dynamic_rapid.py',
    '''    def refresh_squad_ammo_plan(self, now: float) -> None:\n        if not self._squad_ammo_thresholds:\n            return\n        self._squad_ammo_generation += 1\n        self._squad_ammo_scheduled_time=None\n        self._plan_squad_ammo(now)\n\n''',
    '''    def refresh_squad_ammo_plan(self, now: float) -> None:\n        if not self._squad_ammo_thresholds:\n            return\n        self._squad_ammo_generation += 1\n        self._squad_ammo_scheduled_time=None\n        self._plan_squad_ammo(now)\n\n    def record_external_squad_ammo(self, actor: int, now: float) -> int | None:\n        """Record one already-scored external physical shot.\n\n        Charge shots are sparse boundaries in the composite runtime. They do not\n        need to be predicted by the rapid probe: every observed external shot\n        advances the real global count and invalidates/replans the conservative\n        rapid-only future threshold. The returned increment is emitted only when\n        this exact charge shot crosses a compressed global threshold.\n        """\n        actor=int(actor)\n        if actor not in self._squad_ammo_external_actors:\n            raise ValueError("Fast squad-ammo external actor is not registered")\n        before=(\n            sum(st.hit_count for st in self._states.values())\n            + self._squad_ammo_external_count\n        )\n        target=self._next_squad_ammo_target(before)\n        self._squad_ammo_external_count += 1\n        after=before + 1\n        increment=None\n        if target is not None and after == target:\n            increment=target-self._squad_ammo_dispatched_count\n            if increment <= 0:\n                raise RuntimeError("Fast squad-ammo external crossing did not advance dispatched phase")\n            self._squad_ammo_dispatched_count=target\n        self.refresh_squad_ammo_plan(float(now))\n        return increment\n\n''',
)
replace_once(
    'fast_engine/engine/dynamic_rapid.py',
    '''        before=sum(state.hit_count for state in self._states.values())\n''',
    '''        before=(\n            sum(state.hit_count for state in self._states.values())\n            + self._squad_ammo_external_count\n        )\n''',
)

# dynamic_weapon.py — the composite runtime owns a suffix of ordinary charge
# actors as external squad-ammo contributors. Their normal shot is scored by the
# existing charge callback before the compressed squad-ammo signal is emitted.
replace_once(
    'fast_engine/engine/dynamic_weapon.py',
    '''        "_mode_only_rapid_actors",\n        "_external_weapon_block_until",\n''',
    '''        "_mode_only_rapid_actors",\n        "_squad_ammo_charge_actors",\n        "_external_weapon_block_until",\n''',
)
replace_once(
    'fast_engine/engine/dynamic_weapon.py',
    '''        self._mode_only_rapid_actors = frozenset(mode_only_rapid_ids)\n        if self._mode_only_rapid_actors:\n''',
    '''        self._mode_only_rapid_actors = frozenset(mode_only_rapid_ids)\n        self._squad_ammo_charge_actors: frozenset[int] = frozenset()\n        if self._mode_only_rapid_actors:\n''',
)
replace_once(
    'fast_engine/engine/dynamic_weapon.py',
    '''    def attach_squad_ammo_thresholds(self, thresholds: tuple[int, ...]) -> None:\n        self._rapid_reload.attach_squad_ammo_thresholds(thresholds)\n''',
    '''    def attach_squad_ammo_thresholds(self, thresholds: tuple[int, ...]) -> None:\n        rapid=set(self._rapid_reload.actors)\n        external=frozenset(set(range(len(self.squad.members))) - rapid)\n        if external:\n            if any(\n                actor not in self._score_actors\n                or str(self.squad.members[actor].weapon.get("fire_mode") or "") != "charge"\n                for actor in external\n            ):\n                raise NotImplementedError("Fast mixed squad-ammo external actor is not an owned charge scorer")\n            if rapid and max(rapid) >= min(external):\n                raise NotImplementedError("Fast mixed squad-ammo first slice requires charge actors after rapid actors")\n        self._squad_ammo_charge_actors=external\n        self._rapid_reload.attach_squad_ammo_thresholds(\n            thresholds, external_actors=external\n        )\n''',
)
replace_once(
    'fast_engine/engine/dynamic_weapon.py',
    '''        signals: list[DynamicCountSignal] = []\n        if actor in self._mode_only_charge_actors:\n''',
    '''        signals: list[DynamicCountSignal] = []\n        if actor in self._squad_ammo_charge_actors:\n            squad_increment=self._rapid_reload.record_external_squad_ammo(\n                actor,float(event.time)\n            )\n            if squad_increment is not None:\n                signals.append(DynamicCountSignal("squad_ammo_consume",squad_increment))\n        if actor in self._mode_only_charge_actors:\n''',
)

# score.py — keep the original all-rapid proof, add one deliberately narrow
# mixed partition: all rapid actors are already on rapid runtime, all remaining
# actors are ordinary safe charge actors forming a roster suffix, with no weapon
# changes or synthetic ammo-count additions.
replace_once(
    'fast_engine/engine/score.py',
    '''    actors.update(\n        effect.actor\n        for effect in squad.effects\n        if effect.effect_type == "weapon_change"\n        and (\n            _temporary_self_charge_weapon_change_score_supported(squad, effect)\n            or _temporary_self_charge_to_rapid_weapon_change_score_supported(squad, effect)\n        )\n    )\n    return tuple(sorted(actors))\n''',
    '''    actors.update(\n        effect.actor\n        for effect in squad.effects\n        if effect.effect_type == "weapon_change"\n        and (\n            _temporary_self_charge_weapon_change_score_supported(squad, effect)\n            or _temporary_self_charge_to_rapid_weapon_change_score_supported(squad, effect)\n        )\n    )\n    actors.update(_mixed_squad_ammo_charge_actors(squad))\n    return tuple(sorted(actors))\n''',
)
replace_once(
    'fast_engine/engine/score.py',
    '''    # First slice is intentionally all-rapid. Requiring every actor to already\n    # belong to the score runtime avoids inventing a second cadence model solely\n    # for this global counter.\n    if any(\n        effect.effect_type == "weapon_change"\n        and _temporary_self_rapid_weapon_change_score_supported(squad, effect)\n        for effect in squad.effects\n    ):\n        return False\n    rapid=set(_dynamic_rapid_reload_score_actors(squad))\n    if rapid != set(range(len(squad.members))):\n        return False\n    for actor,member in enumerate(squad.members):\n        if str(member.weapon.get("fire_mode") or "") not in {"auto","auto_warmup"}:\n            return False\n        if member.weapon.get("is_clip") or member.weapon.get("control"):\n            return False\n        if not _rapid_actor_score_safe(squad,actor):\n            return False\n''',
    '''    all_actors=set(range(len(squad.members)))\n    rapid_runtime=set(_dynamic_rapid_reload_score_actors(squad))\n    base_rapid={\n        actor for actor,member in enumerate(squad.members)\n        if str(member.weapon.get("fire_mode") or "") in {"auto","auto_warmup"}\n    }\n    base_charge={\n        actor for actor,member in enumerate(squad.members)\n        if str(member.weapon.get("fire_mode") or "") == "charge"\n    }\n    if rapid_runtime == all_actors:\n        # Preserve the original all-rapid ownership contract exactly.\n        if any(\n            other.effect_type == "weapon_change"\n            and _temporary_self_rapid_weapon_change_score_supported(squad, other)\n            for other in squad.effects\n        ):\n            return False\n        for actor,member in enumerate(squad.members):\n            if str(member.weapon.get("fire_mode") or "") not in {"auto","auto_warmup"}:\n                return False\n            if member.weapon.get("is_clip") or member.weapon.get("control"):\n                return False\n            if not _rapid_actor_score_safe(squad,actor):\n                return False\n    else:\n        # First mixed slice: ordinary rapid prefix + ordinary charge suffix.\n        # Future charge shots are already sparse scheduler boundaries; each one\n        # invalidates the rapid-only threshold projection, so no second cadence\n        # simulator or global frame loop is introduced.\n        if not base_rapid or not base_charge:\n            return False\n        if rapid_runtime != base_rapid or (base_rapid | base_charge) != all_actors:\n            return False\n        if max(base_rapid) >= min(base_charge):\n            return False\n        if any(other.effect_type == "weapon_change" for other in squad.effects):\n            return False\n        if any((other.stat or "") in {"gauge_consume_as_ammo","squad_ammo_consume_as"} for other in squad.effects):\n            return False\n        for actor,member in enumerate(squad.members):\n            if member.weapon.get("is_clip") or member.weapon.get("control"):\n                return False\n            if actor in base_rapid:\n                if not _rapid_actor_score_safe(squad,actor):\n                    return False\n            elif not _charge_actor_score_safe(squad,actor):\n                return False\n''',
)
replace_once(
    'fast_engine/engine/score.py',
    '''def _certified_squad_ammo_effect_ids(squad: CompiledSquad) -> frozenset[int]:\n    return frozenset(\n        effect.effect_id for effect in squad.effects\n        if _squad_ammo_sequential_damage_score_supported(squad,effect)\n    )\n\n\n''',
    '''def _certified_squad_ammo_effect_ids(squad: CompiledSquad) -> frozenset[int]:\n    return frozenset(\n        effect.effect_id for effect in squad.effects\n        if _squad_ammo_sequential_damage_score_supported(squad,effect)\n    )\n\n\ndef _mixed_squad_ammo_charge_actors(squad: CompiledSquad) -> tuple[int, ...]:\n    if not any(\n        _squad_ammo_sequential_damage_score_supported(squad,effect)\n        for effect in squad.effects\n    ):\n        return ()\n    rapid={\n        actor for actor,member in enumerate(squad.members)\n        if str(member.weapon.get("fire_mode") or "") in {"auto","auto_warmup"}\n    }\n    charge={\n        actor for actor,member in enumerate(squad.members)\n        if str(member.weapon.get("fire_mode") or "") == "charge"\n    }\n    if not rapid or not charge:\n        return ()\n    return tuple(sorted(charge))\n\n\n''',
)

# Focused regression file.
test=ROOT/'fast_engine/tests/test_damage_little_mermaid_mixed_squad_ammo.py'
test.write_text(r'''from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from context import snapshot, spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.burst_runtime import BurstRuntime
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.model import CompiledSquad, EnemyStaticProfile
from fast_engine.engine.score import (
    _certified_squad_ammo_effect_ids,
    _dynamic_charge_score_actors,
    _dynamic_rapid_reload_score_actors,
    _squad_ammo_sequential_damage_score_supported,
    static_score_blockers,
)
from fast_engine.engine.triggers import TriggerIndex


TEAM="스쿼드1"
EXPECTED=(
    (500,4.616666666666656,"라피 : 레드 후드"),
    (1000,7.04999999999998,"미하라 : 본딩 체인"),
    (1500,9.500000000000052,"크라운"),
    (2000,11.950000000000173,"크라운"),
    (2500,14.383333333333628,"라피 : 레드 후드"),
    (3000,17.616666666666948,"미하라 : 본딩 체인"),
    (3500,20.06666666666681,"라피 : 레드 후드"),
    (4000,22.500000000000004,"미하라 : 본딩 체인"),
    (4500,24.949999999999864,"라피 : 레드 후드"),
    (5000,27.433333333333056,"리틀 머메이드"),
)


def _compiled(team=TEAM):
    return compile_moris_squad(spec.build_squad(list(snapshot.SQUADS[team]["members"])))


def _barrage(squad):
    return next(effect for effect in squad.effects if effect.name=="거품 난사")


def _replace_effect(squad,effect_id,new_effect):
    members=list(squad.members)
    owner=squad.effects[effect_id].actor
    members[owner]=replace(
        members[owner],
        effects=tuple(new_effect if e.effect_id==effect_id else e for e in members[owner].effects),
    )
    effects=tuple(e for m in members for e in m.effects)
    return CompiledSquad(tuple(members),TriggerIndex.from_effects(effects,actor_count=len(members)))


def _runtime(squad,duration):
    moris=spec.build_squad([m.name for m in squad.members])
    policy=compile_burst_policy(moris,squad,{"duration":duration,"rng_mode":"expected"})
    runtime=BurstRuntime(squad,policy,EnemyStaticProfile(duration=duration,core_px=0.0))
    charge=_dynamic_charge_score_actors(squad)
    rapid=_dynamic_rapid_reload_score_actors(squad)
    runtime.weapons.attach_score_shot_sink(charge,lambda actor,time: None)
    runtime.weapons.attach_score_block_sink(rapid,lambda actor,count,time: None)
    ids=_certified_squad_ammo_effect_ids(squad)
    thresholds=tuple(sorted({
        int(rule.threshold or 0)
        for effect_id in ids
        for rule in squad.effects[effect_id].triggers
        if rule.event_key=="squad_ammo_consume"
    }))
    runtime.weapons.attach_squad_ammo_thresholds(thresholds)
    return runtime


class LittleMermaidMixedSquadAmmoTests(unittest.TestCase):
    def test_public_squad1_owns_mixed_prefix_suffix_but_neon_velvet_stays_closed(self):
        squad=_compiled()
        barrage=_barrage(squad)
        self.assertTrue(_squad_ammo_sequential_damage_score_supported(squad,barrage))
        self.assertNotIn(
            "skill_damage:리틀 머메이드:거품 난사:sequential_damage:10",
            static_score_blockers(squad),
        )
        self.assertEqual(_dynamic_rapid_reload_score_actors(squad),(0,1,2,3))
        self.assertEqual(_dynamic_charge_score_actors(squad),(4,))

        neon=_compiled("레이드_네온벨벳")
        neon_barrage=_barrage(neon)
        self.assertFalse(_squad_ammo_sequential_damage_score_supported(neon,neon_barrage))
        self.assertIn(
            "skill_damage:리틀 머메이드:거품 난사:sequential_damage:10",
            static_score_blockers(neon),
        )

    def test_public_first_ten_crossings_match_moris_oracle(self):
        squad=_compiled()
        runtime=_runtime(squad,30.0)
        seen=[]
        original=TriggerDispatcher.dispatch_team_hit
        def traced(dispatcher,event_key,**kwargs):
            if event_key=="squad_ammo_consume":
                seen.append((
                    dispatcher._event_counts.get((-1,event_key),0)+int(kwargs.get("count_increment",1)),
                    float(kwargs["time"]),
                    squad.members[int(kwargs["attacker"])].name,
                    int(kwargs.get("count_increment",1)),
                ))
            return original(dispatcher,event_key,**kwargs)
        with patch.object(TriggerDispatcher,"dispatch_team_hit",new=traced):
            runtime.run(duration=30.0)
        self.assertEqual(len(seen),10)
        for got,want in zip(seen,EXPECTED):
            self.assertEqual(got[0],want[0])
            self.assertAlmostEqual(got[1],want[1],places=9)
            self.assertEqual(got[2],want[2])
            self.assertEqual(got[3],500)

    def test_charge_crossing_scores_before_squad_ammo_signal(self):
        squad=_compiled()
        barrage=_barrage(squad)
        rule=replace(barrage.triggers[0],threshold=32.0,raw="squad_ammo_consume:32")
        squad=_replace_effect(squad,barrage.effect_id,replace(barrage,triggers=(rule,)))
        self.assertTrue(_squad_ammo_sequential_damage_score_supported(squad,_barrage(squad)))

        moris=spec.build_squad([m.name for m in squad.members])
        policy=compile_burst_policy(moris,squad,{"duration":1.1,"rng_mode":"expected"})
        runtime=BurstRuntime(squad,policy,EnemyStaticProfile(duration=1.1,core_px=0.0))
        order=[]
        charge=_dynamic_charge_score_actors(squad)
        rapid=_dynamic_rapid_reload_score_actors(squad)
        runtime.weapons.attach_score_shot_sink(
            charge,lambda actor,time: order.append(("normal",actor,float(time)))
        )
        runtime.weapons.attach_score_block_sink(rapid,lambda actor,count,time: None)
        runtime.weapons.attach_squad_ammo_thresholds((32,))
        original=TriggerDispatcher.dispatch_team_hit
        def traced(dispatcher,event_key,**kwargs):
            if event_key=="squad_ammo_consume":
                order.append(("skill_signal",int(kwargs["attacker"]),float(kwargs["time"])))
            return original(dispatcher,event_key,**kwargs)
        with patch.object(TriggerDispatcher,"dispatch_team_hit",new=traced):
            runtime.run(duration=1.1)
        at_one=[row for row in order if abs(row[2]-1.0)<1e-9]
        self.assertEqual(at_one[:2],[('normal',4,1.0000000000000013),('skill_signal',4,1.0000000000000013)])

    def test_non_suffix_charge_partition_fails_closed(self):
        members=list(snapshot.SQUADS[TEAM]["members"])
        reordered=[members[0],members[4],members[1],members[2],members[3]]
        squad=compile_moris_squad(spec.build_squad(reordered))
        barrage=_barrage(squad)
        self.assertFalse(_squad_ammo_sequential_damage_score_supported(squad,barrage))
        self.assertIn(
            "skill_damage:리틀 머메이드:거품 난사:sequential_damage:10",
            static_score_blockers(squad),
        )


if __name__=="__main__":
    unittest.main()
''')
print('mixed squad-ammo staging patch applied')
