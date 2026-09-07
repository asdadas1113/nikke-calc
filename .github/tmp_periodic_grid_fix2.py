from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p=Path(path); s=p.read_text(encoding='utf-8')
    if old not in s: raise SystemExit(f'anchor missing {path}: {old[:160]!r}')
    p.write_text(s.replace(old,new,1),encoding='utf-8')

# Keep the sparse sync truly targeted. Only actors with an owned targeted
# effect_interval periodic can schedule the next-frame observation boundary.
replace_once(
    'fast_engine/engine/dynamic_periodic.py',
'''        'squad', 'effects', 'scheduler', 'horizon', '_states', '_owned', '_pending_sync',\n''',
'''        'squad', 'effects', 'scheduler', 'horizon', '_states', '_owned', '_pending_sync',\n        '_modifier_actors',\n''')
replace_once(
    'fast_engine/engine/dynamic_periodic.py',
'''        self._owned = frozenset(self._states)\n        self._pending_sync: set[float] = set()\n''',
'''        self._owned = frozenset(self._states)\n        self._modifier_actors = frozenset(\n            state.actor for state in self._states.values()\n        )\n        self._pending_sync: set[float] = set()\n''')
replace_once(
    'fast_engine/engine/dynamic_periodic.py',
'''    def defer_sync(self, now: float) -> None:\n        """Observe a phase-late state change on Moris' next BuffManager frame."""\n        when = moris_next_tick(float(now), horizon=self.horizon)\n''',
'''    def defer_burst_cast_sync(self, actor: int | None, now: float) -> None:\n        """Observe an owned actor's burst-cast modifier on the next Moris frame."""\n        if actor is None or int(actor) not in self._modifier_actors:\n            return\n        when = moris_next_tick(float(now), horizon=self.horizon)\n''')

# Defer only after the exact burst_cast signal that could activate a supported
# modifier. This is actor/shape based and contains no character-name branch.
replace_once(
    'fast_engine/engine/burst_runtime.py',
'''                self.dispatcher.dispatch(signal, context=SignalContext())\n            # BuffManager has already processed every:Ns cooldowns on this frame;\n            # burst-cast interval buffs become visible to that system next frame.\n            self.periodics.defer_sync(event.time)\n            if event.kind is EventKind.FULL_BURST_START:\n''',
'''                self.dispatcher.dispatch(signal, context=SignalContext())\n                if signal.event_key == "burst_cast":\n                    self.periodics.defer_burst_cast_sync(\n                        signal.source_actor, signal.time\n                    )\n            if event.kind is EventKind.FULL_BURST_START:\n''')

print('narrowed periodic-grid sync reservations to owned burst-cast actors')
