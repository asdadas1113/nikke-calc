from __future__ import annotations

import math
from dataclasses import dataclass

from .model import CompiledSquad
from .weapon import (
    StaticCadenceModifiers,
    WeaponCadenceMachine,
    _Accumulator,
    _EPS,
)


@dataclass(frozen=True, slots=True)
class ShotBlock:
    actor: int
    first_time: float
    count: int
    interval: float

    @property
    def last_time(self) -> float:
        return self.first_time + max(0, self.count - 1) * self.interval


class _BlockBuilder(WeaponCadenceMachine):
    __slots__ = ()

    def _append(self, out: list[ShotBlock], first: float, count: int, interval: float) -> None:
        if count <= 0:
            return
        out.append(ShotBlock(self.actor, first, count, interval))

    def _auto(self) -> list[ShotBlock]:
        out: list[ShotBlock] = []
        acc = _Accumulator()
        full = self._full_ammo()
        inter = 1.0 / self._fixed_rate()
        start = 0.0
        while start <= self.duration + _EPS:
            fit = int(math.floor((self.duration - start) / inter + _EPS)) + 1
            if fit <= 0:
                break
            count = min(full, fit)
            self._append(out, start, count, inter)
            if count < full:
                break
            reload_probe = start + full * inter
            if reload_probe > self.duration + _EPS:
                break
            start = self._reload_cycle_after_empty(reload_probe, full, acc)
        return out

    def _charge(self) -> list[ShotBlock]:
        out: list[ShotBlock] = []
        acc = _Accumulator()
        full = self._full_ammo()
        charge = self._effective_charge_time()
        post = float(self.weapon.get("post_fire_delay", 0.0))
        cycle = charge + post
        first = charge
        while first <= self.duration + _EPS:
            fit = (
                int(math.floor((self.duration - first) / cycle + _EPS)) + 1
                if cycle > 0.0
                else full
            )
            count = min(full, max(0, fit))
            self._append(out, first, count, cycle)
            if count < full:
                break
            last = first + (full - 1) * cycle
            reload_probe = last + post
            if reload_probe > self.duration + _EPS:
                break
            next_charge_start = self._reload_cycle_after_empty(reload_probe, full, acc)
            if next_charge_start > self.duration + _EPS:
                break
            first = next_charge_start + charge
        return out

    def _mg(self) -> list[ShotBlock]:
        out: list[ShotBlock] = []
        acc = _Accumulator()
        full = self._full_ammo()
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
                    count = min(ammo, max(0, fit))
                    if count <= 0:
                        return out
                    self._append(out, t, count, inter)
                    last_shot = t + (count - 1) * inter
                    last_inter = inter
                    ammo -= count
                    t += count * inter
                    break
                self._append(out, t, 1, inter)
                last_shot = t
                last_inter = inter
                warmup = next_warmup
                ammo -= 1
                t += inter

            if ammo > 0 or t > self.duration + _EPS:
                break
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
        return out

    def blocks(self) -> tuple[ShotBlock, ...]:
        mode = str(self.weapon.get("fire_mode") or "auto")
        if mode == "auto":
            rows = self._auto()
        elif mode == "auto_warmup":
            rows = self._mg()
        elif mode == "charge":
            rows = self._charge()
        else:
            raise NotImplementedError(f"Fast shot block fire_mode={mode!r}")
        return tuple(rows)


# A bullet-count lifetime can only be lowered to one future shot boundary while
# the recipient's cadence is static. These are the same families that can move
# physical shot timestamps or change how many ammo-consuming shots occur.
_BULLET_LIFETIME_CADENCE_STATS = frozenset({
    "reload_speed_pct",
    "max_ammo_pct",
    "max_ammo_flat",
    "max_ammo_infinite",
    "ammo_charge_flat",
    "ammo_charge_pct",
    "charge_speed_pct",
    "charge_speed_caster_based_pct",
    "charge_time_flat",
    "charge_time_fixed",
    "attack_speed_pct",
    "mg_warmup_speed_pct",
})
_STATIC_FOLDABLE = frozenset(StaticCadenceModifiers.__dataclass_fields__)


def _is_folded_static_self_modifier(effect) -> bool:
    return (
        (effect.stat or "") in _STATIC_FOLDABLE
        and effect.effect_type == "buff"
        and effect.target_spec.mode.value == "self"
        and effect.duration in (None, -1.0)
        and not effect.condition_rules
        and bool(effect.triggers)
        and all(rule.event_key == "battle_start" for rule in effect.triggers)
    )


def static_bullet_lifetime_cadence_safe(squad: CompiledSquad, actor: int) -> bool:
    """Whether a recipient has a stable static shot plan for bullet expiry.

    The check is intentionally conservative. Any live cadence/weapon mutation in
    the squad keeps duration_bullets fail-closed; permanent unconditional self
    modifiers are safe because WeaponCadenceMachine already folds them into the
    static plan. Manual control is also rejected because it changes whether a
    nominal shot is actually fired.
    """

    if actor < 0 or actor >= len(squad.members):
        return False
    if squad.members[actor].weapon.get("control"):
        return False
    for effect in squad.effects:
        if effect.effect_type == "weapon_change":
            return False
        if (effect.stat or "") not in _BULLET_LIFETIME_CADENCE_STATS:
            continue
        if not _is_folded_static_self_modifier(effect):
            return False
    return True


class _NextShotFinder(WeaponCadenceMachine):
    """Find one future shot without expanding the timeline or requiring a horizon."""

    __slots__ = ()

    def _next_auto(self, after: float) -> float:
        acc = _Accumulator()
        full = self._full_ammo()
        inter = 1.0 / self._fixed_rate()
        start = 0.0
        while True:
            if start > after + _EPS:
                return start
            offset = max(0, int(math.floor((after - start) / inter + _EPS)) + 1)
            if offset < full:
                return start + offset * inter
            start = self._reload_cycle_after_empty(start + full * inter, full, acc)

    def _next_charge(self, after: float) -> float:
        acc = _Accumulator()
        full = self._full_ammo()
        charge = self._effective_charge_time()
        post = float(self.weapon.get("post_fire_delay", 0.0))
        cycle = charge + post
        if cycle <= 0.0:
            raise NotImplementedError("Fast duration_bullets zero charge cycle not certified")
        first = charge
        while True:
            if first > after + _EPS:
                return first
            offset = max(0, int(math.floor((after - first) / cycle + _EPS)) + 1)
            if offset < full:
                return first + offset * cycle
            last = first + (full - 1) * cycle
            next_charge_start = self._reload_cycle_after_empty(last + post, full, acc)
            first = next_charge_start + charge

    def _next_mg(self, after: float) -> float:
        acc = _Accumulator()
        full = self._full_ammo()
        warmup = 0.0
        cap = float(self.weapon.get("warmup_bullets") or 1.0)
        warm_inc = max(0.0, 1.0 + self.mods.mg_warmup_speed_pct / 100.0)
        cooldown_time = max(float(self.weapon.get("warmup_cooldown_time") or 1.0), 1e-9)
        cool_rate = cap / cooldown_time
        t = 0.0
        last_shot = -999.0
        last_inter = 0.0
        ammo = full

        while True:
            while ammo > 0:
                rate = self._mg_rate(warmup)
                inter = 1.0 / rate
                if t > after + _EPS:
                    return t
                next_warmup = min(cap, warmup + warm_inc)
                next_rate = self._mg_rate(next_warmup)
                if abs(next_rate - rate) <= 1e-12:
                    last = t + (ammo - 1) * inter
                    if last > after + _EPS:
                        offset = max(
                            0,
                            int(math.floor((after - t) / inter + _EPS)) + 1,
                        )
                        if offset < ammo:
                            return t + offset * inter
                    last_shot = last
                    last_inter = inter
                    t += ammo * inter
                    ammo = 0
                    break
                last_shot = t
                last_inter = inter
                warmup = next_warmup
                ammo -= 1
                t += inter

            next_start = self._reload_cycle_after_empty(t, full, acc)
            idle = next_start - last_shot
            if idle > last_inter * 1.5:
                warmup = max(0.0, warmup - cool_rate * idle)
            t = next_start
            ammo = full

    def next_after(self, after: float) -> float:
        mode = str(self.weapon.get("fire_mode") or "auto")
        if mode == "auto":
            return self._next_auto(after)
        if mode == "auto_warmup":
            return self._next_mg(after)
        if mode == "charge":
            return self._next_charge(after)
        raise NotImplementedError(f"Fast duration_bullets fire_mode={mode!r}")


def next_static_shot_after(squad: CompiledSquad, actor: int, time: float) -> float:
    """Return the first ammo-consuming static shot strictly after ``time``."""

    if not static_bullet_lifetime_cadence_safe(squad, actor):
        name = squad.members[actor].name if 0 <= actor < len(squad.members) else str(actor)
        raise NotImplementedError(
            "Fast duration_bullets static cadence not certified for " + name
        )
    finder = _NextShotFinder(actor, squad.members[actor], duration=math.inf)
    return finder.next_after(float(time))


def compile_static_shot_blocks(
    squad: CompiledSquad, *, duration: float
) -> tuple[tuple[ShotBlock, ...], ...]:
    return tuple(
        _BlockBuilder(actor, character, duration=duration).blocks()
        for actor, character in enumerate(squad.members)
    )


class ShotBlockCursor:
    """Consume compressed shot timestamps without expanding them into objects."""

    __slots__ = ("blocks", "block_index", "shot_offset")

    def __init__(self, blocks: tuple[ShotBlock, ...]) -> None:
        self.blocks = blocks
        self.block_index = 0
        self.shot_offset = 0

    def consume_until(self, time: float, *, inclusive: bool) -> int:
        """Consume shots ``<= time`` or strictly ``< time``.

        The exclusive path deliberately uses a ceil formulation instead of
        subtracting epsilon and then feeding that value through the inclusive
        floor formula.  The latter can add epsilon twice and accidentally pull
        an exactly-equal shot across the boundary (e.g. t=3.0 into ``<3.0``),
        which would make hit-triggered buffs retroactively affect their own shot.
        """

        total = 0
        eps = 1e-9
        while self.block_index < len(self.blocks):
            block = self.blocks[self.block_index]
            remaining = block.count - self.shot_offset
            if remaining <= 0:
                self.block_index += 1
                self.shot_offset = 0
                continue

            first = block.first_time + self.shot_offset * block.interval
            if block.interval <= 0.0:
                due = first <= time + eps if inclusive else first < time - eps
                if not due:
                    break
                take = remaining
            elif inclusive:
                if first > time + eps:
                    break
                relative = (time - first) / block.interval
                take = min(
                    remaining,
                    max(0, int(math.floor(relative + eps)) + 1),
                )
            else:
                if first >= time - eps:
                    break
                relative = (time - first) / block.interval
                # Number of integer offsets i >= 0 satisfying i < relative.
                take = min(
                    remaining,
                    max(0, int(math.ceil(relative - eps))),
                )

            if take <= 0:
                break
            total += take
            self.shot_offset += take
            if self.shot_offset >= block.count:
                self.block_index += 1
                self.shot_offset = 0
        return total
