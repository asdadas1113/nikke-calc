# Placement-order study

This note records why ordered squad placement remains a search variable in the
optimizer prototype. It is benchmark evidence, not a production policy lock.
Private account payloads, character ownership lists, and raw outputs remain
local-only; only anonymized aggregate observations are recorded here.

## Guardrail

Placement heuristics may only decide **which ordered variants Moris sees first**.
They never add a damage bonus, replace Moris damage, or declare one placement
stronger without simulation.

## Why canonical-only is unsafe

A short 2-second real-account smoke initially made several permutations of the
same five-member squad look identical. That was not enough evidence to treat
order as irrelevant.

The same membership was then evaluated exhaustively for 20 seconds across all
`5! = 120` ordered placements with expected RNG and otherwise identical Moris
inputs.

Observed aggregate result:

- minimum: about **126.96M**
- maximum: about **194.81M**
- max/min spread: about **+53.4%**
- distinct Moris totals: **36**

The membership contained one B1, one B2, and three B3 characters. The six
relative orders of those three B3 characters formed six large damage bands. This
matches Moris `BurstController`: candidates of the same burst stage are tried in
squad input order, and later cycles can use the next ready candidate when an
earlier one is still on cooldown.

Conclusion: the 2-second equality was a short-duration artifact. Canonical-only
placement is not a generally safe final search policy.

## Why burst priority alone is also insufficient

A second 20-second real-account fixture held the relative B3 order fixed and used
a character with an explicit adjacent-ally target. Only absolute squad placement
was varied across the 20 permutations compatible with that fixed B3 order.

Observed aggregate result:

- minimum: about **126.96M**
- maximum: about **129.82M**
- spread: about **+2.25%**

Therefore placements sharing the same burst-priority order are not generally
interchangeable. Moris also contains order-sensitive target resolution such as
adjacent allies, first-N allies, leftmost filters, and stable squad-order tie
breaking.

Conclusion: burst-relative order is useful exploration structure, not an exact
placement equivalence relation.

## Failure-driven candidate: structural-diverse ordering

The prototype now carries a third explicit placement mode alongside
`canonical-only` and `all-permutations`:

`structural-diverse`

It does **not** remove any permutation. It only changes exposure order under a
tight Moris-call budget:

1. if the legality object exposes static burst inspection, ordered placements are
   grouped by their static stage-1/2/3 candidate order;
2. those groups are exposed rank-round-robin so one burst-priority family cannot
   consume the early budget;
3. inside each group, a score-blind greedy maximin Hamming order prefers slot
   assignments that differ most from placements already exposed in that group;
4. every one of the original permutations remains available eventually.

The ordering work is cheap: a five-member / 120-permutation test costs roughly
1–2 ms per membership on the local benchmark environment, far below Moris
simulation cost.

## Early evidence, not a default

The new ordering is deliberately **not** the default yet.

Offline replay of the 20-second exhaustive results showed both sides:

- on the first fixture, canonical order already happened to be almost optimal, so
  raw permutation order was marginally better at several tiny budgets;
- on the positional fixture with fixed burst priority, raw order needed about ten
  variants to reach the near-optimal placement, while maximin slot diversity
  reached a 99.998% placement by the fourth variant.

This is exactly the kind of transfer failure that forbids promoting one ordering
from intuition alone.

## Next benchmark

Compare `canonical-only`, `all-permutations`, and `structural-diverse` using:

- the same account snapshot;
- the same boss/config and expected RNG;
- one shared marginal measurement phase;
- the same number of **new candidate-team Moris calls** per placement policy;
- the same exact non-overlapping final allocator.

Primary metric remains final five-team Moris damage. Also record candidate-call
allocation, cheap discovery runtime, and whether additional ordered variants
actually change the selected five-team allocation.
