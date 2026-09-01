from __future__ import annotations

from dataclasses import dataclass

from .burst import BurstMachine, BurstPolicy
from .conditions import SignalContext
from .dispatcher import TriggerDispatcher
from .dynamic_weapon import MultiSignalChargeCadenceRuntime
from .last_bullet import simulate_static_last_bullet_boundaries
from .model import CompiledSquad, EnemyStaticProfile
from .scheduler import EventKind, EventScheduler
from .state import StateStore
from .triggers import TriggerMode
from .weapon_events import simulate_weapon_trigger_boundaries


@dataclass(frozen=True, slots=True)
class BurstRuntimeResult:
    full_burst_starts: tuple[float, ...]
    full_burst_ends: tuple[float, ...]
    casts: tuple[tuple[float, int, str], ...]
    events_processed: int


@dataclass(frozen=True, slots=True)
class PeriodicTickToken:
    effect_id: int
    rule_index: int
    interval: float


class BurstRuntime:
    """Current vertical slice: generic Fast trigger dispatch + burst scheduler."""

    __slots__ = (
        "squad", "enemy", "policy", "scheduler", "state", "machine",
        "dispatcher", "weapons",
    )

    _STATIC_LAST_BULLET_INVALIDATORS = frozenset({
        "reload_speed_pct",
        "max_ammo_pct",
        "max_ammo_flat",
    })

    def __init__(
        self,
        squad: CompiledSquad,
        policy: BurstPolicy,
        enemy: EnemyStaticProfile | None = None,
    ) -> None:
        self.squad = squad
        self.enemy = enemy or EnemyStaticProfile(duration=policy.duration)
        self.policy = policy
        self.scheduler = EventScheduler()
        self.state = StateStore.from_compiled_squad(squad)
        self.machine = BurstMachine(squad, policy)
        self.dispatcher = TriggerDispatcher(
            squad, self.state, self.enemy, self.machine, self.scheduler
        )
        self.weapons = MultiSignalChargeCadenceRuntime(
            squad,
            self.dispatcher.effects,
            self.state,
            self.scheduler,
            duration=policy.duration,
            effect_filter=self.dispatcher.is_executable_effect,
        )

    def _broadcast(self, time: float, event_key: str) -> None:
        from .burst import BurstSignal
        for owner in range(len(self.squad.members)):
            self.dispatcher.dispatch(BurstSignal(time, event_key, owner, owner))

    def _schedule_initial_periodics(self, horizon: float) -> None:
        effect_table = tuple(self.squad.effects)
        for indexed in self.squad.trigger_index.periodic:
            effect = effect_table[indexed.effect_id]
            if not self.dispatcher.can_activate_effect(effect):
                continue
            rule = effect.triggers[indexed.rule_index]
            if rule.mode is not TriggerMode.PERIODIC or rule.interval is None:
                continue
            interval = float(rule.interval)
            if interval <= 0.0 or interval > horizon + 1e-9:
                continue
            # Moris initializes every:Ns at t=interval, not battle_start.
            self.scheduler.schedule(
                interval,
                EventKind.PERIODIC_TICK,
                actor=effect.actor,
                payload=PeriodicTickToken(
                    effect.effect_id, indexed.rule_index, interval
                ),
            )

    @staticmethod
    def _is_static_permanent_self_cadence(effect) -> bool:
        """Match the permanent self modifiers already folded into static cadence."""
        return (
            effect.effect_type == "buff"
            and effect.target_spec.mode.value == "self"
            and effect.duration in (None, -1.0)
            and not effect.condition_rules
            and bool(effect.triggers)
            and all(rule.event_key == "battle_start" for rule in effect.triggers)
        )

    @staticmethod
    def _effect_may_target_actor(effect, actor: int) -> bool:
        mode = effect.target_spec.mode.value
        if mode == "self":
            return effect.actor == actor
        if mode == "named_actor":
            return effect.target_spec.count == actor
        if mode in {"enemy", "model_excluded", "unsupported"}:
            return False
        # Dynamic ranks/filters are intentionally conservative: if the cohort can
        # change later, static last-bullet planning must assume this actor may enter it.
        return True

    def _schedule_static_last_bullets(
        self, horizon: float, dynamic_actors: set[int]
    ) -> None:
        """Expose exact magazine-ending shots without widening to every weapon hit.

        Static actors are safe only while their reload/max-ammo cadence cannot be
        changed by live effects. Dynamic charge actors and potentially-targeting
        runtime cadence modifiers fail closed instead of leaving stale magazine
        boundaries in the scheduler.
        """
        interested = {
            effect.actor
            for effect in self.squad.effects
            if self.dispatcher.is_executable_effect(effect)
            and any(rule.event_key == "last_bullet_fire" for rule in effect.triggers)
        }
        if not interested:
            return

        unsupported = interested & dynamic_actors
        if unsupported:
            names = ", ".join(self.squad.members[actor].name for actor in sorted(unsupported))
            raise NotImplementedError(
                "Fast dynamic charge + last_bullet_fire boundary not certified: " + names
            )

        invalidators: list[tuple[int, str]] = []
        for effect in self.squad.effects:
            if not self.dispatcher.is_executable_effect(effect):
                continue
            if (effect.stat or "") not in self._STATIC_LAST_BULLET_INVALIDATORS:
                continue
            if self._is_static_permanent_self_cadence(effect):
                continue
            for actor in interested:
                if self._effect_may_target_actor(effect, actor):
                    invalidators.append((actor, effect.name or effect.stat or "?"))

        if invalidators:
            detail = ", ".join(
                f"{self.squad.members[actor].name}<-{name}"
                for actor, name in invalidators[:8]
            )
            raise NotImplementedError(
                "Fast static last_bullet_fire cadence can be invalidated by live weapon modifiers: "
                + detail
            )

        from .burst import BurstSignal
        for boundary in simulate_static_last_bullet_boundaries(
            self.squad,
            duration=horizon,
            effect_filter=self.dispatcher.is_executable_effect,
        ):
            self.scheduler.schedule(
                boundary.time,
                EventKind.TRIGGER_BOUNDARY,
                actor=boundary.actor,
                payload=BurstSignal(
                    boundary.time,
                    "last_bullet_fire",
                    boundary.actor,
                    boundary.actor,
                ),
            )

    def start(self, *, duration: float | None = None) -> None:
        self._broadcast(0.0, "battle_start")
        self.machine.start(self.scheduler)
        horizon = (
            self.policy.duration
            if duration is None
            else min(float(duration), self.policy.duration)
        )
        self.weapons.start(0.0)
        dynamic_actors = set(self.weapons.actors)
        from .burst import BurstSignal
        for boundary in simulate_weapon_trigger_boundaries(
            self.squad,
            duration=horizon,
            effect_filter=self.dispatcher.is_executable_effect,
        ):
            if boundary.actor in dynamic_actors:
                continue
            self.scheduler.schedule(
                boundary.time,
                EventKind.TRIGGER_BOUNDARY,
                actor=boundary.actor,
                payload=BurstSignal(
                    boundary.time,
                    boundary.event_key,
                    boundary.actor,
                    boundary.actor,
                    count_increment=boundary.count_increment,
                ),
            )
        self._schedule_static_last_bullets(horizon, dynamic_actors)
        self._schedule_initial_periodics(horizon)

    def run(self, *, duration: float | None = None) -> BurstRuntimeResult:
        horizon = (
            self.policy.duration
            if duration is None
            else min(float(duration), self.policy.duration)
        )
        self.start(duration=horizon)
        fb_starts: list[float] = []
        casts: list[tuple[float, int, str]] = []
        fb_ends: list[float] = []
        processed = 0
        while self.scheduler and (self.scheduler.peek_time() or 0.0) <= horizon + 1e-9:
            event = self.scheduler.pop()
            processed += 1

            if event.kind is EventKind.WEAPON_BOUNDARY:
                boundary = self.weapons.handle_boundary(event)
                if boundary is not None:
                    from .burst import BurstSignal
                    for count_signal in boundary.signals:
                        self.dispatcher.dispatch(
                            BurstSignal(
                                event.time,
                                count_signal.event_key,
                                boundary.actor,
                                boundary.actor,
                                count_increment=count_signal.count_increment,
                            ),
                            context=SignalContext(),
                        )
                    if self.weapons.emits_each_charge_hit:
                        self.dispatcher.dispatch_team_hit(
                            "squad_body_hit",
                            time=event.time,
                            attacker=boundary.actor,
                            context=SignalContext(),
                            count_increment=1,
                        )
                    self.weapons.sync(event.time)
                continue

            self.weapons.advance_to(event.time, inclusive=False)

            if event.kind is EventKind.STATE_EXPIRE:
                self.dispatcher.handle_expiry(event)
                self.weapons.sync(event.time)
                continue

            if event.kind is EventKind.PERIODIC_TICK:
                token = event.payload
                if not isinstance(token, PeriodicTickToken):
                    continue
                self.dispatcher.dispatch_periodic(
                    token.effect_id,
                    token.rule_index,
                    time=event.time,
                    context=SignalContext(),
                )
                next_t = event.time + token.interval
                if next_t <= horizon + 1e-9:
                    self.scheduler.schedule(
                        next_t,
                        EventKind.PERIODIC_TICK,
                        actor=event.actor,
                        payload=token,
                    )
                self.weapons.sync(event.time)
                continue

            if event.kind is EventKind.TRIGGER_BOUNDARY:
                self.dispatcher.dispatch(event.payload, context=SignalContext())
                self.weapons.sync(event.time)
                continue

            extension = 0.0
            if event.kind is EventKind.FULL_BURST_START:
                extension = self.dispatcher.full_burst_extension(
                    event.time, self.machine.full_burst_caster
                )
            signals = self.machine.handle(
                event,
                self.scheduler,
                full_burst_extension=extension,
                cooldown_buff_provider=self.dispatcher.burst_cooldown_buff,
            )
            for signal in signals:
                if signal.event_key == "burst_cast" and signal.source_actor is not None:
                    casts.append(
                        (signal.time, signal.source_actor, signal.stage or "")
                    )
                self.dispatcher.dispatch(signal, context=SignalContext())
            if event.kind is EventKind.FULL_BURST_START:
                fb_starts.append(event.time)
                for actor in range(len(self.squad.members)):
                    self.machine.reconcile_persistent_cooldown(
                        actor,
                        self.dispatcher.burst_cooldown_buff(actor, event.time),
                        event.time,
                        self.scheduler,
                    )
            elif event.kind is EventKind.FULL_BURST_END:
                fb_ends.append(event.time)
            self.weapons.sync(event.time)

        return BurstRuntimeResult(
            tuple(fb_starts), tuple(fb_ends), tuple(casts), processed
        )
