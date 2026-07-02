# LedgerLoop — Backlog

_Last updated: 2026-07-02_

Outstanding work only. When an item ships, remove it from this file and move the
capability into `docs/PROJECT_SUMMARY.md`.

## Next up (highest value)

1. **SQLite memory/event backend** — atomic writes, migrations, and concurrency
   safety, replacing the JSON store once the schema has stabilised.
2. **Real provider adapters** — Claude / Gemini / OpenAI / local, behind the
   existing `ProviderAdapter` interface. Add interface contract tests before
   any real API is called.
3. **Real token accounting hooks** — consume provider usage metadata where
   available instead of estimating from the mock adapter.

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
- Secret redaction before memory/event persistence.

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
