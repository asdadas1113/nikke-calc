# Placement-order study

This note records why ordered squad placement remains a search variable in the
optimizer prototype. It is benchmark evidence, not a production policy lock.
Private account payloads, character ownership lists, and raw outputs remain
local-only; only anonymized aggregate observations are recorded here.

## Guardrail

Placement heuristics may only decide **which ordered variants Moris sees first**.
They never add a damage bonus, replace Moris damage, or declare one placement
stronger without simulation.

A second guardrail applies to explicitly position-sensitive characters. Evidence
from a squad containing a character whose skill targets adjacent/leftmost/etc.
allies is treated as **exception evidence**, not as proof that every ordinary
squad needs the same degree of absolute-slot exploration. The current adjacent-
ally fixture is retained for later exception-policy design, but it must not by
itself justify changing the general placement algorithm.

For now this is an interpretation rule only. The optimizer does not contain a
character-name special case, does not award any position-sensitive bonus, and
does not automatically widen search because a particular character is present.
If later benchmarks show a material benefit, a generic metadata-driven exception
policy can be designed separately.

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

This result is deliberately classified as **position-sensitive exception
evidence**. It proves that burst-relative order is not an exact equivalence
relation, but it does **not** prove that ordinary squads without position-sensitive
targeting need the same absolute-slot search budget.

Moris contains order-sensitive target resolution such as adjacent allies,
first-N allies, leftmost filters, and stable squad-order tie breaking. Later
exception work should first identify those mechanics generically from simulator
metadata/skill structure, then benchmark whether extra placement exposure pays
for itself. Do not infer a global placement rule from this one fixture.

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
- on the position-sensitive fixture with fixed burst priority, raw order needed
  about ten variants to reach the near-optimal placement, while maximin slot
  diversity reached a 99.998% placement by the fourth variant.

The second bullet is retained as an exception-case diagnostic only. It must not be
used by itself to promote structural slot diversity for ordinary squads. This is
exactly the kind of transfer risk that forbids promoting one ordering from
intuition alone.

## First shared-marginal equal-call smoke

A later 20-second real-account smoke compared the three placement modes after one
shared 114-call marginal phase. Discovery widths were held fixed and each policy
received exactly **11 new candidate-team Moris calls**.

Observed five-team totals:

- `canonical-only`: **628.34M**
- `all-permutations` raw order: **628.34M**
- `structural-diverse`: **654.91M**
- `structural-diverse` vs canonical/raw: about **+4.23%**

The gain came from a different ordered placement of the same non-position-
sensitive membership: the selected squad improved from about **320.28M** to
**346.85M** while the other four selected squads were unchanged.

The watched adjacent-ally character appeared in exactly one evaluated candidate
for each policy, but was **not selected in any final five-team allocation**.
Therefore this particular +4.23% result is not attributed to the position-
sensitive exception fixture. The exception evidence is still kept separate and
must not be used to justify general absolute-slot widening.

This is positive transfer evidence for `structural-diverse`, not enough evidence
to make it the default. More memberships, bosses, durations, and candidate-call
budgets are still required.

## Next benchmark

Continue comparing `canonical-only`, `all-permutations`, and
`structural-diverse` using:

- the same account snapshot;
- the same boss/config and expected RNG;
- one shared marginal measurement phase;
- the same number of **new candidate-team Moris calls** per placement policy;
- the same exact non-overlapping final allocator.

Primary metric remains final five-team Moris damage. Also record candidate-call
allocation, cheap discovery runtime, whether additional ordered variants actually
change the selected five-team allocation, and whether a position-sensitive
exception fixture participated in the evidence.

When interpreting placement results, report position-sensitive fixtures separately
from ordinary fixtures. A material position-sensitive effect should be carried
forward as evidence for a later generic exception policy, not folded into the
ordinary-placement conclusion.
