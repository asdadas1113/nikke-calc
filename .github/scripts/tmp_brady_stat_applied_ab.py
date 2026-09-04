from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import subprocess
from unittest.mock import patch


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"missing patch marker: {label}")
    return text.replace(old, new, 1)


def apply_patch() -> None:
    p = Path("fast_engine/engine/dispatcher.py")
    s = p.read_text(encoding="utf-8")
    s = replace_once(
        s,
        '_INTERNAL_BULLET_CONSUME_EVENT = "__fast_consume_dynamic_bullet_lifetime__"\n',
        '_INTERNAL_BULLET_CONSUME_EVENT = "__fast_consume_dynamic_bullet_lifetime__"\n'
        '_STAT_APPLIED_EVENT_STATS = frozenset({"dot_dmg_pct", "split_dmg_pct"})\n',
        "stat constant",
    )
    marker = '    @staticmethod\n    def _charge_speed_bullet_lifetime_shape_supported(effect: "CompiledEffect") -> bool:\n'
    helper = '''    @staticmethod
    def _stat_applied_event_stat(key: str) -> str | None:
        prefix = "event:stat_applied:"
        if not key.startswith(prefix):
            return None
        stat = key[len(prefix):]
        return stat if stat in _STAT_APPLIED_EVENT_STATS else None

    @classmethod
    def _stat_applied_charge_speed_shape_supported(cls, effect: "CompiledEffect") -> bool:
        """Certify one finite self charge-speed state driven by recipient stat application."""
        if not (
            effect.capability.disposition is CapabilityDisposition.PLANNED
            and set(effect.capability.blockers) == {"timing:named_event"}
            and effect.effect_type == "buff"
            and (effect.stat or "") == "charge_speed_pct"
            and effect.target_spec.mode is TargetMode.SELF
            and effect.value is not None
            and float(effect.value) > -100.0
            and effect.duration is not None
            and float(effect.duration) > 0.0
            and effect.max_stack in (None, 1, 1.0)
            and effect.max_trigger is None
            and effect.tick_interval is None
            and not effect.parameters
            and len(effect.triggers) == 1
        ):
            return False
        rule = effect.triggers[0]
        if rule.mode is not TriggerMode.EVENT or cls._stat_applied_event_stat(rule.event_key or "") is None:
            return False
        return (
            not effect.condition_rules
            or (
                len(effect.condition_rules) == 1
                and effect.condition_rules[0].mode is ConditionMode.NOT_SELF_STATE
                and bool(effect.condition_rules[0].key)
            )
        )

    @classmethod
    def stat_applied_dependency_score_safe(
        cls, squad: "CompiledSquad", effect: "CompiledEffect", key: str
    ) -> bool:
        """Prove recipient-scoped stat_applied source ownership without guessing."""
        stat = cls._stat_applied_event_stat(key)
        if stat is None:
            return False
        owner = effect.actor
        providers = tuple(
            provider
            for provider in squad.effects
            if provider.effect_id != effect.effect_id
            and (provider.stat or "") == stat
            and owner in possible_ally_targets(squad, provider)
        )
        if not providers:
            return False
        for provider in providers:
            if (
                provider.effect_type != "buff"
                or not provider.target_spec.runtime_supported
                or cls._named_event_keys(provider)
                or not cls.is_executable_effect(provider)
            ):
                return False

        # First slice may keep a NOT_SELF_STATE gate only when every matching
        # state is another stat_applied charge-speed branch whose source stat is
        # provably absent for this recipient. This makes the condition immutable.
        for condition in effect.condition_rules:
            if condition.mode is not ConditionMode.NOT_SELF_STATE or not condition.key:
                return False
            state_effects = tuple(
                candidate
                for candidate in squad.members[owner].effects
                if candidate.effect_id != effect.effect_id and candidate.name == condition.key
            )
            for state_effect in state_effects:
                if not cls._stat_applied_charge_speed_shape_supported(state_effect):
                    return False
                state_keys = cls._named_event_keys(state_effect)
                if len(state_keys) != 1:
                    return False
                opposite_stat = cls._stat_applied_event_stat(state_keys[0])
                if opposite_stat is None:
                    return False
                if any(
                    candidate.effect_id != state_effect.effect_id
                    and (candidate.stat or "") == opposite_stat
                    and owner in possible_ally_targets(squad, candidate)
                    for candidate in squad.effects
                ):
                    return False
        return True

'''
    s = replace_once(s, marker, helper + marker, "helper insertion")
    s = replace_once(
        s,
        '            or TriggerDispatcher._full_charge_hit_permanent_self_charge_speed_shape_supported(effect)\n'
        '            or TriggerDispatcher._charge_overflow_conversion_shape_supported(effect)\n',
        '            or TriggerDispatcher._full_charge_hit_permanent_self_charge_speed_shape_supported(effect)\n'
        '            or TriggerDispatcher._stat_applied_charge_speed_shape_supported(effect)\n'
        '            or TriggerDispatcher._charge_overflow_conversion_shape_supported(effect)\n',
        "executable shape",
    )
    s = replace_once(
        s,
        '''        for key in keys:
            if key == "event:heal_received":
                if not self.heal_received_dependency_score_safe(self.squad, effect):
                    return False
                continue
            name = key[len("event:"):]
''',
        '''        for key in keys:
            if key == "event:heal_received":
                if not self.heal_received_dependency_score_safe(self.squad, effect):
                    return False
                continue
            if self._stat_applied_event_stat(key) is not None:
                if not self.stat_applied_dependency_score_safe(self.squad, effect, key):
                    return False
                continue
            name = key[len("event:"):]
''',
        "runtime source proof",
    )
    s = replace_once(
        s,
        '''                for observer in audience:
                    self.dispatch(BurstSignal(now, f"event:{effect.name}", observer, observer))
            if stat in self._SHIELD_STATS:
''',
        '''                for observer in audience:
                    self.dispatch(BurstSignal(now, f"event:{effect.name}", observer, observer))
            stat_event_name = f"stat_applied:{stat}"
            if (
                activated_group
                and stat in _STAT_APPLIED_EVENT_STATS
                and stat_event_name in self._named_event_names_needed
            ):
                from .burst import BurstSignal
                for target in targets:
                    if target != ENEMY:
                        observer = int(target)
                        self.dispatch(
                            BurstSignal(now, f"event:{stat_event_name}", observer, observer)
                        )
            if stat in self._SHIELD_STATS:
''',
        "stat emission",
    )
    p.write_text(s, encoding="utf-8")

    p = Path("fast_engine/engine/score.py")
    s = p.read_text(encoding="utf-8")
    s = replace_once(
        s,
        '''    if effect.effect_type != "buff" or not _valid_dynamic_bullet_lifetime(effect):
        return False
    return TriggerDispatcher.is_executable_effect(effect)
''',
        '''    if effect.effect_type != "buff" or not _valid_dynamic_bullet_lifetime(effect):
        return False
    if not TriggerDispatcher.is_executable_effect(effect):
        return False
    return _named_buff_event_dependency_score_safe(squad, effect)
''',
        "dynamic charge source proof",
    )
    s = replace_once(
        s,
        '''    for key in keys:
        if key == "event:heal_received":
            if not TriggerDispatcher.heal_received_dependency_score_safe(squad, effect):
                return False
            continue
        name = key[len("event:"):]
''',
        '''    for key in keys:
        if key == "event:heal_received":
            if not TriggerDispatcher.heal_received_dependency_score_safe(squad, effect):
                return False
            continue
        if TriggerDispatcher._stat_applied_event_stat(key) is not None:
            if not TriggerDispatcher.stat_applied_dependency_score_safe(squad, effect, key):
                return False
            continue
        name = key[len("event:"):]
''',
        "score source proof",
    )
    p.write_text(s, encoding="utf-8")


def probe() -> None:
    from calculator.timeline import simulate
    from context import snapshot, spec
    from fast_engine.engine.burst import compile_burst_policy
    from fast_engine.engine.burst_runtime import BurstRuntime
    from fast_engine.engine.compiler import compile_moris_squad
    from fast_engine.engine.dispatcher import TriggerDispatcher
    from fast_engine.engine.effects import ActiveEffectStore
    from fast_engine.engine.model import CompiledSquad
    from fast_engine.engine.score import static_score_blockers
    from fast_engine.engine.target_scope import possible_ally_targets
    from fast_engine.engine.triggers import TriggerIndex

    team = "레이드_앨리스브래디"
    moris_squad = spec.build_squad(list(snapshot.SQUADS[team]["members"]))
    squad = compile_moris_squad(moris_squad)
    brady = next(i for i, member in enumerate(squad.members) if member.name == "브래디")
    stay = next(e for e in squad.members[brady].effects if e.name == "머물고 싶은 맛")
    split = next(e for e in squad.members[brady].effects if e.name == "나누고 싶은 맛")
    stay_remove = next(e for e in squad.members[brady].effects if e.name == "머물고 싶은 맛 2")
    split_remove = next(e for e in squad.members[brady].effects if e.name == "나누고 싶은 맛 2")

    assert TriggerDispatcher._stat_applied_charge_speed_shape_supported(stay)
    assert TriggerDispatcher._stat_applied_charge_speed_shape_supported(split)
    assert TriggerDispatcher.is_executable_effect(stay)
    assert TriggerDispatcher.is_executable_effect(split)
    assert not TriggerDispatcher.is_executable_effect(stay_remove)
    assert not TriggerDispatcher.is_executable_effect(split_remove)
    assert not TriggerDispatcher.stat_applied_dependency_score_safe(
        squad, stay, "event:stat_applied:dot_dmg_pct"
    )
    assert TriggerDispatcher.stat_applied_dependency_score_safe(
        squad, split, "event:stat_applied:split_dmg_pct"
    )

    blockers = set(static_score_blockers(squad))
    assert "cadence:브래디:머물고 싶은 맛:charge_speed_pct" in blockers, blockers
    assert "cadence:브래디:나누고 싶은 맛:charge_speed_pct" not in blockers, blockers

    # Opposite source existence must invalidate the immutable NOT_SELF_STATE proof.
    source = next(
        effect for effect in squad.effects
        if effect.stat == "split_dmg_pct" and brady in possible_ally_targets(squad, effect)
    )
    members = list(squad.members)
    owner_effects = tuple(
        replace(effect, stat="dot_dmg_pct") if effect.effect_id == source.effect_id else effect
        for effect in members[source.actor].effects
    )
    members[source.actor] = replace(members[source.actor], effects=owner_effects)
    all_effects = tuple(effect for member in members for effect in member.effects)
    opposite = CompiledSquad(
        tuple(members), TriggerIndex.from_effects(all_effects, actor_count=len(members))
    )
    split2 = next(e for e in opposite.members[brady].effects if e.name == "나누고 싶은 맛")
    assert not TriggerDispatcher.stat_applied_dependency_score_safe(
        opposite, split2, "event:stat_applied:split_dmg_pct"
    )

    fast_split: list[float] = []
    fast_stay: list[float] = []
    original_activate = ActiveEffectStore.activate_group

    def traced_activate(store, effect, targets, now, scheduler):
        if effect.effect_id == split.effect_id:
            fast_split.append(float(now))
        if effect.effect_id == stay.effect_id:
            fast_stay.append(float(now))
        return original_activate(store, effect, targets, now, scheduler)

    duration = 40.0
    policy = compile_burst_policy(moris_squad, squad, {"duration": duration})
    with patch.object(ActiveEffectStore, "activate_group", new=traced_activate):
        BurstRuntime(squad, policy).run(duration=duration)
    assert fast_split, "Fast split stat_applied consumer never activated"
    assert not fast_stay, fast_stay

    moris = simulate(
        moris_squad,
        config={"duration": duration, "rng_mode": "expected"},
        verbose=True,
    )
    moris_split = [float(row.t) for row in moris.log.buff_events if row.name == "나누고 싶은 맛"]
    print("FAST_SPLIT", fast_split)
    print("MORIS_SPLIT", moris_split)
    assert moris_split, "Moris split consumer trace empty"
    assert abs(fast_split[0] - moris_split[0]) < 1e-9
    assert abs(fast_split[0] - 3.2) < 1e-9
    assert len(fast_split) > 1, fast_split

    seen: set[tuple[str, ...]] = set()
    cadence = 0
    certified = 0
    matches = []
    for name, entry in snapshot.SQUADS.items():
        if name.startswith("지그_"):
            continue
        members_key = tuple(entry["members"])
        if members_key in seen:
            continue
        seen.add(members_key)
        compiled = compile_moris_squad(spec.build_squad(list(members_key)))
        rows = static_score_blockers(compiled)
        cadence += sum(row.startswith("cadence:") for row in rows)
        certified += not rows
        for effect in compiled.effects:
            if TriggerDispatcher._stat_applied_charge_speed_shape_supported(effect):
                key = effect.triggers[0].event_key or ""
                if TriggerDispatcher.stat_applied_dependency_score_safe(compiled, effect, key):
                    matches.append(
                        (name, compiled.members[effect.actor].name, effect.name, key)
                    )
    print("ACCOUNTING", len(seen), certified, cadence)
    print("CERTIFIED_STAT_APPLIED", matches)
    assert len(seen) == 23
    assert certified == 2
    assert cadence == 63
    assert {(row[1], row[2], row[3]) for row in matches} == {
        ("브래디", "나누고 싶은 맛", "event:stat_applied:split_dmg_pct")
    }


if __name__ == "__main__":
    apply_patch()
    subprocess.run(
        ["python", "-m", "py_compile", "fast_engine/engine/dispatcher.py", "fast_engine/engine/score.py"],
        check=True,
    )
    subprocess.run(["git", "diff", "--check"], check=True)
    subprocess.run(
        ["git", "diff", "--", "fast_engine/engine/dispatcher.py", "fast_engine/engine/score.py"],
        check=True,
    )
    probe()
