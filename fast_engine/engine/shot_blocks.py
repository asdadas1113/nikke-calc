from __future__ import annotations

import math
from dataclasses import dataclass

from .model import CompiledSquad
from .weapon import WeaponCadenceMachine, _Accumulator, _EPS


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
            else:
                limit = time + eps if inclusive else time - eps
                if first > limit:
                    break
                take = min(
                    remaining,
                    int(math.floor((limit - first) / block.interval + eps)) + 1,
                )
            if take <= 0:
                break
            total += take
            self.shot_offset += take
            if self.shot_offset >= block.count:
                self.block_index += 1
                self.shot_offset = 0
        return total
