from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}")
    p.write_text(text.replace(old, new, 1))


replace_once(
    "fast_engine/engine/dispatcher.py",
    '''        "reload_speed_pct",
        "charge_speed_pct",
''',
    '''        "reload_speed_pct",
        "mg_warmup_speed_pct",
        "charge_speed_pct",
''',
)

replace_once(
    "fast_engine/tests/test_damage_dynamic_mg_warmup.py",
    "from fast_engine.engine.burst_runtime import BurstRuntime\n",
    "from fast_engine.engine.burst_runtime import BurstRuntime\nfrom fast_engine.engine.compiler import compile_moris_squad\n",
)
replace_once(
    "fast_engine/tests/test_damage_dynamic_mg_warmup.py",
    "        blockers = static_score_blockers(build_squad(names))\n",
    "        blockers = static_score_blockers(compile_moris_squad(build_squad(names)))\n",
)
