from __future__ import annotations

from dataclasses import dataclass

from .burst import BurstMachine, BurstPolicy
from .conditions import SignalContext
from .core_events import (
    is_static_expected_core_count_rule,
    simulate_static_expected_core_boundaries,
)
from .damage_state import DamageTermResolver
from .dispatcher import TriggerDispatcher
from .frame_lattice import moris_observed_tick
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
    nominal_time: float


class BurstRuntime:
    """Current vertical slice: generic Fast trigger dispatch + burst scheduler."""

    __slots__ = (
        "squad", "enemy", "policy", "scheduler", "state", "machine",
        "dispatcher", "weapons", "damage_sink",
    )

    _STATIC_LAST_BULLET_INVALIDATORS = frozenset({
        "reload_speed_pct",
        "reload_time_fixed",
        "max_ammo_pct",
        "max_ammo_flat",
    })
    _STATIC_CORE_CADENCE_INVALIDATORS = frozenset({
        "reload_speed_pct",
        "reload_time_fixed",
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
        "pellet_count",
        "pellet_count_fixed",
    })

    def __init__(
        self,
        squad: CompiledSquad,
        policy: BurstPolicy,
        enemy: EnemyStaticProfile | None = None,
        *,
        damage_sink=None,
    ) -> None:
        self.squad = squad
        self.enemy = enemy or EnemyStaticProfile(duration=policy.duration)
        self.policy = policy
        self.scheduler = EventScheduler()
        self.state = StateStore.from_compiled_squad(squad)
        self.machine = BurstMachine(squad, policy)
        self.damage_sink = damage_sink
        self.dispatcher = TriggerDispatcher(
            squad,
            self.state,
            self.enemy,
            self.machine,
            self.scheduler,
            damage_sink=damage_sink,
        )
        self.weapons = MultiSignalChargeCadenceRuntime(
            squad,
            self.dispatcher.effects,
            self.state,
            self.scheduler,
            duration=policy.duration,
            effect_filter=self.dispatcher.is_runtime_executable_effect,
        )
        if self.damage_sink is not None:
            self.damage_sink.attach(self)

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
            if interval <= 0.0 or interval >= horizon:
                continue
            # Moris initializes every:Ns at t=interval, not battle_start.
            # The combat scoring window is [0, horizon), so a tick exactly at the
            # nominal end time is not a damage-bearing combat event.
            observed = moris_observed_tick(interval, horizon=horizon)
            if observed >= horizon:
                continue
            self.scheduler.schedule(
                observed,
                EventKind.PERIODIC_TICK,
                actor=effect.actor,
                payload=PeriodicTickToken(
                    effect.effect_id, indexed.rule_index, interval, interval
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
    def _is_static_permanent_accuracy(effect) -> bool:
        """Accuracy fixed by battle-start state is safe for one static core plan."""
        return (
            effect.effect_type == "buff"
            and (effect.stat or "") == "accuracy_pct"
            and effect.duration in (None, -1.0)
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
        # change later, static planning must assume this actor may enter it.
        return True

    def _schedule_static_core_hits(
        self, horizon: float, dynamic_actors: set[int]
    ) -> None:
        """Schedule fixed expected ``core_hit_count:N`` crossings only.

        Moris expected mode accumulates fractional core probability once per
        physical hit/pellet and emits a logical core-hit event at each integer
        crossing. Fast collapses those events to only modulo thresholds that any
        executable effect observes. Live accuracy/cadence changes and dynamic
        weapon actors fail closed so no stale future core boundary is retained.
        """

        interested = {
            effect.actor
            for effect in self.squad.effects
            if self.dispatcher.is_runtime_executable_effect(effect)
            and any(is_static_expected_core_count_rule(rule) for rule in effect.triggers)
        }
        if not interested:
            return

        unsupported = interested & dynamic_actors
        if unsupported:
            names = ", ".join(
                self.squad.members[actor].name for actor in sorted(unsupported)
            )
            raise NotImplementedError(
                "Fast dynamic weapon + core_hit_count boundary not certified: " + names
            )

        invalidators: list[tuple[int, str]] = []
        for effect in self.squad.effects:
            stat = effect.stat or ""
            is_weapon_change = effect.effect_type == "weapon_change"
            is_cadence = stat in self._STATIC_CORE_CADENCE_INVALIDATORS
            is_accuracy = stat == "accuracy_pct"
            if not (is_weapon_change or is_cadence or is_accuracy):
                continue

            if is_cadence and self._is_static_permanent_self_cadence(effect):
                continue
            if (
                is_accuracy
                and self._is_static_permanent_accuracy(effect)
                and self.dispatcher.is_runtime_executable_effect(effect)
            ):
                continue

            for actor in interested:
                if self._effect_may_target_actor(effect, actor):
                    invalidators.append((actor, effect.name or stat or effect.effect_type))

        if invalidators:
            detail = ", ".join(
                f"{self.squad.members[actor].name}<-{name}"
                for actor, name in invalidators[:8]
            )
            if len(invalidators) > 8:
                detail += f", +{len(invalidators) - 8} more"
            raise NotImplementedError(
                "Fast static core_hit_count probability/cadence can be invalidated by live weapon state: "
                + detail
            )

        resolver = DamageTermResolver(
            self.squad,
            self.dispatcher.effects,
            self.state,
            self.enemy,
        )
        probabilities = {
            actor: self.enemy.core_rate_for_weapon(
                self.squad.members[actor].weapon,
                accuracy_pct=resolver.resolve(actor, now=0.0).accuracy_pct,
            )
            for actor in interested
        }

        from .burst import BurstSignal
        for boundary in simulate_static_expected_core_boundaries(
            self.squad,
            duration=horizon,
            core_probability_by_actor=probabilities,
            effect_filter=self.dispatcher.is_runtime_executable_effect,
        ):
            self.scheduler.schedule(
                boundary.time,
                EventKind.TRIGGER_BOUNDARY,
                actor=boundary.actor,
                payload=BurstSignal(
                    boundary.time,
                    "core_hit",
                    boundary.actor,
                    boundary.actor,
                    count_increment=boundary.count_increment,
                ),
            )

    def _schedule_static_last_bullets(
        self, horizon: float, dynamic_actors: set[int]
    ) -> None:
        """Expose exact magazine-ending signals without widening every weapon hit.

        ``last_bullet_fire`` and ``last_bullet`` remain distinct Moris events even
        though they share the same physical magazine-ending shot time. Direct
        damage-state support is certified only for post-shot ``last_bullet``;
        the pre-shot signal is preserved for existing runtime mechanics but is
        never aliased into post-shot semantics.

        Static actors are safe only while their reload/max-ammo cadence cannot be
        changed by live effects. A dynamic actor is safe for post-shot
        ``last_bullet`` only when its runtime explicitly certifies exact magazine
        ends. Dynamic pre-shot ``last_bullet_fire`` remains fail-closed because
        phase-30 weapon boundaries occur after score consumption.
        """
        interested = {
            effect.actor
            for effect in self.squad.effects
            if self.dispatcher.is_runtime_executable_effect(effect)
            and any(
                rule.event_key in {"last_bullet_fire", "last_bullet"}
                for rule in effect.triggers
            )
        }
        if not interested:
            return

        pre_shot_interested = {
            effect.actor
            for effect in self.squad.effects
            if self.dispatcher.is_runtime_executable_effect(effect)
            and any(rule.event_key == "last_bullet_fire" for rule in effect.triggers)
        }
        unsupported = {
            actor
            for actor in interested & dynamic_actors
            if actor in pre_shot_interested
            or not self.weapons.supports_dynamic_last_bullet(actor)
        }
        if unsupported:
            names = ", ".join(self.squad.members[actor].name for actor in sorted(unsupported))
            raise NotImplementedError(
                "Fast dynamic weapon + last-bullet boundary not certified: " + names
            )

        static_interested = interested - dynamic_actors
        invalidators: list[tuple[int, str]] = []
        for effect in self.squad.effects:
            if not self.dispatcher.is_runtime_executable_effect(effect):
                continue
            if (effect.stat or "") not in self._STATIC_LAST_BULLET_INVALIDATORS:
                continue
            if self._is_static_permanent_self_cadence(effect):
                continue
            for actor in static_interested:
                if self._effect_may_target_actor(effect, actor):
                    invalidators.append((actor, effect.name or effect.stat or "?"))

        if invalidators:
            detail = ", ".join(
                f"{self.squad.members[actor].name}<-{name}"
                for actor, name in invalidators[:8]
            )
            raise NotImplementedError(
                "Fast static last-bullet cadence can be invalidated by live weapon modifiers: "
                + detail
            )

        from .burst import BurstSignal
        for boundary in simulate_static_last_bullet_boundaries(
            self.squad,
            duration=horizon,
            effect_filter=lambda effect: (
                self.dispatcher.is_runtime_executable_effect(effect)
                and effect.actor not in dynamic_actors
            ),
        ):
            self.scheduler.schedule(
                boundary.time,
                EventKind.TRIGGER_BOUNDARY,
                actor=boundary.actor,
                payload=BurstSignal(
                    boundary.time,
                    boundary.event_key,
                    boundary.actor,
                    boundary.actor,
                ),
            )

    def start(self, *, duration: float | None = None) -> None:
        self._broadcast(0.0, "battle_start")
        # Moris finishes every ally battle_start notification, then emits an
        # enemy_spawn -> target_spawn pair for each ally in roster order.
        from .burst import BurstSignal
        for owner in range(len(self.squad.members)):
            self.dispatcher.dispatch(
                BurstSignal(0.0, "event:enemy_spawn", owner, owner)
            )
            self.dispatcher.dispatch(
                BurstSignal(0.0, "event:target_spawn", owner, owner)
            )
        self.machine.start(self.scheduler)
        horizon = (
            self.policy.duration
            if duration is None
            else min(float(duration), self.policy.duration)
        )
        self.weapons.start(0.0)
        dynamic_actors = set(self.weapons.all_dynamic_actors)
        # Core-hit notifications happen inside Moris' physical-hit loop before
        # shot-level hit_count/on_attack notifications. Schedule core boundaries
        # first so equal-time stable ordering preserves that relation for static actors.
        self._schedule_static_core_hits(horizon, dynamic_actors)
        from .burst import BurstSignal
        for boundary in simulate_weapon_trigger_boundaries(
            self.squad,
            duration=horizon,
            effect_filter=self.dispatcher.is_runtime_executable_effect,
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

    def run(
        self,
        *,
        duration: float | None = None,
        score_observer=None,
    ) -> BurstRuntimeResult:
        """Run scheduled combat boundaries, optionally feeding a score observer.

        Equal-time scoring follows Moris frame semantics: DoT damage is evaluated
        before expiry; expiry/periodic/burst state applies before the weapon shot;
        weapon-trigger effects apply after that shot. Scheduler phases below 30
        are therefore processed before the observer consumes ``=t``; phase-30+
        events consume the shot first and only then dispatch hit-based effects.

        The combat interval is half-open: ``[0, horizon)``. Moris' 60 Hz loop
        likewise has its final processed frame immediately before the nominal
        duration, so an event scheduled exactly at ``horizon`` does not contribute
        damage or trigger state for ranking.
        """

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

        def score_before_event(event) -> None:
            if score_observer is None:
                return
            score_observer.consume_until(event.time, inclusive=False)
            if event.phase >= 30:
                score_observer.consume_until(event.time, inclusive=True)

        def score_end_of_time(time: float) -> None:
            if score_observer is None:
                return
            next_time = self.scheduler.peek_time()
            if next_time is None or next_time > time + 1e-9:
                score_observer.consume_until(time, inclusive=True)

        while self.scheduler and (self.scheduler.peek_time() or 0.0) < horizon:
            event = self.scheduler.pop()
            processed += 1
            score_before_event(event)

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
                    if self.weapons.emits_squad_body_hit(boundary.actor):
                        self.dispatcher.dispatch_team_hit(
                            "squad_body_hit",
                            time=event.time,
                            attacker=boundary.actor,
                            context=SignalContext(),
                            count_increment=1,
                        )
                    if boundary.is_last_bullet:
                        self.dispatcher.dispatch(
                            BurstSignal(
                                event.time,
                                "last_bullet",
                                boundary.actor,
                                boundary.actor,
                            ),
                            context=SignalContext(),
                        )
                    self.weapons.sync(event.time)
                score_end_of_time(event.time)
                continue

            self.weapons.advance_to(event.time, inclusive=False)

            if event.kind is EventKind.DAMAGE_TICK:
                if self.damage_sink is not None:
                    self.damage_sink.handle_scheduled_tick(event)
                score_end_of_time(event.time)
                continue

            if event.kind is EventKind.STATE_EXPIRE:
                self.dispatcher.handle_expiry(event)
                self.weapons.sync(event.time)
                score_end_of_time(event.time)
                continue

            if event.kind is EventKind.STATE_END_NOTIFY:
                from .burst import BurstSignal
                owner, name = event.payload
                self.dispatcher.dispatch(
                    BurstSignal(
                        event.time,
                        f"event:state_end:{name}",
                        int(owner),
                        int(owner),
                    ),
                    context=SignalContext(),
                )
                self.weapons.sync(event.time)
                score_end_of_time(event.time)
                continue

            if event.kind is EventKind.PERIODIC_TICK:
                token = event.payload
                if not isinstance(token, PeriodicTickToken):
                    score_end_of_time(event.time)
                    continue
                self.dispatcher.dispatch_periodic(
                    token.effect_id,
                    token.rule_index,
                    time=event.time,
                    context=SignalContext(),
                )
                next_nominal = token.nominal_time + token.interval
                if next_nominal < horizon:
                    next_t = moris_observed_tick(next_nominal, horizon=horizon)
                    if next_t < horizon:
                        self.scheduler.schedule(
                            next_t,
                            EventKind.PERIODIC_TICK,
                            actor=event.actor,
                            payload=PeriodicTickToken(
                                token.effect_id, token.rule_index, token.interval, next_nominal
                            ),
                        )
                self.weapons.sync(event.time)
                score_end_of_time(event.time)
                continue

            if event.kind is EventKind.TRIGGER_BOUNDARY:
                self.dispatcher.dispatch(event.payload, context=SignalContext())
                self.weapons.sync(event.time)
                score_end_of_time(event.time)
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
                # Moris applies all full_burst_start buffs first, reconciles
                # persistent burst cooldown, then evaluates queued B3 bonus damage
                # under full-burst state. The score sink mirrors that exact point.
                if self.damage_sink is not None:
                    self.damage_sink.flush_pending_burst(now=event.time)
            elif event.kind is EventKind.FULL_BURST_END:
                fb_ends.append(event.time)
            self.weapons.sync(event.time)
            score_end_of_time(event.time)

        if score_observer is not None:
            score_observer.consume_until(horizon, inclusive=False)

        return BurstRuntimeResult(
            tuple(fb_starts), tuple(fb_ends), tuple(casts), processed
        )