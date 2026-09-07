from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence, TYPE_CHECKING

from .dynamic_rapid import DynamicRapidCadenceRuntime
from .frame_lattice import moris_observed_tick
from .scheduler import EventScheduler, ScheduledEvent
from .state import StateStore
from .triggers import TriggerMode
from .weapon import (
    DynamicChargeCadenceRuntime,
    is_supported_charge_hold_control,
    is_supported_charge_reload_cancel_control,
)

if TYPE_CHECKING:
    from .effects import ActiveEffectStore
    from .model import CompiledEffect, CompiledSquad


_INTERNAL_BULLET_CONSUME_EVENT = "__fast_consume_dynamic_bullet_lifetime__"


@dataclass(frozen=True, slots=True)
class DynamicCountSignal:
    event_key: str
    count_increment: int


@dataclass(frozen=True, slots=True)
class DynamicChargeBoundary:
    actor: int
    signals: tuple[DynamicCountSignal, ...]
    is_last_bullet: bool = False
    pre_signals: tuple[DynamicCountSignal, ...] = ()
    score_pending: bool = False


class MultiSignalChargeCadenceRuntime(DynamicChargeCadenceRuntime):
    """Composite dynamic weapon runtime for the currently certified slices.

    Charge weapons keep the existing generation-based SR/RL cadence runtime.
    Selected non-clip auto/MG actors use a compressed rapid cadence runtime that
    supports live reload speed and the first exact player-control interval
    (``cover.policy == own_full_burst``). The two paths share the scheduler but
    never share actor state: charge actors remain in the base runtime while rapid
    actors live in ``_rapid_reload``.

    Score callbacks run after a physical shot has advanced ammo state but before
    post-shot hit/full-charge/last-bullet effects are dispatched. This preserves
    Moris' damage-before-hit-notify ordering without introducing a frame loop.
    """

    __slots__ = (
        "_hit_thresholds",
        "_raw_full_charge_actors",
        "_raw_on_attack_actors",
        "_score_actors",
        "_score_shot_sink",
        "_rapid_reload",
        "_charge_hold_release",
        "_mode_only_charge_actors",
        "_mode_only_single_charge_actors",
        "_mode_only_weapon_change_ids",
        "_external_weapon_block_until",
    )

    def __init__(
        self,
        squad: "CompiledSquad",
        effects: "ActiveEffectStore",
        state: StateStore,
        scheduler: EventScheduler,
        *,
        duration: float,
        effect_filter: Callable[["CompiledEffect"], bool],
    ) -> None:
        super().__init__(
            squad,
            effects,
            state,
            scheduler,
            duration=duration,
            effect_filter=effect_filter,
        )

        hit_thresholds: dict[int, tuple[int, ...]] = {}
        raw_full_charge_actors: set[int] = set()
        raw_on_attack_actors: set[int] = set()
        for actor, character in enumerate(squad.members):
            values: set[int] = set()
            for effect in character.effects:
                if not effect_filter(effect):
                    continue
                for rule in effect.triggers:
                    if (
                        rule.event_key == "hit_count"
                        and rule.mode is TriggerMode.MODULO
                        and rule.trigger_count_reducible
                    ):
                        threshold = int(rule.threshold or 0)
                        if threshold > 0:
                            values.add(threshold)
                    if (
                        rule.event_key == "full_charge_hit"
                        and rule.mode is TriggerMode.EVENT
                    ):
                        raw_full_charge_actors.add(actor)
                    if (
                        rule.event_key == "on_attack"
                        and rule.mode is TriggerMode.EVENT
                    ):
                        raw_on_attack_actors.add(actor)
            if values:
                hit_thresholds[actor] = tuple(sorted(values))

        mode_only_ids={}
        single_charge_actors=set()
        for effect in squad.effects:
            member=squad.members[effect.actor]
            params=effect.parameters
            if not (
                effect.effect_type == "weapon_change"
                and effect_filter(effect)
                and str(member.weapon.get("fire_mode") or "") == "auto"
            ):
                continue
            skill_mode=(
                params.get("weapon_type") in {"SR","RL"}
                and params.get("skill_damage") is True
            )
            single_mode=(
                params.get("weapon_type") == "SR"
                and params.get("max_ammo") == 1
                and params.get("duration_bullets") == 1
                and "skill_damage" not in params
            )
            if not (skill_mode or single_mode):
                continue
            mode_only_ids[effect.actor]=effect.effect_id
            if single_mode:
                single_charge_actors.add(effect.actor)
        self._mode_only_charge_actors=frozenset(mode_only_ids)
        self._mode_only_single_charge_actors=frozenset(single_charge_actors)
        self._mode_only_weapon_change_ids=dict(mode_only_ids)
        self._external_weapon_block_until=None
        if self._mode_only_charge_actors:
            self.attach_mode_only_charge_actors(self._mode_only_charge_actors)

        interesting = set(hit_thresholds) | raw_full_charge_actors | raw_on_attack_actors
        for actor in interesting:
            character = squad.members[actor]
            if (
                str(character.weapon.get("fire_mode") or "") != "charge"
                and actor not in self._mode_only_charge_actors
            ):
                if actor in raw_full_charge_actors:
                    raise NotImplementedError(
                        "Fast raw full_charge_hit consumer on non-charge weapon is not certified: "
                        + character.name
                    )
                if actor in raw_on_attack_actors:
                    raise NotImplementedError(
                        "Fast raw on_attack consumer on non-charge weapon is not certified: "
                        + character.name
                    )

        self._hit_thresholds = hit_thresholds
        self._raw_full_charge_actors = frozenset(raw_full_charge_actors)
        self._raw_on_attack_actors = frozenset(raw_on_attack_actors)
        self._score_actors: frozenset[int] = frozenset()
        self._score_shot_sink: Callable[[int, float], None] | None = None
        self._charge_hold_release: dict[int, float] = {}
        self._rapid_reload = DynamicRapidCadenceRuntime(
            squad,
            effects,
            state,
            scheduler,
            duration=duration,
            effect_filter=effect_filter,
        )
        rapid_weapon_change_actors = frozenset(
            effect.actor
            for effect in squad.effects
            if effect.effect_type == "weapon_change"
            and effect_filter(effect)
            and str(squad.members[effect.actor].weapon.get("fire_mode") or "")
            in {"auto", "auto_warmup"}
            and effect.parameters.get("weapon_type") == "SMG"
        )
        if rapid_weapon_change_actors:
            self._rapid_reload.attach_effective_weapon(
                self.effective_weapon, rapid_weapon_change_actors
            )

        actors = set(self.actors)
        for actor in interesting:
            if str(squad.members[actor].weapon.get("fire_mode") or "") == "charge":
                actors.add(actor)
        self.actors = tuple(sorted(actors))

    @property
    def all_dynamic_actors(self) -> tuple[int, ...]:
        return tuple(sorted(set(self.actors) | set(self._rapid_reload.actors)))

    def attach_score_shot_sink(
        self,
        actors: tuple[int, ...] | frozenset[int],
        sink: Callable[[int, float], None],
    ) -> None:
        if self._states:
            raise RuntimeError("Fast score shot sink must be attached before weapon start")
        selected = frozenset(int(actor) for actor in actors)
        for actor in selected:
            if actor < 0 or actor >= len(self.squad.members):
                raise IndexError(f"actor out of range: {actor}")
            if (
                str(self.squad.members[actor].weapon.get("fire_mode") or "") != "charge"
                and actor not in self._mode_only_charge_actors
            ):
                raise NotImplementedError(
                    "Fast dynamic score shot sink only supports charge or owned mode-only weapons: "
                    + self.squad.members[actor].name
                )
        # Charge duration_bullets must be registered before battle-start
        # activation so ActiveEffectStore does not schedule a stale static
        # Nth-shot expiry. Rapid registration is additive in the store.
        self.effects.enable_dynamic_bullet_lifetime_targets(selected)
        self._score_actors = selected
        self._score_shot_sink = sink
        if selected:
            self.actors = tuple(sorted(set(self.actors) | set(selected)))

    def attach_score_block_sink(
        self,
        actors: tuple[int, ...] | frozenset[int],
        sink: Callable[[int, int, float], None],
    ) -> None:
        self._rapid_reload.attach_score_sink(actors, sink)

    def _combined_weapon_block_until(self, actor: int, now: float) -> float | None:
        until = (
            None if self._external_weapon_block_until is None
            else self._external_weapon_block_until(actor,now)
        )
        effect_id=self._mode_only_weapon_change_ids.get(actor)
        if effect_id is not None:
            row=self.effects.active_effect_of_type(actor,"weapon_change",now=now)
            if row is not None and int(row[0].effect_id) == int(effect_id):
                expires=row[1].expires_at
                if expires is not None:
                    until=float(expires) if until is None else max(float(until),float(expires))
        return until

    def attach_weapon_block_until(
        self, callback: Callable[[int, float], float | None]
    ) -> None:
        self._external_weapon_block_until=callback
        self._rapid_reload.attach_weapon_block_until(self._combined_weapon_block_until)

    def is_skill_weapon_mode(self, actor: int, now: float) -> bool:
        effect_id=self._mode_only_weapon_change_ids.get(int(actor))
        if effect_id is None:
            return False
        row=self.effects.active_effect_of_type(int(actor),"weapon_change",now=float(now))
        return (
            row is not None
            and int(row[0].effect_id) == int(effect_id)
            and row[0].parameters.get("skill_damage") is True
        )

    def attach_squad_ammo_thresholds(self, thresholds: tuple[int, ...]) -> None:
        self._rapid_reload.attach_squad_ammo_thresholds(thresholds)

    def refresh_squad_ammo_plan(self, now: float) -> None:
        self._rapid_reload.refresh_squad_ammo_plan(now)

    def handle_pre_shot_boundary(self, event: ScheduledEvent) -> DynamicChargeBoundary | None:
        row=self._rapid_reload.handle_pre_shot_boundary(event)
        if row is None:
            return None
        return DynamicChargeBoundary(
            row.actor,
            tuple(DynamicCountSignal(x.event_key,x.count_increment) for x in row.signals),
            is_last_bullet=row.is_last_bullet,
            pre_signals=tuple(DynamicCountSignal(x.event_key,x.count_increment) for x in row.pre_signals),
            score_pending=row.score_pending,
        )

    def score_pending_shot(self, actor: int, now: float) -> None:
        self._rapid_reload.score_pending_shot(actor,now)

    def _charge_shot_release_time(self, actor: int, ready_time: float) -> float:
        release = float(self._charge_hold_release.get(actor, -1.0))
        return release if ready_time < release - 1e-9 else float(ready_time)

    def begin_full_burst(
        self,
        now: float,
        casted: Sequence[bool],
        full_burst_end: float,
    ) -> tuple[int, ...]:
        entered = set(self._rapid_reload.begin_full_burst(now, casted, full_burst_end))
        for actor in self.actors:
            if actor >= len(casted) or not casted[actor]:
                continue
            member = self.squad.members[actor]
            if not is_supported_charge_hold_control(member):
                continue
            hold = member.weapon["control"]["hold"]
            lead = float(hold.get("lead", 0.5))
            release = self._observe_phase_boundary(float(full_burst_end) - lead)
            if release <= now + 1e-9:
                continue
            self._advance_actor_to(actor, now, inclusive=False)
            st = self._states[actor]
            self._charge_hold_release[actor] = release
            self._invalidate(st)
            self._plan(actor, now)
            entered.add(actor)
        return tuple(sorted(entered))

    @staticmethod
    def _ammo_charge_gain(full: int, stat: str, value: float) -> int:
        if stat == "ammo_charge_pct":
            # Moris uses Python round() on final effective maximum ammo.
            return int(round(float(full) * float(value) / 100.0))
        if stat == "ammo_charge_flat":
            return int(value)
        raise ValueError(f"unsupported ammo charge stat: {stat}")

    def apply_ammo_charge(
        self,
        stat: str,
        targets: tuple[int, ...],
        value: float,
        now: float,
    ) -> bool:
        """Apply an instant ammo refill to dynamic weapon state.

        All recipients are validated before mutation. Pure charge
        ``reload.cancel_on_full`` cancels only an active reload filled to full.
        """

        if value < 0.0:
            return False
        selected = tuple(dict.fromkeys(int(actor) for actor in targets))
        dynamic = set(self.all_dynamic_actors)
        if not selected or any(actor not in dynamic for actor in selected):
            return False

        # Bring every selected actor to immediately before the instant effect.
        # BurstRuntime already does this globally, but keeping it local makes the
        # callback safe for direct tests and future non-burst instant sources.
        self.advance_to(float(now), inclusive=False)

        rapid_changed = False
        for actor in selected:
            if actor in self._rapid_reload.actors:
                rapid_changed = True
                runtime = self._rapid_reload
                st = runtime._states.get(actor)
                if st is None:
                    return False
                full = runtime._full_ammo(actor, float(now))
                gain = self._ammo_charge_gain(full, stat, value)
                st.ammo = min(full, st.ammo + gain)
                if st.phase == "reload_wait" and st.ammo > 0:
                    # The empty-magazine probe has not started reloading yet.
                    # Refilled ammo therefore preserves that next fire probe.
                    st.phase = "firing"
                    st.phase_end = max(float(now), st.phase_end)
                runtime._invalidate(st)
                runtime._plan(actor, float(now))
                self.state.set_ammo(actor, st.ammo)
                continue

            st = self._states.get(actor)
            if st is None:
                return False
            full = self._full_ammo(actor, float(now))
            gain = self._ammo_charge_gain(full, stat, value)
            st.ammo = min(full, st.ammo + gain)
            if (
                st.phase == "reloading"
                and st.ammo >= full
                and is_supported_charge_reload_cancel_control(self.squad.members[actor])
            ):
                # Moris keeps the refill, cancels the active reload without
                # full_reload/post-reload semantics, and may charge immediately.
                self._enter_charge(st, float(now), float(now))
            elif st.phase == "post_fire_reload" and st.ammo > 0:
                # Refill arrived after the last shot but before reload start.
                # Keep the existing post-fire boundary, then charge again.
                st.phase = "post_fire"
            self._invalidate(st)
            self._plan(actor, float(now))
            self.state.set_ammo(actor, st.ammo)
        if rapid_changed:
            self._rapid_reload.refresh_squad_ammo_plan(float(now))
        return True

    def apply_force_reload(self, targets: tuple[int, ...], now: float) -> bool:
        return self._rapid_reload.apply_force_reload(targets, now)

    def consume_post_shot_bullet_lifetimes(self, actor: int, now: float) -> tuple[int, ...]:
        return self._rapid_reload.consume_post_shot_bullet_lifetimes(actor, now)

    def emits_every_charge_shot(self, actor: int) -> bool:
        return actor in self.actors and (
            self.emits_each_charge_hit
            or actor in self._raw_full_charge_actors
            or actor in self._raw_on_attack_actors
            or actor in self._score_actors
        )

    def supports_dynamic_last_bullet(self, actor: int) -> bool:
        if actor in self._rapid_reload.actors:
            return actor in self._rapid_reload._last_bullet_actors
        return self.emits_every_charge_shot(actor)

    def emits_squad_body_hit(self, actor: int) -> bool:
        return actor in self.actors and self.emits_each_charge_hit

    def _shot_is_boundary(self, actor: int, absolute_count: int) -> bool:
        if (
            actor in self._score_actors
            or actor in self._raw_full_charge_actors
            or actor in self._raw_on_attack_actors
        ):
            return True
        if super()._shot_is_boundary(actor, absolute_count):
            return True
        return any(
            absolute_count % threshold == 0
            for threshold in self._hit_thresholds.get(actor, ())
        )

    def start(self, now: float = 0.0) -> None:
        super().start(now)
        self._rapid_reload.start(now)

    def advance_to(self, t: float, *, inclusive: bool = False) -> None:
        super().advance_to(t, inclusive=inclusive)
        self._rapid_reload.advance_to(t, inclusive=inclusive)

    def sync(self, now: float) -> None:
        was_active={
            actor: (self._states.get(actor) is not None and self._states[actor].weapon_change_id is not None)
            for actor in self._mode_only_charge_actors
        }
        super().sync(now)
        for actor,active_before in was_active.items():
            active_after=(
                self._states.get(actor) is not None
                and self._states[actor].weapon_change_id is not None
            )
            if (
                not active_before
                and active_after
                and actor in self._mode_only_single_charge_actors
            ):
                st=self._states[actor]
                source_tick=moris_observed_tick(
                    float(now), horizon=self.duration, epsilon=1e-9
                )
                st.charge_start=source_tick
                st.phase_end=self._observe_phase_boundary(
                    source_tick + self._effective_charge_time(actor,float(now))
                )
                self._invalidate(st)
                self._plan(actor,float(now))
            if active_before and not active_after and actor in self._rapid_reload.actors:
                if actor in self._mode_only_single_charge_actors:
                    self._rapid_reload.resume_after_single_charge(actor,float(now))
                else:
                    self._rapid_reload.resume_with_live_full_magazine(actor,float(now))
        self._rapid_reload.sync(now)
        for actor in self._mode_only_charge_actors:
            if self.is_skill_weapon_mode(actor,now) and actor in self._states:
                self.state.set_ammo(actor,self._states[actor].ammo)

    def handle_boundary(self, event: ScheduledEvent) -> DynamicChargeBoundary | None:
        rapid = self._rapid_reload.handle_boundary(event)
        if rapid is not None:
            signals = [
                DynamicCountSignal(row.event_key, row.count_increment)
                for row in rapid.signals
            ]
            if self._rapid_reload.effects.has_dynamic_bullet_lifetime(
                rapid.actor, now=float(event.time)
            ):
                # BurstRuntime dispatches boundary signals in tuple order. This
                # internal signal therefore runs after pellet/hit_count effects,
                # matching Moris consume_bullet_buffs, and before rapid
                # last_bullet (which remains fail-closed in this slice).
                signals.append(DynamicCountSignal(_INTERNAL_BULLET_CONSUME_EVENT, 1))
            return DynamicChargeBoundary(
                rapid.actor,
                tuple(signals),
                is_last_bullet=rapid.is_last_bullet,
                pre_signals=tuple(
                    DynamicCountSignal(row.event_key,row.count_increment)
                    for row in rapid.pre_signals
                ),
                score_pending=rapid.score_pending,
            )

        row = super().handle_boundary(event)
        if row is None:
            return None
        actor, _base_event_key, count_increment = row

        if actor in self._score_actors:
            if self._score_shot_sink is None:
                raise RuntimeError("Fast dynamic score actor has no shot sink")
            self._score_shot_sink(actor, float(event.time))

        signals: list[DynamicCountSignal] = []
        if actor in self._mode_only_charge_actors:
            # Moris skill-weapon shots still consume one physical squad-ammo count
            # before their post-shot full-charge consumers.
            signals.append(DynamicCountSignal("squad_ammo_consume",1))
        if actor in self._thresholds or actor in self._raw_full_charge_actors:
            signals.append(DynamicCountSignal("full_charge_hit", count_increment))
        if actor in self._hit_thresholds:
            signals.append(DynamicCountSignal("hit_count", count_increment))
        if actor in self._raw_on_attack_actors:
            signals.append(DynamicCountSignal("on_attack", 1))
        if (
            not self.is_skill_weapon_mode(actor, float(event.time))
            and self.effects.has_dynamic_bullet_lifetime(actor, now=float(event.time))
        ):
            # Ordinary charge shots consume duration_bullets after their damage
            # and post-shot signals. Skill-weapon shots remain excluded.
            signals.append(DynamicCountSignal(_INTERNAL_BULLET_CONSUME_EVENT, 1))
        return DynamicChargeBoundary(
            actor,
            tuple(signals),
            is_last_bullet=self._states[actor].ammo <= 0,
        )
