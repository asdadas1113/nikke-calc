# Fast Engine first public ranking audit — 2026-09-01

## Status

This is **not yet a Fast-vs-Moris ranking-accuracy report**. It is the first
optimizer-independent coverage audit, and it found that the current conservative
Fast certification gate blocks every real five-person squad in this small public
corpus before a Fast numeric score is accepted.

Do not interpret the result as "Fast ranks all teams incorrectly".

## Why this corpus was chosen

The existing optimizer was designed around expensive Moris calls and contains
search-budget/candidate-reduction heuristics. Using only its survivors for the
first Fast validation could therefore confound two different errors:

1. candidate-generation/pruning bias inherited from the Moris-cost era;
2. Fast Engine scoring/ranking error.

The first probe bypasses that optimizer entirely. Squad memberships come from the
public `context.snapshot.SQUADS` corpus, but snapshot-specific build/config/enemy
overrides are discarded. Synthetic `test_*`/non-five-person fixtures and duplicate
ordered squads are removed. All remaining squads are rebuilt and evaluated under
one common scenario:

- public `context.spec` default build;
- 180 s;
- first burst at 3 s;
- deterministic `rng_mode=expected`;
- default patternless enemy (`def=31784`, no element, no core, no parts/windows).

This produced 24 unique real five-person ordered squads.

## Measured result

CI commit: `782026020dd74647c5fdd5527977a6656cb8c29d`

- public standardized squads: **24**
- Fast certified numeric scores: **0**
- coverage gaps / fail-closed squads: **24**
- Moris simulation wall time for the sequential probe: **90.080 s**
- Fast scoring wall time: **0.000 s**, because every row was rejected by the
  pre-score safety gate and Fast scoring was deliberately not attempted
- Moris Top-10: **10 blocked, 0 scored-and-ranked-out**
- full branch CI after the probe: green, including calculator, optimizer, browser,
  and golden snapshot 29/29

### Important metric caveat

The generic diagnostic currently reports
`catastrophic_false_negative_rate = 1 - top_n_recall`, so this all-blocked corpus
prints `1.0`. That number is **not a demonstrated Fast scoring false-negative rate**.
All ten Top-10 misses were fail-closed coverage gaps; none was a supported Fast
score that ranked below the shortlist cutoff.

Until the metric is split, use:

- `top_n_blocked` for coverage/fallback pressure;
- `top_n_ranked_out` for actual scored ranking misses.

For this probe those values are **10** and **0** respectively.

## Blocker inventory

Counts below are effect/blocker occurrences, not distinct squads:

| blocker family | occurrences |
|---|---:|
| cadence / shot-shape | 109 |
| skill state delivery | 108 |
| normal-attack state delivery | 92 |
| unresolved normal-damage state | 33 |

Frequent repeated examples include:

- Crown `원 포 올 2` reload-speed cadence state — 7 squads;
- Crown `로얄 에타이어 4` ATK-damage state delivery — 7 squads;
- Little Mermaid `세이렌 송 2` ammo-charge cadence state — 6 squads;
- Little Mermaid `거품` received-damage state delivery — 6 squads;
- Maid Mast `파이레츠 스피릿 2` reload-speed cadence state — 5 squads;
- Privaty reload/max-ammo cadence states — 4 squads.

`unsupported` damage-event counts were empty because no row passed the state
safety gate far enough to run the score sink. This does **not** mean all skill
damage is already supported.

## Interpretation

### What this result supports

- The first audit successfully removed the current optimizer/candidate generator
  from the causal chain.
- The standardized scenario also removed snapshot-specific operating/enemy/build
  differences after an earlier rejected probe revealed that those differences
  would invalidate a single ranking table.
- The current bottleneck for realistic broad ranking is **Fast certification
  coverage**, especially dynamic cadence and state-delivery paths.
- Fail-closed behavior is working as designed: unsupported comparison-critical
  states are not silently turned into zero damage.

### What this result does not support

It does not establish:

- Fast pairwise ordering accuracy;
- Fast absolute damage error on these teams;
- production Top-N recall;
- a production shortlist width;
- that any of these 24 teams would be lost by the final optimizer;
- that the current candidate generator is good or bad;
- that a blocked mechanic is implemented incorrectly.

No Fast-vs-Moris score error exists to diagnose in this dataset yet, because no
certified Fast score was produced.

## Next validation sequence

Do not relax blockers merely to obtain a prettier ranking number.

1. Split coverage gaps from true scored false negatives in the generic ranking
   metric so a blocked row is never labeled a scoring failure.
2. Use the blocker inventory to implement/certify high-leverage generalized
   mechanics, not character-name exceptions.
3. Re-run this fixed standardized corpus after each meaningful coverage expansion.
4. Once a non-trivial certified subset exists, report pairwise ordering and
   Top-N-in-Top-K **only within that supported subset**, while continuing to report
   blocked Moris Top-N rows separately.
5. Before production pruning, build a larger optimizer-independent stratified
   corpus. Only after that attach the current candidate generator and decompose
   end-to-end loss as:

   `source universe → candidate generation → Fast coverage → Fast ranking → Moris shortlist`.

This ordering is specifically intended to prevent Moris-era search heuristics from
being misdiagnosed as Fast Engine errors.
