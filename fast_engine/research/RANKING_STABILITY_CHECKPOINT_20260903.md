# First Fast ranking stability checkpoint — 2026-09-03

## Purpose

This is the first ranking-focused checkpoint after the standardized public corpus reached two real Fast-certified teams.

Coverage is intentionally frozen for this checkpoint. No new mechanic support, character-name rule, optimizer pairing rule, or candidate generation logic is added.

The question is narrower: when the same two certified teams are evaluated under the same changing static combat conditions, does Fast preserve the Moris pairwise ordering?

Certified teams:
- `컨트롤_미란다미하라`
- `레이드_레드후드퀀시`

## Grid

Shared build contract remains `context.spec` public defaults. Both engines use expected RNG, first burst at 3.0s, no core, no parts, no immunity/element windows.

Only two common scenario axes change:
- duration: 30 / 60 / 90 / 180 seconds
- enemy DEF: 0 / 31,784 / 60,000

This gives 12 common scenarios. Both teams remained Fast-certified with zero blockers in every scenario.

## Results

`margin` is `(Miranda/Mihara - Red Hood/Quency) / max(team scores)`; positive means Miranda/Mihara ranks higher.

| Duration | DEF | Moris margin | Fast margin | Order agrees |
|---:|---:|---:|---:|:---:|
| 30 | 0 | 43.45% | 47.63% | yes |
| 30 | 31,784 | 42.07% | 46.39% | yes |
| 30 | 60,000 | 40.42% | 44.90% | yes |
| 60 | 0 | 33.43% | 37.53% | yes |
| 60 | 31,784 | 31.62% | 35.84% | yes |
| 60 | 60,000 | 29.49% | 33.83% | yes |
| 90 | 0 | 32.23% | 36.21% | yes |
| 90 | 31,784 | 30.36% | 34.45% | yes |
| 90 | 60,000 | 28.17% | 32.38% | yes |
| 180 | 0 | 30.81% | 35.95% | yes |
| 180 | 31,784 | 28.88% | 34.19% | yes |
| 180 | 60,000 | 26.62% | 32.12% | yes |

Pairwise sign agreement: **12 / 12 = 100%**.

The closest tested Moris case is 180s / DEF 60,000, but the true margin is still 26.62%. Therefore no actual rank reversal or near-tie was exercised.

Fast consistently exaggerates Miranda/Mihara's lead relative to Moris. The Fast-minus-Moris margin bias ranges from **+3.98 to +5.51 percentage points**, mean **+4.49pp** across this grid.

At the standard 180s / DEF 31,784 point:
- Moris: Miranda/Mihara 2,826,025,741 vs Red Hood/Quency 2,009,756,793
- Fast: Miranda/Mihara 2,806,756,837.590 vs Red Hood/Quency 1,847,113,505.936
- ordering agrees, while Fast widens the normalized gap by about 5.31pp.

## Interpretation

This is positive but weak ranking evidence.

What it establishes:
- Fast does not reverse this large-margin pair across a moderate duration/DEF grid.
- The result is not an artifact of the single standardized 180s / DEF 31,784 point.
- Coverage and ranking remain separated: no blocked team is assigned an artificial low Fast score.

What it does **not** establish:
- near-tie discrimination;
- correctness around a true ordering crossover;
- Top-N recall on a useful multi-team certified pool;
- absence of systematic ranking bias.

The observed +3.98 to +5.51pp gap inflation is specifically a reason not to treat the 12/12 result as sufficient ranking validation.

## Next ranking checkpoint

Do not resume coverage merely to grow the sample.

The next ranking-focused step should search for a **closer comparison using the already-certified teams and supported static scenario inputs** (for example core/accuracy or other already-supported static enemy inputs), ideally locating a Moris near-tie or true crossover. If no supported static scenario can bring this pair close, record that limitation and only then reconsider how to obtain a larger certified ranking sample without conflating coverage work with ranking evidence.
