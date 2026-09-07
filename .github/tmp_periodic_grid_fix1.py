from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p=Path(path); s=p.read_text(encoding='utf-8')
    if old not in s: raise SystemExit(f'anchor missing {path}: {old[:140]!r}')
    p.write_text(s.replace(old,new,1),encoding='utf-8')

# Score helper must own its compile-time damage sink locally; static_normal_score_blockers
# intentionally has no runtime sink in scope.
replace_once('fast_engine/engine/score.py',
'''def _finite_targeted_effect_interval_score_supported(\n    squad: CompiledSquad, effect, damage_sink\n) -> bool:\n    if not TriggerDispatcher._finite_self_effect_interval_shape_supported(effect):\n        return False\n''',
'''def _finite_targeted_effect_interval_score_supported(\n    squad: CompiledSquad, effect\n) -> bool:\n    if not TriggerDispatcher._finite_self_effect_interval_shape_supported(effect):\n        return False\n    from .damage_runtime import SimpleDamageScoreSink\n    damage_sink = SimpleDamageScoreSink(\n        squad,\n        EnemyStaticProfile(defense=0.0, duration=1.0),\n        certified_squad_ammo_effect_ids=_certified_squad_ammo_effect_ids(squad),\n    )\n''')
replace_once('fast_engine/engine/score.py',
'''                and _finite_targeted_effect_interval_score_supported(\n                    squad, effect, damage_sink\n                )\n''',
'''                and _finite_targeted_effect_interval_score_supported(\n                    squad, effect\n                )\n''')

# Moris runs BuffManager.tick before the burst controller. A burst-cast modifier
# activated at frame t is therefore first seen by every:Ns cooldown logic on the
# *next* outer-loop frame, not retroactively at t. Add one sparse phase-8 sync
# boundary rather than a global frame loop.
replace_once('fast_engine/engine/scheduler.py',
'''    STATE_END_NOTIFY = 21\n    PERIODIC_TICK = 30\n''',
'''    STATE_END_NOTIFY = 21\n    PERIODIC_SYNC = 22\n    PERIODIC_TICK = 30\n''')
replace_once('fast_engine/engine/scheduler.py',
'''    EventKind.STATE_END_NOTIFY: 5,\n    EventKind.PERIODIC_TICK: 10,\n''',
'''    EventKind.STATE_END_NOTIFY: 5,\n    EventKind.PERIODIC_SYNC: 8,\n    EventKind.PERIODIC_TICK: 10,\n''')

replace_once('fast_engine/engine/dynamic_periodic.py',
'''@dataclass(frozen=True, slots=True)\nclass DynamicPeriodicTickToken:\n    effect_id: int\n    rule_index: int\n    generation: int\n\n\n@dataclass(slots=True)\n''',
'''@dataclass(frozen=True, slots=True)\nclass DynamicPeriodicTickToken:\n    effect_id: int\n    rule_index: int\n    generation: int\n\n\n@dataclass(frozen=True, slots=True)\nclass DynamicPeriodicSyncToken:\n    time: float\n\n\n@dataclass(slots=True)\n''')
replace_once('fast_engine/engine/dynamic_periodic.py',
'''        'squad', 'effects', 'scheduler', 'horizon', '_states', '_owned',\n''',
'''        'squad', 'effects', 'scheduler', 'horizon', '_states', '_owned', '_pending_sync',\n''')
replace_once('fast_engine/engine/dynamic_periodic.py',
'''        self._owned = frozenset(self._states)\n\n    @property\n''',
'''        self._owned = frozenset(self._states)\n        self._pending_sync: set[float] = set()\n\n    @property\n''')
replace_once('fast_engine/engine/dynamic_periodic.py',
'''    def sync(self, now: float) -> None:\n        """Rescale remaining cooldown after an interval state transition."""\n''',
'''    def defer_sync(self, now: float) -> None:\n        """Observe a phase-late state change on Moris' next BuffManager frame."""\n        when = moris_next_tick(float(now), horizon=self.horizon)\n        if when >= self.horizon or when in self._pending_sync:\n            return\n        self._pending_sync.add(when)\n        self.scheduler.schedule(\n            when, EventKind.PERIODIC_SYNC, payload=DynamicPeriodicSyncToken(when)\n        )\n\n    def handle_sync(self, token: DynamicPeriodicSyncToken, now: float) -> None:\n        self._pending_sync.discard(token.time)\n        self.sync(now)\n\n    def sync(self, now: float) -> None:\n        """Rescale remaining cooldown after an interval state transition."""\n''')

replace_once('fast_engine/engine/burst_runtime.py',
'''from .dynamic_periodic import DynamicPeriodicCadenceRuntime, DynamicPeriodicTickToken\n''',
'''from .dynamic_periodic import (\n    DynamicPeriodicCadenceRuntime,\n    DynamicPeriodicSyncToken,\n    DynamicPeriodicTickToken,\n)\n''')
replace_once('fast_engine/engine/burst_runtime.py',
'''            if event.kind is EventKind.STATE_EXPIRE:\n                self.dispatcher.handle_expiry(event)\n                self.periodics.sync(event.time)\n''',
'''            if event.kind is EventKind.PERIODIC_SYNC:\n                token = event.payload\n                if isinstance(token, DynamicPeriodicSyncToken):\n                    self.periodics.handle_sync(token, event.time)\n                score_end_of_time(event.time)\n                continue\n\n            if event.kind is EventKind.STATE_EXPIRE:\n                self.dispatcher.handle_expiry(event)\n                self.periodics.sync(event.time)\n''')
replace_once('fast_engine/engine/burst_runtime.py',
'''            self.periodics.sync(event.time)\n            if event.kind is EventKind.FULL_BURST_START:\n''',
'''            # BuffManager has already processed every:Ns cooldowns on this frame;\n            # burst-cast interval buffs become visible to that system next frame.\n            self.periodics.defer_sync(event.time)\n            if event.kind is EventKind.FULL_BURST_START:\n''')

print('refined periodic-grid score scope and Moris next-frame modifier observation')
