from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from calculator.buff_manager import BuffManager
from calculator.timeline import simulate
from context import snapshot, spec

orig_notify = BuffManager._notify
orig_activate = BuffManager._activate


def traced_notify(self, event, t, caster):
    if caster == "목단" and event == "hit_count" and 2.6 <= t <= 3.6:
        before = self._event_counts.get(caster, {}).get(event, 0)
        print(
            "TRACE_HIT_BEFORE",
            f"t={t:.15f}",
            f"count={before}",
            f"wc={self.weapon_change_name(caster)!r}",
        )
    result = orig_notify(self, event, t, caster)
    if caster == "목단" and event == "hit_count" and 2.6 <= t <= 3.6:
        after = self._event_counts.get(caster, {}).get(event, 0)
        print("TRACE_HIT_AFTER", f"t={t:.15f}", f"count={after}")
    return result


def traced_activate(self, eff, caster, t, *args, **kwargs):
    if caster == "목단" and eff.get("name") in {"정정당당 승부다!", "다 덤벼! 2"}:
        print(
            "TRACE_ACTIVATE",
            f"t={t:.15f}",
            f"name={eff.get('name')!r}",
            f"hit_count={self._event_counts.get(caster, {}).get('hit_count', 0)}",
            f"wc={self.weapon_change_name(caster)!r}",
            f"kwargs={kwargs!r}",
        )
    return orig_activate(self, eff, caster, t, *args, **kwargs)

BuffManager._notify = traced_notify
BuffManager._activate = traced_activate

row = snapshot.SQUADS["스쿼드4"]
squad = spec.build_squad(list(row["members"]))
result = simulate(
    squad,
    config={"duration": 4.0, "rng_mode": "expected", **row.get("config", {})},
    verbose=True,
)
print("TOTAL", result.total_dmg)
for ev in result.log.events:
    text = str(ev)
    if "목단" in text and ("normal" in text or "다 덤벼! 2" in text or "정정당당 승부다!" in text):
        print("EVENT", text)
