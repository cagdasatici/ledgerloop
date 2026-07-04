# LedgerLoop — Backlog

_Last updated: 2026-07-04_

Outstanding work only. When an item ships, remove it from this file and move the
capability into `docs/PROJECT_SUMMARY.md`.

## Next up (highest value)

1. **Real provider adapters** — Claude / Gemini / OpenAI / local, behind the
   existing `ProviderAdapter` interface. Add interface contract tests before
   any real API is called. Prerequisites, in order: provider error taxonomy
   (below), action-time safety (below).
2. **Real token accounting hooks** — consume provider usage metadata where
   available instead of estimating from the mock adapter.

## Strategic gaps (from 2026-07-04 review — bigger than any one module)

- **Safety must gate actions, not intake text.** `evaluate_task()` classifies
  the user's goal string by keyword match, once, at intake. That is fine for
  mocks but structurally insufficient for real providers: the *builder's
  proposed actions* (commands, diffs, installs) are what carry risk, and they
  don't exist yet at intake — a task phrased innocently can propose `pip
  install` or `git push` mid-loop and no gate fires. Design change: every
  proposed action passes through `SafetyPolicy` at execution time (the
  spec §231 already says "classify actions by risk before execution"); intake
  screening stays as a cheap pre-filter. This should shape the
  builder/auditor role contracts before adapters are written.
- **Cross-run budgets.** `BudgetLedger` is per-run and in-memory; cost records
  evaporate at process exit. The cost-awareness pillar needs a persisted
  `cost_records` table (SQLite now exists for this) plus daily/weekly/global
  caps checked at intake — otherwise 100 runs × $1 budget = unbounded spend.
- **Provider error taxonomy.** Adapters have no failure contract: timeouts,
  429s, refusals, malformed output. The loop currently knows only
  `BudgetExceeded` and validation failure. Define `ProviderError` classes,
  retry-with-backoff policy, and whether provider failure consumes a repair
  attempt — before the first real adapter, or every adapter invents its own.

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
- ~~SQLite review fixes: per-item memory UPSERTs, run/project-scoped events, persisted run results, event/memory redaction, and CI `--sqlite-path` smoke.~~
