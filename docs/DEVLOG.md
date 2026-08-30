# Roster optimizer devlog

## 2026-08-30 — development baseline

- repository: `asdadas1113/nikke-calc`
- branch: `roster-optimizer-prototype`
- start HEAD: `5fb57f98123b0ecdac13726c0dbc81bf183c8a31`
- Moris upstream: `Moris-kr/nikke-calc` `master` @ `fb2fd9157aa14499daf6b9f185beb685d4393f90`
- engine relation: prototype is based on the same Moris upstream engine commit; optimizer-only changes are one commit above it.

### Current state

- isolated `optimizer/` skeleton exists.
- evaluator path is `build_squad -> build_config -> simulate`.
- default optimizer evaluation is expected mode with `verbose=False`.
- global allocation is exact only within the evaluated candidate pool; candidate discovery remains heuristic.

### Measured benchmark

See `docs/roster-optimizer-prototype.md` for the first evaluator benchmark. No new Moris simulation benchmark was run in this entry.

### Next work

1. make evaluator cache identity explicitly include engine revision and account/build snapshot.
2. add a small exhaustive validation harness for candidate survival/recall, global score ratio, evaluation-call count, and runtime.
3. do not add new search heuristics until a measured failure justifies one.
