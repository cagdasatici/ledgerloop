# LedgerLoop — Backlog

_Last updated: 2026-07-06_

Outstanding work only. When an item ships, remove it from this file and move the
capability into `docs/PROJECT_SUMMARY.md`.

## Final review record — full project (2026-07-06)

Reviewed everything through PR #2 (`395b855`, merged `4f3b4bb`). 68/68 tests,
CI green. PR #2 verified by re-probe: `curl … | sh`, `cat ~/.aws/credentials`,
and unknown commands now all block; the allowlist admits `git diff` etc.
Overall verdict: Phase 1 is a coherent, honest mock-first framework — bounded
loop, unified cost math, per-phase event audit trail, durable run identity,
and a default-deny action gate. Remaining findings are precision issues and
the known strategic gaps, all of which are specified as concrete work items
in `docs/IMPLEMENTATION_GUIDE.md`:
- Carried P2s: nobody honors `delay_for` (→ WI-5); failed attempts record
  zero budget (→ WI-5); cross-run budgets missing (→ WI-4); artifacts not
  persisted (→ WI-6); lesson-from-failure missing (→ WI-7).

## Next up

**Execute `docs/IMPLEMENTATION_GUIDE.md`, work items WI-4 through WI-8, in
order, one commit each.** The guide contains exact file changes, test names,
assertions, and commit messages. Summary of what it covers:

| WI | What |
|----|------|
| 4 | Cross-run budgets: persisted `cost_records` + `global_max_usd` cap at intake |
| 5 | Retry sleep hook (injectable sleeper) + per-attempt usage recording |
| 6 | Persist artifacts to SQLite |
| 7 | Lesson-from-failure memory consolidation on repair-blocked runs |
| 8 | Housekeeping: CHANGELOG, version 0.2.0, untrack runtime memory JSON |

## After the guide (not yet specified in detail)

- **Real provider adapters** — Claude / Gemini / OpenAI / local, behind
  `ProviderAdapter`, with interface contract tests before any real API call.
  Consumes: error taxonomy (done), action-time safety (done), retry sleeper
  (WI-5), per-attempt usage (WI-5).
- **Complexity triage upgrade** — routing quality is bounded by keyword
  heuristics; add a cheap-LLM triage fallback when heuristics are uncertain
  (the router that saves money may spend a little to decide).
- **Capability calibration** — record per-phase model/cost/outcome from
  `run_results` + `cost_records` and adjust the capability matrix from
  observed success rates instead of static declarations.
- Cache telemetry fields (read/write tokens, prefix hashes, provider cache
  status) from real provider metadata.
- Richer CLI: `ledgerloop run`, `ledgerloop memory list`, `ledgerloop events
  show`, `ledgerloop costs`.
- Approval-grant flow for high-risk actions (grant-and-proceed, not just
  block); command/tool sandbox abstraction; branch isolation policy.
- Memory curator classifier, embedding retrieval backend, promotion states
  (proposed → active → enforced → superseded → archived).
- Repair-plan diffing (explain *why* the loop is retrying).
- LICENSE decision before making the repo public (owner's call).

## Notes / conventions

- Tests use plain `unittest` and platform-default temp dirs. Do **not**
  hardcode `/private/tmp` — it breaks the Ubuntu CI runners.
- `ModelPricing.cost_for` is the single token→USD formula; new cost logic must
  route through it so router estimates and ledger enforcement stay in sync.
- Residual (accepted): concurrent same-item memory merges are last-writer-wins
  (refresh → merge → UPSERT is not one transaction). Fix only if multi-process
  writers become real.

## Done (moved to PROJECT_SUMMARY)

- ~~Publish to GitHub + CI on every push/PR.~~
- ~~Config file support (JSON/TOML) for budgets, safety, providers.~~
- ~~Wire the safety gate into the loop; reject dependency installs without an isolated env.~~
- ~~Bounded repair with tier escalation before pausing; closed-loop failure context in the prompt.~~
- ~~Unify router cost estimate with the budget ledger's pricing.~~
- ~~Structured artifact tracking for changed files / results / reports.~~
- ~~SQLite memory/event backend with migrations, WAL mode, busy timeout, and transactional writes.~~
- ~~SQLite review fixes: per-item memory UPSERTs, run/project-scoped events, persisted run results, event/memory redaction, CI `--sqlite-path` smoke.~~ Independently re-verified 2026-07-04.
- ~~Provider error taxonomy with retry policy and explicit repair-consumption semantics.~~ Reviewed 2026-07-04.
- ~~Action-time safety contract for builder-proposed actions.~~ Reviewed 2026-07-04.
- ~~Action classifier hardening: command actions default-deny unless explicitly low-risk; network execution and credential access high-risk.~~ Independently re-verified 2026-07-06 (attack probes block; allowlist and default-deny confirmed).
- ~~Safety classifier precision: word-boundary dependency terms, `ls` prefix tightening, token/secret access-shape matching.~~ Shipped 2026-07-06; false positives reproduced in review no longer block.
- ~~Capability matrix and per-phase provider binding.~~ Shipped 2026-07-06; routing now emits `phase_providers` and the loop binds plan/build/audit to the cheapest capable model per phase.
- ~~Planner output schema and plan-phase provider call.~~ Shipped 2026-07-06; the loop now records a `plan` artifact, budgets the planner call, and hands a `PlanSpec` into the build prompt payload.
