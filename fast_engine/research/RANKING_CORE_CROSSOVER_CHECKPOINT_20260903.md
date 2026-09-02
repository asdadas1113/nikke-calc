# Fast ranking core-crossover checkpoint — 2026-09-03

## Purpose

Continue ranking validation after the first two-team stability grid, without reopening Fast coverage.

The goal is to find a supported static scenario where the two currently certified public teams become a true near-tie or cross in Moris, then check whether Fast preserves that ordering.

Certified teams remain:

- `컨트롤_미란다미하라`
- `레이드_레드후드퀀시`

No new mechanic support, character-name rule, candidate-generation rule, or optimizer pairing rule is introduced in this checkpoint.

## Team structure

`컨트롤_미란다미하라`:

- 미란다 — 작열 / SMG
- 브리드 : 사일런트 트랙 — 작열 / SG
- 헬름 — 수냉 / SR
- 루주 — 전격 / SR
- 미하라 : 본딩 체인 — 작열 / MG

`레이드_레드후드퀀시`:

- 라피 : 레드 후드 — 작열 / MG
- 레드 후드 — 철갑 / SR
- 프리카 — 수냉 / SR
- 민트 — 철갑 / RL
- 퀀시 : 이스케이프 퀸 — 수냉 / SMG

This makes an elemental scenario useful for ranking pressure: against a 작열 enemy, the Red Hood/Quency team has two 수냉 members while Miranda/Mihara has one.

## Scenario contract

Shared build contract: `context.spec` public defaults.

Fixed inputs:

- duration: 180s
- first burst: 3.0s
- expected RNG
- enemy DEF: 60,000
- enemy code: 작열
- no parts / immunity chronology / element window chronology

Only `core_px` changes.

Both teams remained Fast-certified with:

- `static_score_blockers == ()`
- `FastScore.unsupported == ()`

at every tested point.

## Results

Margin is `(Miranda/Mihara - Red Hood/Quency) / max(team scores)`.
Positive means Miranda/Mihara ranks higher; negative means Red Hood/Quency ranks higher.

| core_px | Moris margin | Fast margin | Order agrees |
|---:|---:|---:|:---:|
| 0 | +9.94% | +19.64% | yes |
| 10 | **-0.45%** | **+9.36%** | **no** |
| 20 | -2.61% | +7.43% | **no** |
| 30 | -7.01% | +3.22% | **no** |
| 40 | -13.52% | -3.68% | yes |
| 52 | -20.54% | -11.23% | yes |

The key near-tie point is `core_px=10`.

Moris:

- Miranda/Mihara: `3,441,496,042`
- Red Hood/Quency: `3,457,138,934`
- Red Hood/Quency wins by about **0.45%**.

Fast:

- Miranda/Mihara: `3,441,658,894.956`
- Red Hood/Quency: `3,119,374,346.189`
- Miranda/Mihara wins by about **9.36%**.

So Fast gives the **wrong pairwise order exactly where the authoritative comparison is close**.

## Crossover bracketing

The authoritative Moris ordering crosses between:

- `core_px=0`: Miranda/Mihara ahead
- `core_px=10`: Red Hood/Quency ahead

Fast does not cross until between:

- `core_px=30`: Miranda/Mihara ahead
- `core_px=40`: Red Hood/Quency ahead

No exact threshold is claimed here; these are only tested brackets. The important result is that the two engines respond very differently to the same supported core-size axis.

## Interpretation

The first 12-scenario duration/DEF grid gave 12/12 pairwise agreement because that pair was always separated by a large true margin. This checkpoint provides the missing hard case and shows that the earlier stability result was not sufficient.

Ranking validation has now found a real failure:

1. both teams are genuinely Fast-certified;
2. no artificial blocked-team score is involved;
3. the scenario uses an already-supported static input (`core_px`);
4. Moris produces a near-tie and actual crossover;
5. Fast crosses much later and misorders the pair at `core_px=10`, `20`, and `30`.

This is therefore a **ranking-semantic problem inside already-supported core response**, not a coverage problem.

The magnitude and direction suggest that Fast is under-valuing the Red Hood/Quency team's gain from opening/increasing the core relative to Moris, or otherwise over-valuing Miranda/Mihara on the same axis. This checkpoint does not yet identify which character/effect path causes the divergence.

## Consequence

Keep coverage expansion paused.

Do not add more characters merely to increase the ranking sample before understanding this inversion.

The next single checkpoint should decompose the core-response delta by character/effect for these two certified teams, especially the Red Hood/Quency side, and determine whether the discrepancy comes from:

- weapon-specific core-hit probability / accuracy response;
- core-damage modifiers;
- core-hit-triggered effects;
- or another already-supported damage path.

Only after the source of this ranking inversion is understood should ranking validation continue to a larger sample or optimizer integration.
