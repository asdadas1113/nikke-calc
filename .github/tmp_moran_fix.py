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
print("Moran favorite provenance fix staged")
