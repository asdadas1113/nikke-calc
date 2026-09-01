from pathlib import Path

from context.spec import build_squad
from fast_engine.engine.compiler import compile_moris_squad

names = [
    "리틀 머메이드",
    "델타 : 닌자 시프",
    "크라운",
    "아스카 : WILLE",
    "라피 : 레드 후드",
]
squad = compile_moris_squad(build_squad(names))
print("=== ASUKA state-end effects ===")
for effect in squad.members[3].effects:
    if any((rule.event_key or "").startswith("event:state_end:") for rule in effect.triggers):
        print(effect)

for path in ("calculator/buff_manager.py", "calculator/timeline.py"):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    print(f"=== {path} force_reload contexts ===")
    for idx, line in enumerate(lines):
        if "force_reload" not in line:
            continue
        lo = max(0, idx - 10)
        hi = min(len(lines), idx + 18)
        print(f"--- lines {lo + 1}-{hi} ---")
        for j in range(lo, hi):
            print(f"{j + 1:05d}: {lines[j]}")
