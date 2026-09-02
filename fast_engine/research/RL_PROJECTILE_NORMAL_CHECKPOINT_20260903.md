# Fast RL normal projectile-routing checkpoint — 2026-09-03

## Purpose

Continue ranking-semantic diagnosis after the core-crossover inversion was decomposed by character.

This checkpoint fixes one generic Fast damage-shape mismatch only:

- ordinary **RL normal attacks** are projectile-explosion hits in Moris;
- Fast already resolved `projectile_explosion_dmg_pct`, but its normal-attack `HitSpec` did not mark RL shots as projectile explosions;
- therefore active projectile-explosion buffs were present in Fast state but omitted from RL normal-attack factor 5.

No Moris `calculator/` semantics, character-name rule, candidate-generation rule, optimizer pairing rule, boss chronology, or coverage policy is changed.

## Diagnosis

The ranking hard case remains the two certified public teams from the core-crossover checkpoint:

- `컨트롤_미란다미하라`
- `레이드_레드후드퀀시`

Earlier decomposition showed that the crossover error was not explained by core probability, physical shot count, full-burst interval counting, or collection `charge_dmg_mag_pct` activation.

A 2.5s first-shot probe under:

- enemy DEF 60,000
- enemy code `작열`
- `core_px=0`
- expected RNG

isolated the first divergence.

Before this fix:

- 프리카 first full-charge normal hit
  - Moris: `328,312`
  - Fast: `328,312.282...`
  - effectively exact.
- 민트 first full-charge normal hit, after 프리카's same-time `full_charge_hit` buffs activate
  - Moris: `208,234`
  - Fast: `173,528.189...`
  - Fast was lower by almost exactly the active `projectile_explosion_dmg_pct +20%` factor.

Moris normal-fire construction marks RL shots with `is_projectile_explosion=True`. Fast's `NormalAttackSpec` had no equivalent weapon-shape bit, even though `DamageTermResolver` already carried the buff value.

## Implementation

`fast_engine/engine/normal_attack.py` now carries:

- `NormalAttackSpec.is_projectile_explosion`
- compiled/base weapon rule: `weapon_type == "RL"`
- forwarding into `HitSpec.is_projectile_explosion`

This lets the existing generic damage formula apply `projectile_explosion_dmg_pct` through factor 5 exactly where Moris does for ordinary RL shots.

The field defaults to `False` so existing ad-hoc/dynamic `NormalAttackSpec(...)` constructors are not silently widened. This checkpoint certifies the compiled/base RL path only; it does not claim support for a future weapon-type-changing dynamic path.

Implementation commits:

- `05c9a62ab75c0a55252b7f54c19ab90575b819a7` — `fix: apply RL projectile explosion buffs to normal attacks`
- `63afaa6a66083255815d841e1558db17bff1e6d1` — `fix: keep dynamic normal spec compatibility`
- `ece369165b31a233519bc08e2afe06a6c2fa569c` — `test: cover RL projectile explosion normal damage`

## Focused regression

A synthetic RL regression was added to `fast_engine/tests/test_damage_normal_attack.py`.

It verifies that:

1. compiled RL normal attack sets `is_projectile_explosion=True`;
2. Fast routes `projectile_explosion_dmg_pct` through the ordinary normal-attack formula;
3. the resulting expected damage matches Moris `calc_damage_avg(..., is_projectile_explosion=True)`.

Post-fix real-team first shot:

- 민트 Moris: `208,234`
- 민트 Fast: `208,233.827...`

The isolated mismatch is therefore removed.

## Core-crossover recheck

Scenario is unchanged from `RANKING_CORE_CROSSOVER_CHECKPOINT_20260903.md`:

- duration 180s
- first burst 3.0s
- expected RNG
- enemy DEF 60,000
- enemy code `작열`
- only `core_px` changes.

Margin is `(Miranda/Mihara - Red Hood/Quency) / max(team scores)`.
Positive means Miranda/Mihara ranks higher.

| core_px | Moris margin | Fast before | Fast after | After order agrees |
|---:|---:|---:|---:|:---:|
| 0 | +9.94% | +19.64% | +18.39% | yes |
| 10 | -0.45% | +9.36% | +7.66% | no |
| 20 | -2.61% | +7.43% | +5.73% | no |
| 30 | -7.01% | +3.22% | +1.52% | no |
| 40 | -13.52% | -3.68% | -5.22% | yes |

So this was a real ranking-semantic bug and fixing it moves Fast in the correct direction, but it does **not** fully resolve the near-tie inversion. Fast still misorders the pair at `core_px=10`, `20`, and `30`.

The next remaining error should therefore be diagnosed separately rather than broadening this fix. The earlier character decomposition makes Quency's normal-attack under-valuation a strong next candidate, but this checkpoint does not implement or claim that diagnosis.

## Standardized public audit

The current `public_ranking_probe.py` run after the fix reports:

- 23 **unique memberships**
- 2 certified
- 21 coverage gaps
- clean certified pairwise accuracy: `1.0`
- clean relative error:
  - Miranda/Mihara: `-0.68184%`
  - Red Hood/Quency: `-5.90561%`
  - median of the two: `-3.29372%`
- unsupported runtime families: none.

Red Hood/Quency under the default public scenario:

- Moris: `2,009,756,793`
- Fast: `1,891,068,454.610`

### Public-corpus accounting note

The project contract says the standardized source universe is the fixed **24 non-`지그_*` five-person source cases**.

`context.snapshot.SQUADS` still has those 24 source cases, but the current ranking probe deduplicates identical ordered memberships. `레이드_미하라에이다` and `컨트롤_에이다미하라` have the same five members, and the probe deliberately discards their case-specific config/enemy/character overrides. They therefore collapse to one identical standardized membership and the script prints 23.

Under source-case accounting the same run is therefore:

- 24 source cases
- 2 certified
- 22 coverage gaps.

This is a **validation-harness accounting mismatch**, not a Fast engine result. It is recorded here but deliberately not fixed in this RL mechanic checkpoint.

## CI

Official feature-branch CI on implementation HEAD `ece369165b31a233519bc08e2afe06a6c2fa569c`:

- run `33691333035`
- conclusion: success
- doclint: success
- Fast damage suite: 110 tests passed
- engine unit tests: 137 passed, 1 skipped
- optimizer unit tests: 374 passed
- bridge: 31 passed, 1 skipped
- browser/site: 385 passed
- golden snapshot: 29/29 passed
- Fast structural performance: median `95.85ms` for 180s score, 368 events in that contract run.

The Moris golden snapshots did not change, as expected for a Fast-only correction.

## Repository safety

`master` remains unchanged at:

- `fb2fd9157aa14499daf6b9f185beb685d4393f90`

No merge to `master` was performed.

## Consequence

This RL projectile-routing slice is complete.

Keep coverage expansion paused. Ranking validation still has a genuine supported near-tie inversion, but one known source of Red Hood/Quency under-valuation has been removed.

Before using future standardized public-audit counts as a strict 24-team corpus metric, reconcile the probe's membership deduplication with the fixed 24-source-case contract. The remaining ranking-semantic diagnosis should stay separate from that harness-accounting correction.
