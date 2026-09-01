from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

from .weapon import WeaponCadenceMachine, _Accumulator, _EPS

if TYPE_CHECKING:
    from .model import CompiledEffect, CompiledSquad


_LAST_BULLET_EVENT_KEYS = frozenset({"last_bullet_fire", "last_bullet"})


@dataclass(frozen=True, slots=True)
class LastBulletBoundary:
    """One magazine-ending boundary for one exact Moris last-bullet signal."""

    time: float
    actor: int
    event_key: str


class _LastBulletCadence(WeaponCadenceMachine):
    """Reuse Fast's static weapon primitives and expose only magazine-end shots.

    This deliberately does not create every-shot events. It mirrors the three
    existing cadence paths until a magazine is exhausted and records only the
    shot that consumes the final round. Reload/charge/rate math stays owned by
    WeaponCadenceMachine's existing helpers.
    """

    def _auto_boundaries(self) -> list[float]:
        out: list[float] = []
        acc = _Accumulator()
        full = self._full_ammo()
        inter = 1.0 / self._fixed_rate()
        start = 0.0
        while start <= self.duration + _EPS:
            fit = int(math.floor((self.duration - start) / inter + _EPS)) + 1
            if fit < full:
                break
            last = start + (full - 1) * inter
            out.append(last)
            reload_probe = start + full * inter
            if reload_probe > self.duration + _EPS:
                break
            start = self._reload_cycle_after_empty(reload_probe, full, acc)
        return out

    def _charge_boundaries(self) -> list[float]:
        out: list[float] = []
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
            if fit < full:
                break
            last = first + (full - 1) * cycle
            out.append(last)
            reload_probe = last + post
            if reload_probe > self.duration + _EPS:
                break
            next_charge_start = self._reload_cycle_after_empty(reload_probe, full, acc)
            if next_charge_start > self.duration + _EPS:
                break
            first = next_charge_start + charge
        return out

    def _mg_boundaries(self) -> list[float]:
        out: list[float] = []
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
                    n = min(ammo, max(0, fit))
                    if n <= 0:
                        return out
                    last_shot = t + (n - 1) * inter
                    last_inter = inter
                    ammo -= n
                    t += n * inter
                    if ammo > 0:
                        return out
                    break
                last_shot = t
                last_inter = inter
                warmup = next_warmup
                ammo -= 1
                t += inter
            if ammo > 0:
                break
            out.append(last_shot)
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

    def boundaries(self) -> tuple[float, ...]:
        mode = str(self.weapon.get("fire_mode") or "auto")
        if mode == "auto":
            rows = self._auto_boundaries()
        elif mode == "auto_warmup":
            rows = self._mg_boundaries()
        elif mode == "charge":
            rows = self._charge_boundaries()
        else:
            raise NotImplementedError(f"Fast last-bullet cadence fire_mode={mode!r}")
        return tuple(rows)


def simulate_static_last_bullet_boundaries(
    squad: "CompiledSquad",
    *,
    duration: float,
    effect_filter: Callable[["CompiledEffect"], bool],
) -> tuple[LastBulletBoundary, ...]:
    """Return only magazine-ending boundaries observed by executable effects.

    ``last_bullet_fire`` and ``last_bullet`` share the physical magazine-ending
    timestamp but remain distinct logical signals. Moris emits the former before
    the final shot and the latter after its damage/hit notifications; callers must
    preserve that semantic distinction instead of aliasing one name to the other.
    """

    interested: dict[int, set[str]] = {}
    for effect in squad.effects:
        if not effect_filter(effect):
            continue
        keys = {
            rule.event_key
            for rule in effect.triggers
            if rule.event_key in _LAST_BULLET_EVENT_KEYS
        }
        if keys:
            interested.setdefault(effect.actor, set()).update(keys)

    out: list[LastBulletBoundary] = []
    for actor in sorted(interested):
        machine = _LastBulletCadence(actor, squad.members[actor], duration=duration)
        for t in machine.boundaries():
            out.extend(
                LastBulletBoundary(t, actor, event_key)
                for event_key in sorted(interested[actor])
            )
    out.sort(key=lambda row: (row.time, row.actor, row.event_key))
    return tuple(out)
