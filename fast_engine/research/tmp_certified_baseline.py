from __future__ import annotations

import argparse
import json
from pathlib import Path

from context import spec
from fast_engine.engine.burst import compile_burst_policy
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.model import EnemyStaticProfile
from fast_engine.engine.score import score_static_squad, static_score_blockers

CONFIG = {"duration": 180.0, "first_burst_time": 3.0, "rng_mode": "expected"}
TEAMS = {
    "컨트롤_미란다미하라": ["미란다", "브리드 : 사일런트 트랙", "헬름", "루주", "미하라 : 본딩 체인"],
    "레이드_레드후드퀀시": ["라피 : 레드 후드", "레드 후드", "프리카", "민트", "퀀시 : 이스케이프 퀸"],
}


def scores() -> dict[str, float]:
    enemy = EnemyStaticProfile(
        defense=31784.0,
        element=None,
        core_uptime=0.0,
        core_px=0.0,
        duration=180.0,
    )
    out = {}
    for name, members in TEAMS.items():
        raw = spec.build_squad(members)
        compiled = compile_moris_squad(raw)
        blockers = static_score_blockers(compiled)
        assert blockers == (), (name, blockers)
        policy = compile_burst_policy(raw, compiled, CONFIG)
        result = score_static_squad(compiled, policy, enemy, duration=180.0)
        assert not result.unsupported, (name, result.unsupported)
        out[name] = float(result.squad_total)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write")
    group.add_argument("--compare")
    args = parser.parse_args()
    current = scores()
    if args.write:
        Path(args.write).write_text(json.dumps(current, ensure_ascii=False, sort_keys=True))
        print("CERTIFIED_BASELINE_PRE=" + json.dumps(current, ensure_ascii=False, sort_keys=True))
        return
    before = json.loads(Path(args.compare).read_text())
    assert before.keys() == current.keys()
    for name, value in current.items():
        old = float(before[name])
        rel = value / old - 1.0 if old else 0.0
        assert abs(rel) < 1e-12, f"{name}: pre={old} post={value} rel={rel}"
        print(f"CERTIFIED_UNCHANGED {name} pre={old:.9f} post={value:.9f} rel={rel:.3e}")
    print("CERTIFIED_BASELINE_POST=" + json.dumps(current, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
