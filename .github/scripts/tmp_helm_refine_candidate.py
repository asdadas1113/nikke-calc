from __future__ import annotations

from pathlib import Path

path = Path("fast_engine/engine/dispatcher.py")
text = path.read_text(encoding="utf-8")
old = '''            and effect.effect_type == "buff"
            and bool(effect.name)
            and (effect.stat or "") == "received_dmg_pct"
            and effect.target_spec.mode is TargetMode.ENEMY
'''
new = '''            and effect.effect_type == "buff"
            and effect.polarity == "harmful"
            and bool(effect.name)
            and (effect.stat or "") == "received_dmg_pct"
            and effect.target_spec.mode is TargetMode.ENEMY
'''
if old not in text:
    if new not in text:
        raise SystemExit("Helm candidate refinement marker missing")
else:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
