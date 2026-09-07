from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p=Path(path); s=p.read_text(encoding='utf-8')
    if old not in s:
        raise SystemExit(f'anchor missing in {path}: {old[:120]!r}')
    p.write_text(s.replace(old,new,1),encoding='utf-8')

# score.py already imports no CapabilityDisposition; keep this local proof value-based.
replace_once(
    'fast_engine/engine/score.py',
    '        companion.capability.disposition is CapabilityDisposition.PLANNED\n',
    '        companion.capability.disposition.value == "planned"\n',
)

# A decimal Fast burst boundary such as 3.35 represents the same Moris outer
# frame as the repeated-add value 3.349999999999993. Re-anchor only this new
# one-shot mode to that observed source frame before computing a long charge.
replace_once(
    'fast_engine/engine/dynamic_weapon.py',
    'from .dynamic_rapid import DynamicRapidCadenceRuntime\n',
    'from .dynamic_rapid import DynamicRapidCadenceRuntime\nfrom .frame_lattice import moris_observed_tick\n',
)
old='''        super().sync(now)\n        for actor,active_before in was_active.items():\n            active_after=(\n                self._states.get(actor) is not None\n                and self._states[actor].weapon_change_id is not None\n            )\n            if active_before and not active_after and actor in self._rapid_reload.actors:\n'''
new='''        super().sync(now)\n        for actor,active_before in was_active.items():\n            active_after=(\n                self._states.get(actor) is not None\n                and self._states[actor].weapon_change_id is not None\n            )\n            if (\n                not active_before\n                and active_after\n                and actor in self._mode_only_single_charge_actors\n            ):\n                st=self._states[actor]\n                source_tick=moris_observed_tick(\n                    float(now), horizon=self.duration, epsilon=1e-9\n                )\n                st.charge_start=source_tick\n                st.phase_end=self._observe_phase_boundary(\n                    source_tick + self._effective_charge_time(actor,float(now))\n                )\n                self._invalidate(st)\n                self._plan(actor,float(now))\n            if active_before and not active_after and actor in self._rapid_reload.actors:\n'''
replace_once('fast_engine/engine/dynamic_weapon.py',old,new)
print('refined staged single-charge score import and Moris source-frame anchor')
