from __future__ import annotations

from dataclasses import dataclass

from .burst import BurstMachine, BurstPolicy
from .conditions import SignalContext
from .dispatcher import TriggerDispatcher
from .model import CompiledSquad, EnemyStaticProfile
from .scheduler import EventKind, EventScheduler
from .state import StateStore
from .weapon import simulate_static_weapon_trigger_boundaries


@dataclass(frozen=True, slots=True)
class BurstRuntimeResult:
    full_burst_starts: tuple[float, ...]
    full_burst_ends: tuple[float, ...]
    casts: tuple[tuple[float, int, str], ...]
    events_processed: int


class BurstRuntime:
    """Current vertical slice: generic Fast trigger dispatch + burst scheduler."""

    __slots__ = ("squad", "enemy", "policy", "scheduler", "state", "machine", "dispatcher")

    def __init__(self, squad: CompiledSquad, policy: BurstPolicy, enemy: EnemyStaticProfile | None = None) -> None:
        self.squad = squad
        self.enemy = enemy or EnemyStaticProfile(duration=policy.duration)
        self.policy = policy
        self.scheduler = EventScheduler()
        self.state = StateStore.from_compiled_squad(squad)
        self.machine = BurstMachine(squad, policy)
        self.dispatcher = TriggerDispatcher(squad, self.state, self.enemy, self.machine, self.scheduler)

    def _broadcast(self, time: float, event_key: str) -> None:
        from .burst import BurstSignal
        for owner in range(len(self.squad.members)):
            self.dispatcher.dispatch(BurstSignal(time, event_key, owner, owner))

    def start(self, *, duration: float | None = None) -> None:
        # Moris registers passive as battle_start too.
        self._broadcast(0.0, "battle_start")
        self.machine.start(self.scheduler)
        horizon = self.policy.duration if duration is None else min(float(duration), self.policy.duration)
        # First weapon/runtime bridge: only reducible count thresholds belonging
        # to already-executable effects are materialized.  Ordinary bullets stay
        # aggregated inside WeaponCadenceMachine.
        from .burst import BurstSignal
        for boundary in simulate_static_weapon_trigger_boundaries(
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
                    boundary.event_key,
                    boundary.actor,
                    boundary.actor,
                    count_increment=boundary.count_increment,
                ),
            )

    def run(self, *, duration: float | None = None) -> BurstRuntimeResult:
        horizon = self.policy.duration if duration is None else min(float(duration), self.policy.duration)
        self.start(duration=horizon)
        fb_starts: list[float] = []
        casts: list[tuple[float, int, str]] = []
        fb_ends: list[float] = []
        processed = 0
        while self.scheduler and (self.scheduler.peek_time() or 0.0) <= horizon + 1e-9:
            event = self.scheduler.pop()
            processed += 1
            if event.kind is EventKind.STATE_EXPIRE:
                self.dispatcher.handle_expiry(event)
                continue
            if event.kind is EventKind.TRIGGER_BOUNDARY:
                self.dispatcher.dispatch(event.payload, context=SignalContext())
                continue

            extension = 0.0
            if event.kind is EventKind.FULL_BURST_START:
                extension = self.dispatcher.full_burst_extension(event.time, self.machine.full_burst_caster)
            signals = self.machine.handle(
                event,
                self.scheduler,
                full_burst_extension=extension,
                cooldown_buff_provider=self.dispatcher.burst_cooldown_buff,
            )
            for signal in signals:
                if signal.event_key == "burst_cast" and signal.source_actor is not None:
                    casts.append((signal.time, signal.source_actor, signal.stage or ""))
                self.dispatcher.dispatch(signal, context=SignalContext())
            if event.kind is EventKind.FULL_BURST_START:
                fb_starts.append(event.time)
                # Persistent burst_cooldown buffs that trigger at full_burst_start
                # are now active; reconcile them after all owner notifications.
                for actor in range(len(self.squad.members)):
                    self.machine.reconcile_persistent_cooldown(
                        actor,
                        self.dispatcher.burst_cooldown_buff(actor, event.time),
                        event.time,
                        self.scheduler,
                    )
            elif event.kind is EventKind.FULL_BURST_END:
                fb_ends.append(event.time)
        return BurstRuntimeResult(tuple(fb_starts), tuple(fb_ends), tuple(casts), processed)
