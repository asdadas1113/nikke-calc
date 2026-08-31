from pathlib import Path


auto = Path("tests/benchmark_optimizer_same_budget_auto_worker.py")
text = auto.read_text(encoding="utf-8")
old = "from optimizer.same_budget import run_same_budget_comparison  # noqa: E402\n"
new = (
    "from optimizer.meta_bounds_input import parse_bounded_meta_evidence  # noqa: E402\n"
    "from optimizer.same_budget import run_same_budget_comparison  # noqa: E402\n"
)
if old not in text:
    raise SystemExit("auto worker import anchor missing")
text = text.replace(old, new, 1)
old = "    meta = base.parse_meta_evidence(base.load(args.meta))\n"
new = (
    "    meta = parse_bounded_meta_evidence(\n"
    "        base.load(args.meta),\n"
    "        roster=snapshot.roster,\n"
    "    )\n"
)
if old not in text:
    raise SystemExit("auto worker research parser call missing")
text = text.replace(old, new, 1)
replacements = {
    'meta["snapshots"]': "meta.snapshots",
    'meta["epochs"]': "meta.epochs",
    'meta["schedule"]': "meta.schedule",
    'meta["completed_through"]': "meta.completed_through",
    'meta["policy"]': "meta.policy",
    'meta["restoration_batch_size"]': "meta.restoration_batch_size",
    'meta["cold_exploration_limit"]': "meta.cold_exploration_limit",
    'meta["protected_names"]': "meta.protected_names",
}
for old, new in replacements.items():
    if old not in text:
        raise SystemExit(f"auto worker expected access missing: {old}")
    text = text.replace(old, new)
auto.write_text(text, encoding="utf-8")

wrapper = Path("tests/benchmark_optimizer_same_budget_auto_enikk_worker.py")
text = wrapper.read_text(encoding="utf-8")
old = "from optimizer.meta_epoch_input import resolve_meta_epoch_input  # noqa: E402\n"
new = "from optimizer.meta_bounds_input import parse_bounded_meta_evidence  # noqa: E402\n"
if old not in text:
    raise SystemExit("enikk wrapper import anchor missing")
text = text.replace(old, new, 1)
start = text.index("def _resolved_meta_payload(\n")
end = text.index("\n\ndef main() -> None:\n", start)
replacement = '''def _resolved_meta_payload(
    payload: dict[str, Any],
    roster: Sequence[str],
) -> tuple[dict[str, Any], dict[str, int]]:
    """Normalize supported epoch evidence after strict bounded Meta parsing."""

    parsed = parse_bounded_meta_evidence(payload, roster=roster)
    out = json.loads(json.dumps(payload, ensure_ascii=False))
    out.pop("first_availability", None)
    out.pop("change_events", None)
    out["epochs"] = {
        name: {
            "knowledge": row.knowledge.value,
            **(
                {"valid_from": row.valid_from.isoformat()}
                if row.valid_from is not None
                else {}
            ),
            "source": row.source,
            "reason": row.reason,
        }
        for name, row in parsed.epochs.items()
    }
    counts: dict[str, int] = {}
    for row in parsed.epochs.values():
        counts[row.knowledge.value] = counts.get(row.knowledge.value, 0) + 1
    return out, counts
'''
text = text[:start] + replacement + text[end:]
wrapper.write_text(text, encoding="utf-8")

test = Path("tests/test_optimizer_same_budget_auto_enikk_worker.py")
text = test.read_text(encoding="utf-8")
anchor = '        "schedule": {"periods": [], "complete": True, "source": "fixture"},\n'
insertion = anchor + '''        "coverage_contract": {
            "servers": ["GLOBAL"],
            "rank_start": 1,
            "rank_end": 1,
            "team_count": 5,
            "team_size": 5,
            "source": "fixture-contract",
        },
'''
if anchor not in text:
    raise SystemExit("meta fixture schedule anchor missing")
text = text.replace(anchor, insertion, 1)
test.write_text(text, encoding="utf-8")
