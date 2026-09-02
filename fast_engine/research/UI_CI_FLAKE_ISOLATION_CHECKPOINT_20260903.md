# UI CI flake isolation checkpoint — 2026-09-03

## Purpose

Classify the repeated `site/src/ui.test.ts` failure seen after the first Fast ranking checkpoint before continuing ranking validation.

The failing case was:

- `blocks a forged growth stage 1.5 outside the character rarity range`
- validation error text was present as expected
- `FakeClient.simulateCalls` was intermittently `1` instead of expected `0`

No site behavior or Moris calculator semantics were changed in this checkpoint.

## Static source separation

Compared `master` (`fb2fd9157aa14499daf6b9f185beb685d4393f90`) with Fast checkpoint `7838496a9e46d2cb9bbbe1d128a43976b44cb0c1`.

The Fast branch is ahead by Fast Engine / optimizer / docs / CI work, but the compare contained no `site/`, `calculator/`, or `data/` file changes. Therefore the repeated UI failure could not be attributed to a changed site/calculator/data source file in the Fast branch.

## Reproduction matrix

### 1. Master baseline, isolated 1.5 case

Temporary branch from exact master SHA.

- Node 22
- `npm ci`
- runtime sync
- only the `growth stage 1.5` Vitest case

Result: **PASS**.

### 2. Master baseline, full site suite

Same exact master baseline.

- `npm test -- --run`

Result: **385/385 PASS**.

### 3. Fast checkpoint, full site suite only

Temporary branch from exact Fast checkpoint `7838496a...`.

Result: **385/385 PASS**.

### 4. Fast checkpoint, bridge then full site suite

- Python 3.13
- Node 22
- `python scripts/test-bridge.py`
- `npm test -- --run`

Result: bridge **PASS**, site **385/385 PASS**.

### 5. Fast checkpoint, exact CI prefix then bridge/site

Replayed the normal CI sequence in one clean job:

- doclint
- all Fast CI groups
- Fast performance contract
- calculator unit tests + damage self-check
- optimizer unit tests
- working-tree inspection
- Node/npm setup
- bridge smoke
- full site suite

Results:

- all Python/Fast/calculator/optimizer checks: **PASS**
- working tree after the Python prefix: **clean** (`git status` and `git diff --name-only` empty)
- bridge: **PASS**
- site: **385/385 PASS**

Therefore there is no evidence that an earlier Python/Fast test mutates tracked or untracked repository state and causes the UI failure.

## Official CI rerun

The previously failed official workflow run `33683055919` was rerun without changing the checkpoint commit.

Attempt 2 result:

- doclint: PASS
- all Fast groups: PASS
- calculator tests: PASS
- optimizer tests: PASS
- bridge smoke: PASS
- browser site tests: **PASS**
- golden snapshot 29: **PASS**
- overall job: **SUCCESS**

The same commit and workflow that had failed the 1.5 case therefore later passed without a code change.

## Conclusion

Treat the earlier `growth stage 1.5` failures as an **intermittent UI-test timing/race flake**, not a Fast Engine source regression.

Evidence is stronger than a single retry:

1. no site/calculator/data source diff exists between master and the Fast checkpoint;
2. master isolated and full-site runs pass;
3. Fast site-only and bridge→site runs pass;
4. the exact Python→bridge→site CI sequence passes with a clean working tree;
5. the exact failed official CI run succeeds on rerun at the same commit.

This checkpoint does **not** claim the flaky UI test itself has been repaired. It only separates it from the Fast Engine ranking work. A future site-test hardening task may investigate asynchronous simulation timing around the in-range-but-non-integer `growthStage=1.5` case.

## Ranking consequence

The Fast ranking checkpoint remains valid. Coverage expansion stays paused.

Next ranking work should seek a **near-tie or actual order crossing** between the two currently certified public teams using already-supported static scenario inputs, rather than opening additional character mechanics.
