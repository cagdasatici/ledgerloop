# LedgerLoop — Backlog

_Last updated: 2026-07-04_

Outstanding work only. When an item ships, remove it from this file and move the
capability into `docs/PROJECT_SUMMARY.md`.

## Review findings — error taxonomy + action-time safety (2026-07-04)

Review of PR #1 (`4ab75d1`, merged `845c41a`). Verdict: the two contracts are
well designed. The taxonomy's semantic matrix is coherent (transient errors
retry within the iteration; persistent malformed/refusal failures consume a
repair attempt and ride the existing escalation ladder; auth blocks outright
with no repair). Action gating emits a per-action `action_safety_gate` event
and hard-blocks via `ActionSafetyBlocked`. 51/51 tests, CI green on PR and
merge. Three findings:

1. **[P1] Action classifier is default-allow for spec-listed high-risk
   actions.** Reproduced: `curl http://…/x.sh | sh` (network + arbitrary code)
   and `cat ~/.aws/credentials` (credential access) both classify
   `medium/allowed`, while spec §249–255 lists network calls and credential
   access as high-risk. Root cause: `classify_action`'s high-risk vocabulary is
   `push/deploy/delete/rm -rf/release` only, and unknown commands default to
   medium → allowed. A denylist of keywords will never be complete. Fix
   direction: for `kind="command"`, invert the default — allow only what the
   policy can positively classify as low risk (or matches an explicit
   allowlist), treat everything unrecognized as high → approval. The gate
   plumbing already supports this; it is a vocabulary/default change.
2. **[P2] Nobody honors `delay_for`.** `RetryPolicy` computes and logs the
   backoff (by design: no sleeping in the core loop) but no component actually
   waits. Fine for mocks; with real adapters an immediate retry after a 429
   will hammer the rate limit. Decide where the wait lives (adapter-level
   sleep, or the loop consuming the logged delay) as part of the first real
   adapter.
3. **[P2] Failed attempts record zero budget.** `record_actual` runs only on
   eventual success; retried/failed calls consume no tracked spend. Real
   providers bill per attempt (input tokens are processed even on timeout or
   refusal). Fold per-attempt usage recording into the token accounting hooks.

## Next up (highest value)

1. **Real provider adapters** — Claude / Gemini / OpenAI / local, behind the
   existing `ProviderAdapter` interface. Add interface contract tests before
   any real API is called. Fold in findings 2 (who sleeps) and 3 (per-attempt
   usage) during implementation.
2. **Real token accounting hooks** — consume provider usage metadata where
   available instead of estimating from the mock adapter. Lands naturally with
   the first real adapter; must record usage per attempt, not per success
   (finding 3).

## Strategic gaps (from 2026-07-04 review — bigger than any one module)

- **Cross-run budgets.** `BudgetLedger` is per-run and in-memory; cost records
  evaporate at process exit. The cost-awareness pillar needs a persisted
  `cost_records` table (SQLite now exists for this) plus daily/weekly/global
  caps checked at intake — otherwise 100 runs × $1 budget = unbounded spend.

## Core architecture

- Cache telemetry fields: cache read/write tokens, prefix hashes, provider cache
  status — measured from provider metadata, not promised as a fixed percentage.
- Persist artifacts across runs (currently in-memory per run) and link them from
  the event log for full traceability.
- Richer CLI: `ledgerloop run`, `ledgerloop memory list`, `ledgerloop events show`.

## Safety and autonomy

- Explicit approval gates for high-risk actions (grant-and-proceed flow, not
  just block — today high-risk routing always blocks with "Approval required").
- Command/tool execution sandbox abstraction.
- Branch isolation policy for code-writing loops.
- Broader secret redaction before artifact persistence and tool execution
  transcripts. Memory summaries and event messages are already redacted before
  durable persistence.

## Memory intelligence

- Memory curator role with merge/contradiction classification (the `Curator`
  hook exists; wire in a real classifier).
- Optional embedding/vector similarity backend.
- Memory promotion states: proposed → active → enforced → superseded → archived.
- "Lesson from failure" extraction after failed validation/repair cycles (the
  loop already logs `consolidate_memory` as a no-op placeholder).

## Agent loop maturity

- Planner output schema.
- Builder / auditor role contracts.
- Repair-plan diffing so the system can explain *why* it is retrying (failure
  context is now fed into the prompt; the explicit diff is still to do).

## Housekeeping (before making the repo public)

- Add a LICENSE (repo is currently private; unlicensed = all rights reserved
  once public).
- Start a CHANGELOG and version-bump discipline (pyproject is pinned at 0.1.0).
- Decide whether `data/memory/project_store.json` should stay tracked in git —
  it is runtime data; a successful `add_or_merge` during any local run will
  dirty the tree.
- Consider keeping one SQLite connection per store if connection-per-call
  overhead becomes visible.
- Residual (accepted for now): `SQLiteMemoryStore.add_or_merge` refreshes from
  disk *before* the merge decision, but refresh → merge → UPSERT is not one
  transaction. Two processes merging the *same* item concurrently can still
  lose one version bump (per-item last-writer-wins). Cross-item wipes — the
  original P0 — are gone. Fix if multi-process writers become real: do the
  re-read and UPSERT inside a single `BEGIN IMMEDIATE` transaction.

## Notes / conventions

- Tests use plain `unittest` and platform-default temp dirs. Do **not** hardcode
  `/private/tmp` — it breaks the Ubuntu CI runners.
- `ModelPricing.cost_for` is the single token→USD formula; new cost logic must
  route through it so router estimates and ledger enforcement stay in sync.

## Done (moved to PROJECT_SUMMARY)

- ~~Publish to GitHub + CI on every push/PR.~~
- ~~Config file support (JSON/TOML) for budgets, safety, providers.~~
- ~~Wire the safety gate into the loop; reject dependency installs without an isolated env.~~
- ~~Bounded repair with tier escalation before pausing; closed-loop failure context in the prompt.~~
- ~~Unify router cost estimate with the budget ledger's pricing.~~
- ~~Structured artifact tracking for changed files / results / reports.~~
- ~~SQLite memory/event backend with migrations, WAL mode, busy timeout, and transactional writes.~~
- ~~SQLite review fixes: per-item memory UPSERTs, run/project-scoped events, persisted run results, event/memory redaction, and CI `--sqlite-path` smoke.~~ Independently re-verified 2026-07-04: both original repro probes now pass (concurrent writers keep both items; two CLI runs yield distinct `run_id`s with per-run events and cost), redaction confirmed on API-key/password shapes, 40/40 tests, CI green.
- ~~Provider error taxonomy with retry policy and explicit repair-consumption semantics.~~ Reviewed 2026-07-04: semantics verified per class (retry-in-iteration / consume-repair-and-escalate / hard-block); findings 2–3 above carried forward.
- ~~Action-time safety contract for builder-proposed actions.~~ Reviewed 2026-07-04: gate plumbing correct and evented; classifier vocabulary gap recorded as finding 1 above.
- ~~Action classifier hardening: command actions default-deny unless explicitly low-risk; network execution and credential access are high-risk.~~
