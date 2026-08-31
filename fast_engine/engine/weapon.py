from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Iterable, TYPE_CHECKING

from .triggers import TriggerMode

if TYPE_CHECKING:
    from .model import CompiledEffect

from .model import CompiledCharacter, CompiledSquad

_EPS = 1e-9
_FRAME_RATE_CAP = 60.0


def _round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


def _quantize(value: float, step: float) -> float:
    return _round_half_up(value / step) * step


@dataclass(frozen=True, slots=True)
class StaticCadenceModifiers:
    """Permanent, unconditional cadence modifiers known at compile time.

    This is intentionally a narrow first slice. Dynamic skill buffs remain in
    TriggerDispatcher/ActiveEffectStore and are not silently folded into this
    snapshot. The weapon runtime can later become piecewise-dynamic without
    changing the compiled weapon representation.
    """

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
        # Only permanent unconditional self effects are compile-time constants.
        # Finite/dynamic effects stay in the event runtime.
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
    """One meaningful count boundary reached by an aggregated weapon span.

    `count_increment` is the number of base events skipped since the previous
    dispatched boundary for the same actor/event key.  The dispatcher therefore
    sees the same absolute event count without receiving every bullet.
    """

    time: float
    actor: int
    event_key: str
    count_increment: int


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
                    # The first fast-forward slice is deliberately limited to
                    # reducible modulo counters.  Other count semantics stay
                    # explicit until they get their own correctness rule.
                    continue
                n = int(rule.threshold or 0)
                if n > 0:
                    thresholds.setdefault(rule.event_key, set()).add(n)
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
        self, first_t: float, count: int, *, interval: float, hits: int, full_charge: bool = False,
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
        self, t: float, *, hits: int, full_charge: bool = False, pellet_events: bool = False
    ) -> None:
        self.add_shots(
            t, 1, interval=0.0, hits=hits, full_charge=full_charge, pellet_events=pellet_events
        )


class WeaponCadenceMachine:
    """Score-only weapon timing model without a frame loop or damage objects.

    Phase-2A scope is deliberately narrow: base weapon mechanics plus permanent
    unconditional cadence modifiers. Dynamic cadence buffs, weapon changes and
    manual-control policies are explicit later gates. The point of this slice is
    to validate shot/reload/charge counts independently from damage semantics.
    """

    __slots__ = ("actor", "character", "mods", "duration", "weapon")

    def __init__(self, actor: int, character: CompiledCharacter, *, duration: float) -> None:
        self.actor = actor
        self.character = character
        self.mods = compile_static_cadence_modifiers(character)
        self.duration = float(duration)
        self.weapon = character.weapon

    def _full_ammo(self) -> int:
        base = int(self.weapon["max_ammo"])
        # First Fast approximation: permanent compile-time sources are summed,
        # then converted to bullets once. Source-by-source Moris quantization is
        # a later parity refinement if it changes ranking/shot counts materially.
        pct_gain = _round_half_up(base * self.mods.max_ammo_pct / 100.0)
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
            pellets = max(1, int(self.weapon.get("pellets", 1)) + _round_half_up(self.mods.pellet_count))
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
            # Moris discovers the empty magazine at the next scheduled fire.
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
        # Preserve the real 60fps one-shot-per-frame weapon cap without a frame loop.
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
            # Warmup is the only per-shot section. Once the 60fps weapon cap is
            # reached, the remaining magazine is one constant-rate interval.
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
            fit = int(math.floor((self.duration - first) / cycle + _EPS)) + 1 if cycle > 0 else full
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


def simulate_static_weapon_cadence(squad: CompiledSquad, *, duration: float) -> tuple[WeaponCadenceResult, ...]:
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
    """Plan only meaningful reducible weapon-count boundaries.

    The cadence pass still computes every magazine/constant-rate span, but it
    materializes scheduler events only where an executable effect can observe a
    count threshold.  This is the bridge from interval aggregation to runtime
    trigger dispatch.
    """

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
