from pathlib import Path

path = Path("fast_engine/engine/score.py")
text = path.read_text(encoding="utf-8")
old = '_PATTERNLESS_UNREACHABLE_EVENT_KEYS = frozenset({"received_hit"})'
new = '''_PATTERNLESS_UNREACHABLE_EVENT_KEYS = frozenset({
    "received_hit",
    "enemy_death",
    "event:part_destroy",
})'''
if old not in text:
    raise SystemExit("expected patternless event set not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("patched", path)
