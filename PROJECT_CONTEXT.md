# LedgerLoop — current context

This is a navigation snapshot, not a replacement for requirements or live evidence. Update it after a meaningful milestone; keep history in existing records.

## Snapshot — 2026-09-20

HEAD `22d68cc`, plus pre-existing changes to README/changelog/pyproject/loop/router/tests. Fresh **74 tests passed**. Phase 1's mock contracts are substantially delivered; the broader real-provider execution product is still early. No real-provider quality, cost, sandbox execution or multiwriter memory acceptance was established.

Built: bounded loop, unified pricing, deterministic prompt hashes, per-phase provider binding, plans, failed-attempt cost records, safety gates, repair lessons and SQLite artifact/event/memory persistence. Remaining: real adapters, execution/approval sandbox, trustworthy audit signal, cache telemetry, representative economic evaluation and owner license decision.

## Read only for the relevant task

| Task | Entry points / authority |
|---|---|
| Current scope/queue | `README.md`, `docs/BACKLOG.md` |
| Loop/repair | `src/orchestrator/loop.py`, `providers.py`, `tests/test_loop.py` |
| Budget/routing | `budget.py`, `router.py`, corresponding tests under `tests/` |
| Prompts/memory/storage | `prompts.py`, `memory.py`, `sqlite_store.py`, corresponding tests (all source paths under `src/orchestrator/`) |
| Contract/acceptance | Relevant section of `docs/loop-orchestrator-functional-spec.md` |
| Historical build detail | `docs/IMPLEMENTATION_GUIDE.md`, `docs/PROJECT_SUMMARY.md` only for the named requirement |

Next useful delivery: select one real adapter and a small fixed acceptance workload after resolving how execution, validation and cost evidence will be trusted. Keep Phase 1 complete-for-mocks distinct from end-to-end product completion. Check the existing dirty feedback-hook changes before modifying the integration.
