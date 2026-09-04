from __future__ import annotations

from collections import Counter, defaultdict
import json

from context import snapshot, spec
from fast_engine.engine.compiler import compile_moris_squad
from fast_engine.engine.dispatcher import TriggerDispatcher
from fast_engine.engine.score import static_score_blockers


def source_corpus():
    rows = []
    seen = set()
    for source_name, case in snapshot.SQUADS.items():
        if str(source_name).startswith("지그_"):
            continue
        members = tuple(str(x) for x in case["members"])
        if len(members) != 5 or any(x.startswith("test_") for x in members):
            continue
        if members in seen:
            continue
        seen.add(members)
        rows.append((str(source_name), members))
    return rows


def trigger_shape(effect):
    return tuple(
        (
            str(rule.event_key or ""),
            str(getattr(rule.mode, "value", rule.mode)),
            rule.threshold,
            rule.interval,
            bool(getattr(rule, "trigger_count_reducible", False)),
        )
        for rule in effect.triggers
    )


def condition_shape(effect):
    out = []
    for rule in effect.condition_rules:
        raw = getattr(rule, "__dict__", None)
        if raw is None:
            raw = {slot: getattr(rule, slot) for slot in getattr(rule, "__slots__", ())}
        cooked = {}
        for key, value in raw.items():
            cooked[key] = getattr(value, "value", value)
        out.append(cooked)
    return tuple(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) for row in out)


def blocker_effect(blocker, compiled):
    if blocker.startswith("control:"):
        return None
    parts = blocker.split(":")
    family = parts[0]
    if family == "weapon_change":
        owner = parts[1]
        name = ":".join(parts[2:])
        candidates = [e for e in compiled.effects if compiled.members[e.actor].name == owner and e.effect_type == "weapon_change"]
        exact = [e for e in candidates if (e.name or "unnamed") == name]
        return exact[0] if len(exact) == 1 else (candidates[0] if len(candidates) == 1 else None)
    if len(parts) < 4:
        return None
    owner = parts[1]
    stat = parts[-1]
    name = ":".join(parts[2:-1])
    candidates = [
        e for e in compiled.effects
        if compiled.members[e.actor].name == owner
        and (e.stat or "?") == stat
        and (e.name or e.stat or "?") == name
    ]
    return candidates[0] if len(candidates) == 1 else None


def main():
    family_counts = Counter()
    exact_counts = Counter()
    shape_counts = Counter()
    shape_teams = defaultdict(set)
    details = []
    certified = []

    for source_name, members in source_corpus():
        squad = spec.build_squad(list(members))
        compiled = compile_moris_squad(squad)
        blockers = static_score_blockers(compiled)
        if not blockers:
            certified.append(source_name)
            continue
        for blocker in blockers:
            family = blocker.split(":", 1)[0]
            family_counts[family] += 1
            exact_counts[blocker] += 1
            effect = blocker_effect(blocker, compiled)
            if effect is None:
                shape = (family, "<no-effect>")
                row = {
                    "team": source_name,
                    "members": members,
                    "blocker": blocker,
                    "family": family,
                    "effect_match": False,
                }
            else:
                shape = (
                    family,
                    effect.effect_type,
                    effect.stat or "",
                    effect.target_spec.mode.value,
                    effect.duration,
                    effect.max_stack,
                    trigger_shape(effect),
                    condition_shape(effect),
                    tuple(sorted((str(k), str(v)) for k, v in effect.parameters.items())),
                    str(getattr(effect.capability, "value", effect.capability)),
                    bool(TriggerDispatcher.is_executable_effect(effect)),
                )
                row = {
                    "team": source_name,
                    "members": members,
                    "blocker": blocker,
                    "family": family,
                    "effect_match": True,
                    "effect_id": effect.effect_id,
                    "owner": compiled.members[effect.actor].name,
                    "name": effect.name,
                    "type": effect.effect_type,
                    "stat": effect.stat,
                    "value": effect.value,
                    "target": effect.target_spec.mode.value,
                    "duration": effect.duration,
                    "max_stack": effect.max_stack,
                    "triggers": trigger_shape(effect),
                    "conditions": condition_shape(effect),
                    "parameters": effect.parameters,
                    "capability": str(getattr(effect.capability, "value", effect.capability)),
                    "executable": bool(TriggerDispatcher.is_executable_effect(effect)),
                }
            shape_counts[shape] += 1
            shape_teams[shape].add(source_name)
            details.append(row)

    print("=== POST-ASUKA FRONTIER ===")
    print("unique_teams", len(source_corpus()), "certified", len(certified), "gaps", len(source_corpus()) - len(certified))
    print("certified", certified)
    print("family_counts", family_counts.most_common())
    print("\n=== REPEATED EXACT BLOCKERS ===")
    for blocker, count in exact_counts.most_common():
        if count >= 2:
            print(count, blocker)
    print("\n=== REPEATED SHAPES ===")
    for shape, count in shape_counts.most_common():
        if count < 2:
            continue
        print(json.dumps({"count": count, "teams": sorted(shape_teams[shape]), "shape": shape}, ensure_ascii=False, default=str))
    print("\n=== DETAILS ===")
    for row in details:
        print(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
