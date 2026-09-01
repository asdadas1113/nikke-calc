# Fast Engine public ranking audit — 2026-09-01

## Status

This is still **not yet a Fast-vs-Moris ranking-accuracy report**. It is an
optimizer-independent coverage audit. The current conservative Fast certification
gate still blocks every real five-person squad in this small public corpus before
a Fast numeric score is accepted.

Do not interpret the result as "Fast ranks all teams incorrectly". The current
result is a **coverage failure only**; there is no certified Fast ranking in this
corpus yet.

## Post-spawn-lifecycle rerun

The standardized public audit was rerun once after the static
`enemy_spawn -> target_spawn` lifecycle checkpoint.

Engine branch baseline before the one-shot audit workflow:

`ae3b50bb870c034a036b14572c85e526643c4ba3`

One-shot audit commit:

`e1317f6cec73fec12f54feb1a4323a92412a0d7f`

GitHub Actions run:

`33524616825`

Measured result:

- public standardized squads: **24**
- Fast certified numeric scores: **0**
- coverage gaps / fail-closed squads: **24**
- Moris simulation wall time: **91.879 s**
- Fast scoring wall time: **0.000 s** because every row was rejected before
  certified scoring
- Moris Top-10: **10 blocked, 0 scored-and-ranked-out**
- `catastrophic_false_negative_rate = 0.0`
- `top_n_coverage_gap_rate = 1.0`
- `overall_top_n_miss_rate = 1.0`
- pairwise ranking accuracy: **not measurable** (`0` comparable pairs)

The important conclusion is therefore:

`candidate generation bypassed -> Fast coverage gap -> no ranking diagnosis yet`

The Little Mermaid `거품` blocker is absent from the rerun blocker inventory.
The former entries

- `normal_delivery:리틀 머메이드:거품:received_dmg_pct`
- `skill_state_delivery:리틀 머메이드:거품:received_dmg_pct`

no longer appear in any of the 24 rows. The aggregate families moved from the
first audit's `normal_delivery=92`, `skill_state_delivery=108` to
`normal_delivery=86`, `skill_state_delivery=103` on this rerun. The spawn
lifecycle checkpoint therefore removed the intended corpus blocker without
creating a certified team by itself.

Current blocker-family counts:

| blocker family | occurrences |
|---|---:|
| cadence / shot-shape | 109 |
| skill state delivery | 103 |
| normal-attack state delivery | 86 |
| unresolved normal-damage state | 33 |
| manual control | 9 |

Most frequent individual blockers now include:

- Crown `원 포 올 2` reload-speed cadence state — 7 squads;
- Crown `로얄 에타이어 4` ATK-damage delivery via `heal_received` — 7 squads;
- Little Mermaid `세이렌 송 2` ammo-charge cadence state — 6 squads;
- Maid Mast `파이레츠 스피릿 2` reload-speed cadence state — 5 squads;
- Privaty `EX 매거진 2/3` reload/max-ammo cadence states — 4 squads each;
- Rapi : Red Hood `부착형 유탄` `element_code_override` unresolved normal state — 4 squads.

Crown `로얄 에타이어 4` remains intentionally deferred because correct support
requires the larger HP/heal/lifesteal -> `heal_received` event model described in
the handoff. The next broad pressure point is therefore dynamic cadence/shot-state
coverage, not Fast ranking.

## Why this corpus was chosen

The existing optimizer was designed around expensive Moris calls and contains
search-budget/candidate-reduction heuristics. Using only its survivors for the
first Fast validation could therefore confound two different errors:

1. candidate-generation/pruning bias inherited from the Moris-cost era;
2. Fast Engine scoring/ranking error.

The probe bypasses that optimizer entirely. Squad memberships come from the
public `context.snapshot.SQUADS` corpus, but snapshot-specific build/config/enemy
overrides are discarded. Synthetic `test_*`/non-five-person fixtures and duplicate
ordered squads are removed. All remaining squads are rebuilt and evaluated under
one common scenario:

- public `context.spec` default build;
- 180 s;
- first burst at 3 s;
- deterministic `rng_mode=expected`;
- default patternless enemy (`def=31784`, no element, no core, no parts/windows).

This produces 24 unique real five-person ordered squads.

## Historical first measured result

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

At that historical checkpoint the ranking diagnostic still conflated blocked
Top-N rows with catastrophic scored false negatives. That metric has since been
split. The post-spawn rerun above confirms that blocked Top-N rows now contribute
to `top_n_coverage_gap_rate`, while `catastrophic_false_negative_rate` counts only
certified rows that Fast actually ranks outside the shortlist.

## Original blocker inventory

Counts below are effect/blocker occurrences, not distinct squads:

| blocker family | occurrences |
|---|---:|
| cadence / shot-shape | 109 |
| skill state delivery | 108 |
| normal-attack state delivery | 92 |
| unresolved normal-damage state | 33 |

Frequent repeated examples included:

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

- The audit removes the current optimizer/candidate generator from the causal
  chain.
- The standardized scenario removes snapshot-specific operating/enemy/build
  differences.
- The current bottleneck for realistic broad ranking is **Fast certification
  coverage**, especially dynamic cadence and state-delivery paths.
- Static spawn lifecycle support removed the intended Little Mermaid `거품`
  coverage blocker.
- Fail-closed behavior is working as designed: unsupported comparison-critical
  states are not silently turned into zero damage.
- Coverage gaps and true scored ranking misses are now separate diagnostics.

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

1. Keep candidate generation bypassed while diagnosing Fast parity/root causes.
2. Continue expanding generalized coverage from the blocker inventory; do not add
   character-name exceptions.
3. Keep large HP/heal/lifesteal -> `heal_received` work deferred until smaller
   independent mechanisms are exhausted.
4. Treat the dynamic cadence family as the next major coverage pressure point,
   but decompose it before implementation rather than opening all cadence states
   at once.
5. Re-run this fixed standardized corpus after each meaningful coverage expansion.
6. Once a non-trivial certified subset exists, report pairwise ordering and
   Top-N-in-Top-K **only within that supported subset**, while continuing to report
   blocked Moris Top-N rows separately.
7. Before production pruning, build a larger optimizer-independent stratified
   corpus. Only after that attach the current candidate generator and decompose
   end-to-end loss as:

   `source universe -> candidate generation -> Fast coverage -> Fast ranking -> Moris shortlist`.

This ordering is specifically intended to prevent Moris-era search heuristics from
being misdiagnosed as Fast Engine errors.
