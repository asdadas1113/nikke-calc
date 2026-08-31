# Search-budget allocation study

This note records failure-driven benchmark evidence for how a fixed post-marginal
Moris-call budget should be split between discovering more five-member
memberships and exploring more ordered placements of memberships already found.
It is **not** a production-default lock.

Private account payloads, owned-character lists, and raw benchmark outputs remain
local-only. Only anonymized aggregate observations are recorded here.

## Guardrails

- One shared real-account marginal measurement is reused by every policy.
- Every compared policy receives the same number of **new candidate-team Moris
  calls**.
- Membership/placement policies may only change which squads Moris sees first.
  They do not add damage, popularity, meta, or position bonuses.
- Final five-team selection uses only actual Moris scores and the exact
  non-overlapping allocator.
- Explicitly position-sensitive character fixtures are interpreted separately
  from ordinary placement evidence. No character-name special case is introduced
  into the optimizer.

## Benchmark fixture

One anonymous 109-character account was evaluated with expected RNG and a common
20-second simulator fixture. The common marginal phase used 114 Moris calls and
covered the full owned roster.

The placement policy for the membership-width study was held fixed at the
experimental `structural-diverse` ordering. Only cheap membership-discovery widths
changed.

The original `1x` discovery widths were:

- single-team beam width: 24
- single-team global limit: 72
- allocation team beam width: 24
- allocation team options/state: 8
- allocation beam width: 12
- allocation output limit: 6

Sensitivity variants scaled those widths approximately by powers of two. This is
an experiment axis, not a hidden optimizer default.

## 11-call membership-width result

With exactly 11 post-marginal candidate Moris calls:

| Membership width | Final 5-team Moris total | Cheap discovery time |
| --- | ---: | ---: |
| 1/8x | 644.126M | ~0.07 s |
| 1/4x | 654.907M | ~0.29 s |
| 1/2x | 654.907M | ~0.9 s |
| 1x | 654.907M | ~3.4 s |
| 2x | 654.907M | ~13.4 s |

The 1/8x policy lost about 1.65% versus the common plateau, proving that membership
breadth can be made too narrow. By contrast, 1/4x through 2x all reached the same
five-team total at 11 calls, while cheap-search cost differed by almost two orders
of magnitude.

Interpretation: on this fixture, the useful membership-recall threshold lies
between the tested 1/8x and 1/4x policies. More breadth beyond 1/4x did not improve
the evaluated-pool answer at this budget.

## Call-budget curves

The same streams were extended to 30 logical candidate calls while preserving the
same common marginal evidence.

| Calls | 1/8x | 1/4x | 1/2x | 1x |
| ---: | ---: | ---: | ---: | ---: |
| 7 | 644.126M | 654.907M | 654.907M | 654.907M |
| 11 | 644.126M | 654.907M | 654.907M | 654.907M |
| 15 | 644.364M | 654.907M | 654.907M | 654.907M |
| 20 | 645.328M | 655.145M | 654.907M | 654.907M |
| 25 | 645.328M | 655.145M | 655.145M | 654.907M |
| 30 | 646.944M | **655.852M** | **655.852M** | 655.145M |

This rules out the possibility that 1/4x merely matched 1x at one lucky 11-call
point. In this fixture, 1/4x retained enough membership coverage while exposing
useful alternate placements earlier.

## Membership calls versus placement calls

For the 1x structural-diverse stream, the first 30 candidate calls contained 17
first-seen memberships and 13 additional placements. After a complete five-team
allocation was first available, no newly evaluated membership improved the total;
one later non-position-sensitive placement improved it by about 0.237M.

For the 1/2x stream, the first 30 calls contained 11 first-seen memberships and 19
additional placements. Two non-position-sensitive placement calls improved the
five-team total, by about 0.237M and 0.708M respectively. No first-seen membership
call improved the completed allocation in that window.

Some evaluated candidates in these exploratory streams contained the known
adjacent-ally position-sensitive exception character. None of the calls that
improved the final total contained that character, so the marginal placement
benefit above is not attributed to that exception case.

## Rejected naive exposure decoupling

The width result suggested that membership breadth and placement exposure might be
coupled too tightly, so a score-blind scheduler experiment kept the full `1x`
membership universe but split its ordered candidates into two categories:

- first placement of a newly seen membership;
- additional placement of an already seen membership.

A naive 1:1 category round-robin moved the first later placement improvement from
call 30 to call 25, but it also delayed the first complete five-team allocation
from call 7 to call 11. A second variant forced new memberships until five disjoint
membership sets were structurally available and only then switched to 1:1; it
still did not outperform the simpler 1/4x width policy.

Conclusion: do **not** add a new membership/placement scheduler from this evidence.
The simpler explicit width policy currently dominates the tested extra
complexity. Revisit decoupling only after a new failure shows that width control is
insufficient.

## Transfer check on ordinary memberships

To avoid basing placement conclusions on the position-sensitive exception fixture,
four additional real-account memberships without that character were evaluated
for 20 seconds. For each membership, raw permutation order and
`structural-diverse` were allowed the same first 12 placement evaluations.

Observed best-score differences for `structural-diverse` versus raw order were:

- +8.4%
- 0.0%
- +1.9%
- 0.0%

A fifth attempted membership was excluded because its Moris simulations exceeded
the local execution window before a comparable prefix completed.

This is positive transfer evidence, but still not enough to promote the policy to
a universal production default.

## Current benchmark candidate policy

For subsequent **benchmarking only**, the strongest failure-driven candidate from
this fixture is:

- membership widths: tested 1/4x configuration
- placement ordering: `structural-diverse`
- Moris remains the only final scorer

This is intentionally not a hidden default in optimizer code. Future boss/config
fixtures should either reproduce the result or reject it.

## Next decision

The next high-value test is not another arbitrary width increase. It is to run the
same explicit policy candidate on a materially different simulator/boss context
and compare it against at least the 1/8x, 1/2x, and 1x controls under equal new
Moris-call budgets.

If 1/4x repeatedly preserves final damage, it can become a caller-selected
benchmark baseline. If it fails, keep the widths boss/config dependent rather than
encoding a universal constant.
