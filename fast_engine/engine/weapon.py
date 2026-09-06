from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Callable, Iterable, TYPE_CHECKING

from .frame_lattice import moris_next_tick, moris_observed_tick
from .scheduler import EventKind, EventScheduler, ScheduledEvent
from .triggers import TriggerMode

if TYPE_CHECKING:
    from .effects import ActiveEffectStore
    from .model import CompiledEffect
    from .state import StateStore

from .model import CompiledCharacter, CompiledSquad

_EPS = 1e-9
_FRAME_RATE_CAP = 60.0

_CERTIFIED_AUTO_WEAPON_CHANGE_DEFAULTS = {
    "SMG": {
        "fire_mode": "auto",
        "fire_rate": 24.0,
        "fire_rate_max": None,
        "warmup_bullets": 1.0,
        "warmup_cooldown_time": 1.0,
        "post_fire_delay": 0.0,
        "post_reload_delay": 0.0,
        "reload_start_delay": 0.0,
        "cover_during_delay": False,
        "charge_time": 0.0,
        "pellets": 1,
        "muzzles": 1,
        "is_clip": False,
        "normal_hit_coeff": 1.0,
        "core_base_diameter": 110.0,
        "core_acc_slope": 1.0,
        "core_model_n": 2.55,
        "control": {},
    },
}


def is_supported_charge_hold_control(member) -> bool:
    """Certify the first sparse pure charge-hold control shape.

    The supported shape is a non-clip charge weapon with exactly one control:
    ``hold.policy == own_full_burst`` and an optional non-negative ``lead``.
    Mixed controls (tap-fire/cover/reload/sequence) stay fail-closed. The
    separate score-safety gate owns ``cover_during_delay`` reachability.
    """

    weapon = member.weapon
    if str(weapon.get("fire_mode") or "") != "charge":
        return False
    if weapon.get("is_clip"):
        return False
    control = weapon.get("control") or {}
    if not isinstance(control, dict) or set(control) != {"hold"}:
        return False
    hold = control.get("hold")
    if not isinstance(hold, dict) or hold.get("policy") != "own_full_burst":
        return False
    if set(hold) - {"policy", "lead"}:
        return False
    try:
        lead = float(hold.get("lead", 0.5))
    except (TypeError, ValueError):
        return False
    return lead >= 0.0


def is_supported_charge_reload_cancel_control(member) -> bool:
    """Certify pure non-clip charge ``reload.cancel_on_full`` control.

    Mixed charge controls and any additional reload policy remain fail-closed.
    """

    weapon = member.weapon
    if str(weapon.get("fire_mode") or "") != "charge":
        return False
    if weapon.get("is_clip"):
        return False
    control = weapon.get("control") or {}
    if not isinstance(control, dict) or set(control) != {"reload"}:
        return False
    reload_control = control.get("reload")
    return (
        isinstance(reload_control, dict)
        and set(reload_control) == {"cancel_on_full"}
        and reload_control.get("cancel_on_full") is True
    )


def _round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


def _quantize(value: float, step: float) -> float:
    return _round_half_up(value / step) * step


@dataclass(frozen=True, slots=True)
class StaticCadenceModifiers:
    """Permanent, unconditional cadence modifiers known at compile time."""

    max_ammo_pct: float = 0.0
    max_ammo_flat: float = 0.0
    reload_speed_pct: float = 0.0
    charge_speed_pct: float = 0.0
    charge_time_flat: float = 0.0
    attack_speed_pct: float = 0.0
    mg_warmup_speed_pct: float = 0.0
    pellet_count: float = 0.0
    pellet_count_fixed: float = 0.0


_STATIC_STATS = frozenset(StaticCadenceModifiers.__dataclass_fields__)


def compile_static_cadence_modifiers(character: CompiledCharacter) -> StaticCadenceModifiers:
    values = {name: 0.0 for name in _STATIC_STATS}
    for effect in character.effects:
        if effect.effect_type != "buff" or effect.stat not in _STATIC_STATS:
            continue
        if effect.target != "self" or effect.condition_rules:
            continue
        if effect.duration not in (None, -1):
            continue
        if not any(rule.event_key == "battle_start" for rule in effect.triggers):
            continue
        values[effect.stat] += float(effect.value or 0.0)
    return StaticCadenceModifiers(**values)


@dataclass(frozen=True, slots=True)
class WeaponTriggerBoundary:
    """One meaningful count boundary reached by an aggregated weapon span."""

    time: float
    actor: int
    event_key: str
    count_increment: int


def reducible_threshold_candidates(
    effect: "CompiledEffect", all_effects, base: int
) -> tuple[int, ...]:
    """Return sparse modulo boundaries for one exact-name count reducer.

    This slice is deliberately narrow: one same-actor finite self buff may reduce
    one exact named hit_count effect by a positive integer. Runtime still decides
    whether the reducer is active at each candidate crossing.
    """
    values = {int(base)}
    if base <= 0 or not effect.name:
        return tuple(sorted(values))
    reducers = []
    for other in all_effects:
        if not (
            other.actor == effect.actor
            and other.effect_type == "buff"
            and (other.stat or "") == "trigger_count_reduce"
            and other.target_spec.mode.value == "self"
            and other.parameters.get("target_effect") == effect.name
            and set(other.parameters) == {"target_effect"}
            and other.value is not None
            and float(other.value) > 0.0
            and float(other.value).is_integer()
            and other.duration is not None
            and float(other.duration) > 0.0
            and other.max_stack in (None, 1, 1.0)
            and all(rule.is_runtime_supported for rule in other.condition_rules)
            and bool(other.triggers)
        ):
            continue
        reducers.append(other)
    if len(reducers) == 1:
        values.add(max(1, int(base) - int(float(reducers[0].value))))
    return tuple(sorted(values))


class _WeaponBoundaryCollector:
    __slots__ = ("actor", "thresholds", "totals", "dispatched", "boundaries")

    def __init__(self, actor: int, thresholds: dict[str, tuple[int, ...]]) -> None:
        self.actor = actor
        self.thresholds = thresholds
        self.totals: dict[str, int] = {}
        self.dispatched: dict[str, int] = {}
        self.boundaries: list[WeaponTriggerBoundary] = []

    @classmethod
    def from_character(
        cls,
        actor: int,
        character: CompiledCharacter,
        *,
        effect_filter: Callable[["CompiledEffect"], bool],
    ) -> "_WeaponBoundaryCollector":
        thresholds: dict[str, set[int]] = {}
        for effect in character.effects:
            if not effect_filter(effect):
                continue
            for rule in effect.triggers:
                if rule.event_key not in {"hit_count", "full_charge_hit", "pellet_hit"}:
                    continue
                if rule.mode is not TriggerMode.MODULO or not rule.trigger_count_reducible:
                    continue
                n = int(rule.threshold or 0)
                if n > 0:
                    thresholds.setdefault(rule.event_key, set()).update(
                        reducible_threshold_candidates(effect, character.effects, n)
                    )
        return cls(actor, {key: tuple(sorted(values)) for key, values in thresholds.items()})

    def add_block(
        self,
        event_key: str,
        first_t: float,
        shot_count: int,
        shot_interval: float,
        *,
        events_per_shot: int = 1,
    ) -> None:
        if shot_count <= 0 or events_per_shot <= 0:
            return
        rules = self.thresholds.get(event_key)
        if not rules:
            return
        before = self.totals.get(event_key, 0)
        after = before + shot_count * events_per_shot
        crossings: set[int] = set()
        for threshold in rules:
            value = ((before // threshold) + 1) * threshold
            while value <= after:
                crossings.add(value)
                value += threshold
        last_dispatched = self.dispatched.get(event_key, 0)
        for absolute_count in sorted(crossings):
            ordinal = absolute_count - before - 1
            shot_index = ordinal // events_per_shot
            t = first_t + shot_index * shot_interval
            self.boundaries.append(
                WeaponTriggerBoundary(
                    time=t,
                    actor=self.actor,
                    event_key=event_key,
                    count_increment=absolute_count - last_dispatched,
                )
            )
            last_dispatched = absolute_count
        self.totals[event_key] = after
        self.dispatched[event_key] = last_dispatched


@dataclass(frozen=True, slots=True)
class WeaponCadenceResult:
    actor: int
    shots: int
    hit_events: int
    ammo_consumed: int
    full_charge_hits: int
    reload_starts: int
    reload_completions: int
    last_bullet_fire: int
    last_bullet: int
    first_shot: float | None
    last_shot: float | None


@dataclass(slots=True)
class _Accumulator:
    collector: _WeaponBoundaryCollector | None = None
    shots: int = 0
    hit_events: int = 0
    ammo_consumed: int = 0
    full_charge_hits: int = 0
    reload_starts: int = 0
    reload_completions: int = 0
    last_bullet_fire: int = 0
    last_bullet: int = 0
    first_shot: float | None = None
    last_shot: float | None = None

    def add_shots(
        self,
        first_t: float,
        count: int,
        *,
        interval: float,
        hits: int,
        full_charge: bool = False,
        pellet_events: bool = False,
    ) -> None:
        if count <= 0:
            return
        self.shots += count
        self.hit_events += hits * count
        self.ammo_consumed += count
        if full_charge:
            self.full_charge_hits += count
        if self.collector is not None:
            self.collector.add_block("hit_count", first_t, count, interval)
            if full_charge:
                self.collector.add_block("full_charge_hit", first_t, count, interval)
            if pellet_events:
                self.collector.add_block(
                    "pellet_hit", first_t, count, interval, events_per_shot=hits
                )
        if self.first_shot is None:
            self.first_shot = first_t
        self.last_shot = first_t + (count - 1) * interval

    def shot(
        self,
        t: float,
        *,
        hits: int,
        full_charge: bool = False,
        pellet_events: bool = False,
    ) -> None:
        self.add_shots(
            t,
            1,
            interval=0.0,
            hits=hits,
            full_charge=full_charge,
            pellet_events=pellet_events,
        )


class WeaponCadenceMachine:
    """Score-only static weapon timing model without a frame loop."""

    __slots__ = ("actor", "character", "mods", "duration", "weapon")

    def __init__(self, actor: int, character: CompiledCharacter, *, duration: float) -> None:
        self.actor = actor
        self.character = character
        self.mods = compile_static_cadence_modifiers(character)
        self.duration = float(duration)
        self.weapon = character.weapon

    def _full_ammo(self) -> int:
        base = int(self.weapon["max_ammo"])
        # Moris quantizes permanent max-ammo percentage sources separately before
        # adding them. Aggregating equipment + collection percentages first can
        # move the magazine by one bullet at half-step boundaries.
        pct_gain = 0
        for effect in self.character.effects:
            if effect.effect_type != "buff" or effect.stat != "max_ammo_pct":
                continue
            if effect.target != "self" or effect.condition_rules:
                continue
            if effect.duration not in (None, -1):
                continue
            if not any(rule.event_key == "battle_start" for rule in effect.triggers):
                continue
            pct_gain += _round_half_up(
                base * float(effect.value or 0.0) / 100.0
            )
        flat = _round_half_up(self.mods.max_ammo_flat)
        return max(1, base + pct_gain + flat)

    def _reload_factor(self) -> float:
        return max(0.0, 1.0 - self.mods.reload_speed_pct / 100.0)

    def _reload_duration_from_empty(self, full: int) -> float:
        one = float(self.weapon["reload_time"]) * self._reload_factor()
        if not self.weapon.get("is_clip"):
            return one
        gain = max(1, _round_half_up(full / 3.0))
        clips = max(1, math.ceil(full / gain))
        return one * clips

    def _reload_cycle_after_empty(self, t: float, full: int, acc: _Accumulator) -> float:
        factor = self._reload_factor()
        acc.reload_starts += 1
        finish = (
            t
            + float(self.weapon.get("reload_start_delay", 0.0)) * factor
            + self._reload_duration_from_empty(full)
        )
        if finish <= self.duration + _EPS:
            acc.reload_completions += 1
        return finish + float(self.weapon.get("post_reload_delay", 0.0)) * factor

    def _hits_per_shot(self) -> int:
        fixed = self.mods.pellet_count_fixed
        if fixed > 0:
            pellets = max(1, _round_half_up(fixed))
        else:
            pellets = max(
                1,
                int(self.weapon.get("pellets", 1)) + _round_half_up(self.mods.pellet_count),
            )
        return pellets * max(1, int(self.weapon.get("muzzles", 1)))

    def _fixed_rate(self) -> float:
        base = float(self.weapon["fire_rate"])
        return max(0.01, base * max(0.01, 1.0 + self.mods.attack_speed_pct / 100.0))

    def _run_auto(self, acc: _Accumulator) -> None:
        full = self._full_ammo()
        hits = self._hits_per_shot()
        rate = self._fixed_rate()
        inter = 1.0 / rate
        start = 0.0
        while start <= self.duration + _EPS:
            fit = int(math.floor((self.duration - start) / inter + _EPS)) + 1
            if fit <= 0:
                break
            n = min(full, fit)
            acc.add_shots(start, n, interval=inter, hits=hits, pellet_events=True)
            if n < full:
                break
            acc.last_bullet_fire += 1
            acc.last_bullet += 1
            reload_probe = start + full * inter
            if reload_probe > self.duration + _EPS:
                break
            start = self._reload_cycle_after_empty(reload_probe, full, acc)

    def _mg_rate(self, warmup: float) -> float:
        fr_min = float(self.weapon["fire_rate"])
        fr_max = float(self.weapon.get("fire_rate_max") or fr_min)
        cap = float(self.weapon.get("warmup_bullets") or 1.0)
        base = fr_min + (fr_max - fr_min) * min(warmup, cap) / cap
        rate = base * max(0.01, 1.0 + self.mods.attack_speed_pct / 100.0)
        return min(_FRAME_RATE_CAP, max(0.01, rate))

    def _run_mg(self, acc: _Accumulator) -> None:
        full = self._full_ammo()
        hits = self._hits_per_shot()
        warmup = 0.0
        cap = float(self.weapon.get("warmup_bullets") or 1.0)
        warm_inc = max(0.0, 1.0 + self.mods.mg_warmup_speed_pct / 100.0)
        cooldown_time = max(float(self.weapon.get("warmup_cooldown_time") or 1.0), 1e-9)
        cool_rate = cap / cooldown_time
        t = 0.0
        last_shot = -999.0
        last_inter = 0.0
        ammo = full
        while t <= self.duration + _EPS:
            while ammo > 0 and t <= self.duration + _EPS:
                rate = self._mg_rate(warmup)
                inter = 1.0 / rate
                next_warmup = min(cap, warmup + warm_inc)
                next_rate = self._mg_rate(next_warmup)
                if abs(next_rate - rate) <= 1e-12:
                    fit = int(math.floor((self.duration - t) / inter + _EPS)) + 1
                    n = min(ammo, max(0, fit))
                    acc.add_shots(t, n, interval=inter, hits=hits, pellet_events=True)
                    if n <= 0:
                        return
                    last_shot = t + (n - 1) * inter
                    last_inter = inter
                    ammo -= n
                    t += n * inter
                    break
                acc.shot(t, hits=hits, pellet_events=True)
                last_shot = t
                last_inter = inter
                warmup = next_warmup
                ammo -= 1
                t += inter
            if ammo > 0 or t > self.duration + _EPS:
                break
            acc.last_bullet_fire += 1
            acc.last_bullet += 1
            reload_probe = t
            if reload_probe > self.duration + _EPS:
                break
            next_start = self._reload_cycle_after_empty(reload_probe, full, acc)
            if next_start > self.duration + _EPS:
                break
            idle = next_start - last_shot
            if idle > last_inter * 1.5:
                warmup = max(0.0, warmup - cool_rate * idle)
            t = next_start
            ammo = full

    def _effective_charge_time(self) -> float:
        base = float(self.weapon.get("charge_time") or 0.0)
        cut = _quantize(base * self.mods.charge_speed_pct / 100.0, 0.01)
        return max(0.0, max(0.0, base - cut) + self.mods.charge_time_flat)

    def _run_charge(self, acc: _Accumulator) -> None:
        full = self._full_ammo()
        hits = self._hits_per_shot()
        charge = self._effective_charge_time()
        post = float(self.weapon.get("post_fire_delay", 0.0))
        cycle = charge + post
        first = charge
        while first <= self.duration + _EPS:
            fit = (
                int(math.floor((self.duration - first) / cycle + _EPS)) + 1
                if cycle > 0
                else full
            )
            n = min(full, max(0, fit))
            acc.add_shots(first, n, interval=cycle, hits=hits, full_charge=True)
            if n < full:
                break
            acc.last_bullet_fire += 1
            acc.last_bullet += 1
            last = first + (full - 1) * cycle
            reload_probe = last + post
            if reload_probe > self.duration + _EPS:
                break
            next_charge_start = self._reload_cycle_after_empty(reload_probe, full, acc)
            if next_charge_start > self.duration + _EPS:
                break
            first = next_charge_start + charge

    def run(
        self, *, collector: _WeaponBoundaryCollector | None = None
    ) -> WeaponCadenceResult:
        acc = _Accumulator(collector=collector)
        mode = str(self.weapon.get("fire_mode") or "auto")
        if mode == "auto":
            self._run_auto(acc)
        elif mode == "auto_warmup":
            self._run_mg(acc)
        elif mode == "charge":
            self._run_charge(acc)
        else:
            raise NotImplementedError(f"Fast weapon cadence fire_mode={mode!r}")
        return WeaponCadenceResult(
            actor=self.actor,
            shots=acc.shots,
            hit_events=acc.hit_events,
            ammo_consumed=acc.ammo_consumed,
            full_charge_hits=acc.full_charge_hits,
            reload_starts=acc.reload_starts,
            reload_completions=acc.reload_completions,
            last_bullet_fire=acc.last_bullet_fire,
            last_bullet=acc.last_bullet,
            first_shot=acc.first_shot,
            last_shot=acc.last_shot,
        )


def simulate_static_weapon_cadence(
    squad: CompiledSquad, *, duration: float
) -> tuple[WeaponCadenceResult, ...]:
    return tuple(
        WeaponCadenceMachine(actor, character, duration=duration).run()
        for actor, character in enumerate(squad.members)
    )


def simulate_static_weapon_trigger_boundaries(
    squad: CompiledSquad,
    *,
    duration: float,
    effect_filter: Callable[["CompiledEffect"], bool],
) -> tuple[WeaponTriggerBoundary, ...]:
    out: list[WeaponTriggerBoundary] = []
    for actor, character in enumerate(squad.members):
        collector = _WeaponBoundaryCollector.from_character(
            actor, character, effect_filter=effect_filter
        )
        if not collector.thresholds:
            continue
        WeaponCadenceMachine(actor, character, duration=duration).run(collector=collector)
        out.extend(collector.boundaries)
    out.sort(key=lambda row: (row.time, row.actor, row.event_key))
    return tuple(out)


# ── Dynamic charge-cadence slice ──────────────────────────────────────────

@dataclass(slots=True)
class _ChargeActorState:
    actor: int
    ammo: int
    phase: str
    phase_end: float
    charge_start: float
    weapon_change_id: int | None = None
    pending_weapon_change_refill: bool = False
    full_charge_count: int = 0
    dispatched_count: int = 0
    generation: int = 0
    scheduled_time: float | None = None
    signature: tuple[float, ...] | None = None
    charge_latched: bool = False


@dataclass(frozen=True, slots=True)
class DynamicWeaponToken:
    actor: int
    generation: int
    expected_full_charge_count: int


class DynamicChargeCadenceRuntime:
    """Piecewise SR/RL cadence planner exposing only meaningful boundaries.

    State-changing Fast events invalidate one actor's future plan by generation.
    Ordinary full-charge shots stay inside this runtime unless a reducible
    full-charge counter or the auxiliary squad-body-hit bridge can observe them.
    """

    __slots__ = (
        "squad", "effects", "state", "scheduler", "duration", "effect_filter",
        "actors", "emits_each_charge_hit", "_thresholds", "_states",
    )

    def __init__(
        self,
        squad: CompiledSquad,
        effects: "ActiveEffectStore",
        state: "StateStore",
        scheduler: EventScheduler,
        *,
        duration: float,
        effect_filter: Callable[["CompiledEffect"], bool],
    ) -> None:
        self.squad = squad
        self.effects = effects
        self.state = state
        self.scheduler = scheduler
        self.duration = float(duration)
        self.effect_filter = effect_filter

        thresholds: dict[int, tuple[int, ...]] = {}
        for actor, character in enumerate(squad.members):
            vals: set[int] = set()
            for effect in character.effects:
                if not effect_filter(effect):
                    continue
                for rule in effect.triggers:
                    if (
                        rule.event_key == "full_charge_hit"
                        and rule.mode is TriggerMode.MODULO
                        and rule.trigger_count_reducible
                    ):
                        n = int(rule.threshold or 0)
                        if n > 0:
                            vals.add(n)
            if vals:
                thresholds[actor] = tuple(sorted(vals))

        self.emits_each_charge_hit = any(
            effect_filter(effect)
            and any(rule.event_key == "squad_body_hit" for rule in effect.triggers)
            for effect in squad.effects
        )
        self.actors = tuple(
            actor
            for actor, member in enumerate(squad.members)
            if str(member.weapon.get("fire_mode") or "") == "charge"
            and (actor in thresholds or self.emits_each_charge_hit)
        )
        self._thresholds = thresholds
        self._states: dict[int, _ChargeActorState] = {}

    def _active_sum(self, actor: int, stat: str, now: float) -> float:
        return self.effects.sum_stat(actor, stat, now=now)

    def _active_weapon_change(self, actor: int, now: float):
        return self.effects.active_effect_of_type(actor, "weapon_change", now=now)

    def _weapon_change_id(self, actor: int, now: float) -> int | None:
        row = self._active_weapon_change(actor, now)
        return None if row is None else int(row[0].effect_id)

    def effective_weapon(self, actor: int, now: float):
        base = self.squad.members[actor].weapon
        row = self._active_weapon_change(actor, now)
        if row is None:
            return base
        effect, _active = row
        params = effect.parameters
        weapon = dict(base)
        changed_type = str(params.get("weapon_type") or weapon.get("weapon_type") or "")
        base_type = str(base.get("weapon_type") or "")
        defaults = _CERTIFIED_AUTO_WEAPON_CHANGE_DEFAULTS.get(changed_type)
        if changed_type != base_type and defaults is not None:
            weapon.update(defaults)
            weapon["weapon_type"] = changed_type
            weapon["_moris_frame_observed"] = True
            weapon["_weapon_change_effect_id"] = int(effect.effect_id)
        for key in (
            "weapon_type", "damage_coeff", "max_ammo", "full_charge_mult",
            "post_fire_delay", "cover_during_delay",
        ):
            if key in params:
                weapon[key] = params[key]
        if "reload_seconds" in params:
            weapon["reload_time"] = float(params["reload_seconds"])
        elif "reload_time" in params:
            weapon["reload_time"] = float(params["reload_time"])
        if "charge_seconds" in params:
            weapon["charge_time"] = float(params["charge_seconds"])
        elif "charge_time" in params:
            weapon["charge_time"] = float(params["charge_time"])
        return weapon

    def _caster_based_charge_speed(self, actor: int, now: float) -> float:
        target_base = float(self.effective_weapon(actor, now).get("charge_time") or 0.0)
        if target_base <= _EPS:
            return 0.0
        total = 0.0
        for effect, active in self.effects.iter_stat(
            "charge_speed_caster_based_pct", now=now
        ):
            if active.target != actor:
                continue
            caster_base = float(
                self.effective_weapon(active.source_actor, now).get("charge_time") or 0.0
            )
            total += (
                caster_base
                * float(effect.value or 0.0)
                * active.stacks
                / target_base
            )
        return total

    def _signature(self, actor: int, now: float) -> tuple[float, ...]:
        wc_id = self._weapon_change_id(actor, now)
        return (
            float(-1 if wc_id is None else wc_id),
            self._active_sum(actor, "max_ammo_pct", now),
            self._active_sum(actor, "max_ammo_flat", now),
            self._active_sum(actor, "reload_speed_pct", now),
            self._active_sum(actor, "charge_speed_pct", now)
            + self._caster_based_charge_speed(actor, now),
            self._active_sum(actor, "charge_time_flat", now),
        )

    def _full_ammo(self, actor: int, now: float) -> int:
        weapon = self.effective_weapon(actor, now)
        base = int(weapon["max_ammo"])
        if base < 0:
            return 999999
        pct = self._active_sum(actor, "max_ammo_pct", now)
        flat = self._active_sum(actor, "max_ammo_flat", now)
        return max(
            1,
            base
            + _round_half_up(base * pct / 100.0)
            + _round_half_up(flat),
        )

    def _reload_factor(self, actor: int, now: float) -> float:
        return max(0.0, 1.0 - self._active_sum(actor, "reload_speed_pct", now) / 100.0)

    def _reload_duration_from_empty(self, actor: int, now: float) -> float:
        weapon = self.effective_weapon(actor, now)
        factor = self._reload_factor(actor, now)
        one = float(weapon["reload_time"]) * factor
        if not weapon.get("is_clip"):
            return one
        full = self._full_ammo(actor, now)
        gain = max(1, _round_half_up(full / 3.0))
        clips = max(1, math.ceil(full / gain))
        return one * clips

    def _effective_charge_time(self, actor: int, now: float) -> float:
        weapon = self.effective_weapon(actor, now)
        base = float(weapon.get("charge_time") or 0.0)
        speed = (
            self._active_sum(actor, "charge_speed_pct", now)
            + self._caster_based_charge_speed(actor, now)
        )
        cut = _quantize(base * speed / 100.0, 0.01)
        flat = self._active_sum(actor, "charge_time_flat", now)
        return max(0.0, max(0.0, base - cut) + flat)

    def _shot_is_boundary(self, actor: int, absolute_count: int) -> bool:
        if self.emits_each_charge_hit:
            return True
        return any(
            absolute_count % threshold == 0
            for threshold in self._thresholds.get(actor, ())
        )

    def _observe_phase_boundary(self, deadline: float) -> float:
        return moris_observed_tick(deadline, horizon=self.duration)

    def _next_outer_tick(self, after: float) -> float:
        return moris_next_tick(after, horizon=self.duration)

    def _charge_shot_release_time(self, actor: int, ready_time: float) -> float:
        return float(ready_time)

    def _latch_charge_until_release(self, st: _ChargeActorState, ready_time: float) -> bool:
        if st.charge_latched:
            return False
        release = self._charge_shot_release_time(st.actor, ready_time)
        if release <= ready_time + _EPS:
            return False
        st.charge_latched = True
        st.phase_end = self._observe_phase_boundary(release)
        return True

    def _enter_charge(self, st: _ChargeActorState, at: float, now_for_mods: float) -> None:
        st.phase = "charging"
        st.charge_start = at
        st.charge_latched = False
        st.phase_end = self._observe_phase_boundary(
            at + self._effective_charge_time(st.actor, now_for_mods)
        )

    def _after_shot(self, st: _ChargeActorState, shot_time: float) -> None:
        st.charge_latched = False
        st.ammo -= 1
        st.full_charge_count += 1
        st.phase = "post_fire_reload" if st.ammo <= 0 else "post_fire"
        if st.pending_weapon_change_refill and st.ammo <= 0:
            st.phase = "post_fire"
        st.phase_end = self._observe_phase_boundary(
            shot_time
            + float(
                self.effective_weapon(st.actor, shot_time).get("post_fire_delay", 0.0)
            )
        )

    def _finish_nonshot_phase(
        self, st: _ChargeActorState, transition_time: float, now_for_mods: float
    ) -> None:
        actor = st.actor
        weapon = self.effective_weapon(actor, now_for_mods)
        if st.phase == "post_fire":
            if st.pending_weapon_change_refill and st.ammo <= 0:
                st.phase = "post_reload"
                st.phase_end = self._next_outer_tick(transition_time)
            else:
                self._enter_charge(st, transition_time, now_for_mods)
            return
        if st.phase == "post_fire_reload":
            factor = self._reload_factor(actor, now_for_mods)
            st.phase = "reloading"
            st.phase_end = self._observe_phase_boundary(
                transition_time
                + float(weapon.get("reload_start_delay", 0.0)) * factor
                + self._reload_duration_from_empty(actor, now_for_mods)
            )
            return
        if st.phase == "reloading":
            st.ammo = self._full_ammo(actor, now_for_mods)
            factor = self._reload_factor(actor, now_for_mods)
            delay = float(weapon.get("post_reload_delay", 0.0)) * factor
            if delay > _EPS:
                st.phase = "post_reload"
                st.phase_end = self._observe_phase_boundary(transition_time + delay)
            else:
                self._enter_charge(st, transition_time, now_for_mods)
            return
        if st.phase == "post_reload":
            if st.pending_weapon_change_refill:
                st.ammo = self._full_ammo(actor, now_for_mods)
                st.pending_weapon_change_refill = False
            self._enter_charge(st, transition_time, now_for_mods)
            return
        raise RuntimeError(f"unexpected dynamic charge phase: {st.phase!r}")

    def _advance_actor_to(
        self, actor: int, t: float, *, inclusive: bool
    ) -> None:
        st = self._states[actor]
        while True:
            due = st.phase_end <= t + _EPS if inclusive else st.phase_end < t - _EPS
            if not due:
                return
            when = st.phase_end
            if when > self.duration + _EPS:
                return
            if st.phase == "charging":
                if self._latch_charge_until_release(st, when):
                    continue
                next_count = st.full_charge_count + 1
                if self._shot_is_boundary(actor, next_count):
                    # A meaningful shot belongs to the global scheduler.
                    return
                self._after_shot(st, when)
                continue
            self._finish_nonshot_phase(st, when, when)

    def advance_to(self, t: float, *, inclusive: bool = False) -> None:
        for actor in self.actors:
            self._advance_actor_to(actor, t, inclusive=inclusive)

    def _predict_next_boundary(
        self, actor: int, now: float
    ) -> tuple[float, int] | None:
        src = self._states[actor]
        st = replace(src)
        # Prediction assumes cadence state is unchanged until the next global
        # event. Any real state mutation calls sync() and invalidates this plan.
        while st.phase_end <= self.duration + _EPS:
            when = st.phase_end
            if st.phase == "charging":
                if self._latch_charge_until_release(st, when):
                    continue
                next_count = st.full_charge_count + 1
                if self._shot_is_boundary(actor, next_count):
                    return when, next_count
                self._after_shot(st, when)
                continue
            self._finish_nonshot_phase(st, when, now)
        return None

    def _invalidate(self, st: _ChargeActorState) -> None:
        st.generation += 1
        st.scheduled_time = None

    def _plan(self, actor: int, now: float) -> None:
        st = self._states[actor]
        if st.scheduled_time is not None:
            return
        row = self._predict_next_boundary(actor, now)
        if row is None:
            return
        when, expected = row
        when = max(float(now), float(when))
        if when > self.duration + _EPS:
            return
        st.generation += 1
        st.scheduled_time = when
        self.scheduler.schedule(
            when,
            EventKind.WEAPON_BOUNDARY,
            actor=actor,
            payload=DynamicWeaponToken(actor, st.generation, expected),
        )

    def start(self, now: float = 0.0) -> None:
        for actor in self.actors:
            full = self._full_ammo(actor, now)
            charge = self._effective_charge_time(actor, now)
            st = _ChargeActorState(
                actor=actor,
                ammo=full,
                phase="charging",
                phase_end=self._observe_phase_boundary(float(now) + charge),
                charge_start=float(now),
                weapon_change_id=self._weapon_change_id(actor, now),
                signature=self._signature(actor, now),
            )
            self._states[actor] = st
            self.state.set_ammo(actor, full)
            self._plan(actor, now)

    def sync(self, now: float) -> None:
        for actor in self.actors:
            st = self._states[actor]
            while st.phase != "charging" and st.phase_end <= now + _EPS:
                self._finish_nonshot_phase(st, st.phase_end, now)

            current_wc_id = self._weapon_change_id(actor, now)
            wc_changed = current_wc_id != st.weapon_change_id
            if wc_changed:
                entering = current_wc_id is not None
                inherited_magazine = (
                    entering and st.phase in {"charging", "post_fire"} and st.ammo > 0
                )
                st.weapon_change_id = current_wc_id
                self._invalidate(st)
                if inherited_magazine:
                    st.pending_weapon_change_refill = True
                else:
                    st.pending_weapon_change_refill = False
                    st.ammo = self._full_ammo(actor, now)

                if entering and st.phase == "charging":
                    st.charge_start = float(now)
                    st.phase_end = self._observe_phase_boundary(
                        float(now) + self._effective_charge_time(actor, now)
                    )
                elif st.phase in {"post_fire_reload", "reloading", "post_reload"}:
                    self._enter_charge(st, float(now), float(now))
                elif not entering and st.phase == "charging":
                    st.phase_end = self._observe_phase_boundary(
                        st.charge_start + self._effective_charge_time(actor, now)
                    )

            old_signature = st.signature
            signature = self._signature(actor, now)
            if signature != old_signature:
                st.signature = signature
                if not wc_changed:
                    self._invalidate(st)
                    if (
                        st.phase == "charging"
                        and not st.charge_latched
                        and old_signature is not None
                        and (signature[4], signature[5])
                        != (old_signature[4], old_signature[5])
                    ):
                        st.phase_end = self._observe_phase_boundary(
                            st.charge_start + self._effective_charge_time(actor, now)
                        )
            if st.scheduled_time is None:
                self._plan(actor, now)
            self.state.set_ammo(actor, st.ammo)

    def handle_boundary(
        self, event: ScheduledEvent
    ) -> tuple[int, str, int] | None:
        token = event.payload
        if not isinstance(token, DynamicWeaponToken):
            return None
        st = self._states.get(token.actor)
        if st is None:
            return None
        if token.generation != st.generation:
            return None
        if st.scheduled_time is None or abs(st.scheduled_time - event.time) > 1e-7:
            return None

        # Keep every actor current to immediately before this global boundary.
        self.advance_to(event.time, inclusive=False)
        st = self._states[token.actor]
        while st.phase != "charging" and st.phase_end <= event.time + _EPS:
            self._finish_nonshot_phase(st, st.phase_end, event.time)
        if st.phase != "charging" or st.phase_end > event.time + 1e-7:
            return None

        next_count = st.full_charge_count + 1
        if next_count != token.expected_full_charge_count:
            return None
        self._after_shot(st, event.time)
        st.scheduled_time = None
        increment = st.full_charge_count - st.dispatched_count
        st.dispatched_count = st.full_charge_count
        self.state.set_ammo(token.actor, st.ammo)
        return token.actor, "full_charge_hit", increment
