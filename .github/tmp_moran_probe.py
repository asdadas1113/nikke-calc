from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def show(path: str, needles: tuple[str, ...], pad: int = 10) -> None:
    lines = (ROOT / path).read_text(encoding="utf-8").splitlines()
    print(f"\n===== {path} =====")
    ranges = []
    for i, line in enumerate(lines):
        if any(n in line for n in needles):
            ranges.append((max(0, i-pad), min(len(lines), i+pad+1)))
    merged = []
    for lo, hi in ranges:
        if not merged or lo > merged[-1][1]:
            merged.append([lo, hi])
        else:
            merged[-1][1] = max(merged[-1][1], hi)
    for lo, hi in merged:
        for j in range(lo, hi):
            print(f"{j+1:5d}: {lines[j]}")
        print("-----")

show("calculator/buff_manager.py", (
    "weapon_change",
    "_weapon_overrides",
    "_hit_count[",
    "def process_hit",
    "def notify(",
), pad=8)
show("calculator/timeline.py", (
    "def _runtime_weapon",
    "def _current_weapon",
    "last_weapon_state",
    "weapon_state !=",
    "ammo == -1",
    "state.hit_count",
    "duration_from_fire_rate",
), pad=12)
show("fast_engine/engine/compiler.py", (
    "weapon_change",
    "Weapon",
    "parameters",
), pad=8)
show("fast_engine/engine/score.py", (
    "weapon_change",
    "weapon_change_score",
    "dynamic_weapon",
    "hit_count",
    "self_state",
), pad=10)
show("fast_engine/engine/dispatcher.py", (
    "weapon_change",
    "hit_count",
    "self_state",
    "dynamic_weapon",
), pad=10)
show("fast_engine/engine/weapon_runtime.py", (
    "weapon",
    "reload",
    "next_fire",
    "hit_count",
    "ammo",
), pad=8)
show("fast_engine/engine/normal_runtime.py", (
    "weapon",
    "next_fire",
    "hit_count",
    "ammo",
    "on_shot",
), pad=8)
show("fast_engine/engine/damage_runtime.py", (
    "bonus_damage",
    "hit_count",
    "self_state",
), pad=8)
