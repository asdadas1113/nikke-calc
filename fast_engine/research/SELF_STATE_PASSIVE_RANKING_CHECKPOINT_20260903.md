# Self-state conditional passive ranking checkpoint — 2026-09-03

## Purpose

Close the ranking inversion found in `RANKING_CORE_CROSSOVER_CHECKPOINT_20260903.md` by identifying the remaining supported-semantic mismatch after the Quency self-stack passive fix.

This checkpoint does **not** expand Fast coverage, change candidate generation, add a character-name rule, or modify Moris semantics.

## Certified pair

`컨트롤_미란다미하라`

- 미란다
- 브리드 : 사일런트 트랙
- 헬름
- 루주
- 미하라 : 본딩 체인

`레이드_레드후드퀀시`

- 라피 : 레드 후드
- 레드 후드
- 프리카
- 민트
- 퀀시 : 이스케이프 퀸

## Correction to the previous Quency diagnosis

The handoff had isolated Quency `위대한 도둑 3` as approximately `-40.28%` in Fast and proposed same-timestamp burst ordering as the leading hypothesis.

That diagnosis is no longer reproducible on the current runtime.

A direct single-hit comparison after commit `7695efcff56bd59a5e352a1462f4bda9e61cefed` showed:

- Moris: `25,711,754`
- Fast: `25,711,753.73`

The old `-40.28%` ratio instead matches the state before the self-stack conditional-passive fix: omitting Quency's completed-route critical-rate and split-damage passives produces essentially the same fixed ratio.

Therefore Quency same-timestamp burst ordering was not changed.

## Remaining discrepancy after the Quency fix

Re-running the certified core crossover after `7695efc` reduced the old `core_px=10` inversion from roughly 9 percentage points to less than 1 percentage point.

Actor decomposition identified one outlier:

- Frika remained about `-18.7%` in Fast at both `core_px=0` and `core_px=10`.
- Frika's damage in this scenario is entirely normal attack damage.
- Moris fired 122 Frika normal attacks; Fast's static plan contained 123, so missing shots were not the cause.

The compiled Frika effects contain a permanent passive `pierce_enabled` gated by `self_state:퍼포먼스`. `퍼포먼스` is created by Frika's burst, but Fast did not re-materialize the permanent conditional passive when that named self-state appeared.

The existing sparse synchronization introduced in `7695efc` handled `SELF_STACK_AT_LEAST`, but not `SELF_STATE` / `NOT_SELF_STATE`.

## Generic fix

Commit:

`28428dd601ae3ce64a219188afd894b1242a5eb4` — `fix: sync self-state conditional passives`

Changed:

- `fast_engine/engine/dispatcher.py`
- `fast_engine/tests/test_conditional_passive_self_stack.py`

New certified shape:

- effect type `buff`
- permanent (`duration None/-1`)
- one-stack passive
- static/runtime-supported target
- trigger exactly `passive`
- conditions only `SELF_STATE` or `NOT_SELF_STATE`

These passives are re-evaluated sparsely on named self-state edges. No character name is used by the runtime rule.

Focused regression now checks that Frika has `퍼포먼스` and its conditional `pierce_enabled` passive becomes active. The existing Quency self-stack regression remains in the same test module.

Targeted result:

- 2 tests run
- 2 passed

## Certified core crossover after the fix

Scenario contract remains:

- duration: 180s
- first burst: 3.0s
- expected RNG
- enemy DEF: 60,000
- enemy code: `작열`
- only `core_px` changes

Margin is `(Miranda/Mihara - Red Hood/Quency) / max(team scores)`.
Positive means Miranda/Mihara ranks higher.

| core_px | Moris margin | Fast margin | Order agrees |
|---:|---:|---:|:---:|
| 0 | +9.94% | +8.28% | yes |
| 10 | -0.45% | -2.22% | yes |
| 20 | -2.61% | -4.34% | yes |
| 30 | -7.01% | -8.64% | yes |
| 40 | -13.52% | -15.03% | yes |
| 52 | -20.54% | -21.90% | yes |

The previously failing points `core_px=10`, `20`, and `30` now all preserve Moris order.

At the key near-tie point `core_px=10`:

Moris:

- Miranda/Mihara: `3,441,496,042`
- Red Hood/Quency: `3,457,138,934`
- Red Hood/Quency wins by about `0.45%`.

Fast:

- Miranda/Mihara: `3,441,658,894.956`
- Red Hood/Quency: `3,519,875,399.507`
- Red Hood/Quency wins by about `2.22%`.

Frika itself changed from roughly `-18.7%` Fast error before the fix to roughly `+2.6~2.8%` after the fix.

For the `core_px=0 -> 10` response, the Red Hood/Quency team's Fast gain is `1.0210x` Moris gain; Frika's gain is `1.0234x` Moris. The severe under-response is gone.

## Standardized public audit after the fix

The project corpus remains 24 non-`지그_*` five-person source cases. One ordered membership is duplicated, so ranking analysis is performed on 23 unique memberships while source accounting remains 24 cases.

Post-fix audit:

- source cases: 24
- unique memberships: 23
- Fast-certified memberships: 2
- coverage gaps: 21
- certified pairwise accuracy: `1.0` (`1/1` comparable pair)
- certified clean top-N recall: `1.0`

Certified default-scenario score errors:

`컨트롤_미란다미하라`

- Moris: `2,826,025,741`
- Fast: `2,806,756,837.590`
- relative error: `-0.68184%`

`레이드_레드후드퀀시`

- Moris: `2,009,756,793`
- Fast: `2,045,799,145.664`
- relative error: `+1.79337%`

Median clean relative error across the two certified teams is about `+0.556%`.

## Interpretation

The original supported-core ranking inversion is resolved for the only currently certified real pair.

The failure was not one core-hit formula bug. It was dominated by two generic state-delivery gaps:

1. Quency permanent passives gated by self stacks were not synchronized when their named stack providers changed (`7695efc`).
2. Frika permanent passives gated by named self states were not synchronized when `퍼포먼스` appeared (`28428dd`).

After both fixes, the tested core-response axis preserves Moris ordering at all six sampled points.

This does **not** prove production-ranking readiness. Only two real public memberships are currently Fast-certified, and the Red Hood/Quency team still has a modest positive absolute-score bias around 1.8% under the default standardized scenario.

## Consequence / next checkpoint

Keep coverage expansion paused for the immediate next checkpoint.

The next useful step is ranking validation on additional supported static scenarios for the same certified pair, deliberately seeking close margins and different stress axes without adding mechanics. Examples include supported DEF and element-code variations already represented by the current static enemy contract.

If those tests remain stable, ranking validation can move toward a broader certified sample as coverage naturally becomes available. Do not integrate Fast into optimizer production ranking based only on this one pair.
