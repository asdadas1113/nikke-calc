from pathlib import Path

p = Path("fast_engine/engine/score.py")
text = p.read_text(encoding="utf-8")
old = """        and not consumer.parameters\n        and len(consumer.condition_rules) == 1\n"""
new = """        and set(consumer.parameters).issubset({\"favorite\"})\n        and len(consumer.condition_rules) == 1\n"""
if old not in text and new not in text:
    raise RuntimeError("Moran consumer parameter anchor missing")
if old in text:
    text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")

# Moris keeps a nominal auto-fire deadline separate from the 60 Hz tick that
# observes it. Feeding the observed shot timestamp back into the deadline drifts
# 24/s cadence by a frame after the first non-grid deadline.
p = Path("fast_engine/engine/dynamic_reload.py")
text = p.read_text(encoding="utf-8")
old = "st.fire_deadline = max(float(st.fire_deadline), float(shot_time)) + inter"
new = "st.fire_deadline = float(st.fire_deadline) + inter"
if old not in text and new not in text:
    raise RuntimeError("Moran nominal deadline anchor missing")
if old in text:
    text = text.replace(old, new, 1)
p.write_text(text, encoding="utf-8")

# The direct lifecycle test must install the same damage delivery capability that
# production score_static_squad installs; otherwise hit_count damage consumers
# are deliberately absent from the runtime effect filter and no sparse boundary
# can be registered.
t = Path("fast_engine/tests/test_damage_moran_weapon_change_lifecycle.py")
text = t.read_text(encoding="utf-8")
old_import = "from fast_engine.engine.model import EnemyStaticProfile\n"
new_import = "from fast_engine.engine.model import EnemyStaticProfile\nfrom fast_engine.engine.damage_runtime import SimpleDamageScoreSink\n"
if new_import not in text:
    if old_import not in text:
        raise RuntimeError("Moran test import anchor missing")
    text = text.replace(old_import, new_import, 1)
old_runtime = '''        runtime = BurstRuntime(\n            compiled,\n            BurstPolicy(duration=20.0, first_burst_time=3.0),\n            EnemyStaticProfile(defense=31784.0, duration=20.0, core_px=0.0),\n        )\n'''
new_runtime = '''        enemy = EnemyStaticProfile(defense=31784.0, duration=20.0, core_px=0.0)\n        damage_sink = SimpleDamageScoreSink(compiled, enemy)\n        runtime = BurstRuntime(\n            compiled,\n            BurstPolicy(duration=20.0, first_burst_time=3.0),\n            enemy,\n            damage_sink=damage_sink,\n        )\n'''
if new_runtime not in text:
    if old_runtime not in text:
        raise RuntimeError("Moran test runtime anchor missing")
    text = text.replace(old_runtime, new_runtime, 1)
t.write_text(text, encoding="utf-8")
print("Moran provenance, nominal deadline, and direct score-delivery fixes staged")
