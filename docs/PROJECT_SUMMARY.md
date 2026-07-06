# LedgerLoop — Project Summary

_Last updated: 2026-07-06_

LedgerLoop is a mock-first loop orchestrator for multi-agent code-build-audit
workflows. Core principle: every agent loop must be **bounded, cost-aware,
memory-backed, auditable, and safe** before it is connected to real LLM
providers.

## Status

**Phase 1 complete and hardened.** All ten minimum acceptance criteria from the
functional spec are met. Published at
[github.com/cagdasatici/ledgerloop](https://github.com/cagdasatici/ledgerloop)
(private) with GitHub Actions CI (Python 3.9 / 3.11 / 3.13). 60 unit tests
passing locally.

## Architecture

Deterministic fake provider adapters throughout — no real API calls yet. Source
under `src/orchestrator/`:

| Module | Responsibility |
|--------|----------------|
| `loop.py` | Bounded execution state machine: intake → route → intake safety gate → resolve memory → plan → execute provider with retry policy → action-time safety gate → validate → audit → repair/escalate → consolidate → report. |
| `router.py` | Deterministic routing by intent, risk, and complexity. Emits a USD estimate computed from the same pricing the ledger enforces. |
| `budget.py` | Budget ledger with hard spend/token circuit breakers; estimates before calls, records actuals after. |
| `config.py` | Config contracts + `load_config`/`config_from_dict` (JSON/TOML). `ModelPricing.cost_for` is the single token→USD formula. |
| `memory.py` | JSON-backed memory with dedupe, versioning, supersession, scoped retrieval. |
| `prompts.py` | Five-section deterministic prompt builder with full and cacheable-prefix hashes. |
| `providers.py` | Provider adapter interface, deterministic `FakeProviderAdapter`, provider error taxonomy, and retry policy. |
| `safety.py` | Intake risk classification plus execution-time `ProposedAction` gating for commands, diffs, installs, and other builder-proposed actions. Command actions are default-deny unless positively classified as low risk. |
| `artifacts.py` | Structured artifact registry (builder edits, validation/audit results, report) with content hashes. |
| `events.py` | Structured, timezone-aware loop event log. |
| `sqlite_store.py` | SQLite-backed memory and event persistence with schema migrations, WAL mode, busy timeout, transactional memory UPSERTs, project/run-scoped events, and persisted run results. |
| `cli.py` | CLI for running mock loops (`--config`, `--json`, budget/repair overrides, failure simulation). |

## What's implemented

- **Bounded loop** with per-fingerprint repair counters and a hard iteration cap.
- **Explainable routing** across 6 intents (audit, edit, test, release, explain, execute).
- **Hard budget enforcement** — spend and token breakers; a reserved headroom for the final report (`reserved_final_report_usd`, default 0.02).
- **Unified cost model** — router pre-flight estimate and ledger enforcement share `ModelPricing.cost_for`, so they cannot diverge.
- **Deterministic prompts** — stable full and cacheable-prefix hashes; cacheable prefix stays constant across repair iterations.
- **Scoped memory** — similarity-based retrieval that excludes irrelevant items; repeated lessons are merged, not appended.
- **Safety gate wired into the loop** — dependency-changing tasks are rejected unless an approved isolated environment (project-local venv / configured container) is active; a `safety_gate` event is always emitted.
- **Closed-loop repair + escalation** — failure fingerprint, message, and attempt counts are fed back into the next prompt; at the repair cap the loop escalates to the next stronger provider tier (ordered by input pricing) and resets the counter, blocking only when no stronger tier remains.
- **Provider error taxonomy** — timeout, rate-limit, auth, refusal, and malformed-output failures define retryability and whether they consume a repair attempt. Retry policy records structured retry events without sleeping inside the core loop.
- **Action-time safety** — builder-proposed actions are represented as `ProposedAction` records and pass through `SafetyPolicy.evaluate_action()` before the loop accepts them as executed.
- **Command safety hardening** — network execution, credential access, deploy/push/delete, dependency changes, and unknown command strings are blocked pending approval; only explicit low-risk command prefixes are allowed automatically.
- **Safety classifier precision fixes** — dependency-change detection now uses word boundaries, low-risk prefix matching no longer misclassifies `lsof` via `ls`, and token/secret mentions only block when they look like access shapes rather than normal engineering text.
- **Artifact tracking** — builder edits, validation/audit results, and the final report are recorded with content hashes; events carry `output_refs`; `LoopResult` exposes `artifacts` and `changed_artifacts`.
- **Config files** — JSON or TOML, layered onto the mock defaults; unknown keys ignored.
- **SQLite persistence** — opt-in SQLite backend for memories and event logs via `--sqlite-path`; JSON remains the bootstrap default. Memory writes use per-item UPSERTs, durable events are project/run scoped, and final run results are persisted.
- **Secret redaction** — event messages and memory summaries redact common API key/token/password shapes before durable persistence.
- **CI** — unit tests + CLI smoke runs on three Python versions.

## Running it

```bash
# tests
python3 -m unittest discover -s tests

# mock loop
PYTHONPATH=src python3 -m orchestrator "implement a small budget ledger improvement"

# full JSON output
PYTHONPATH=src python3 -m orchestrator --json "explain LedgerLoop architecture"

# watch repair escalate through tiers then block
PYTHONPATH=src python3 -m orchestrator \
  --max-repair-attempts 1 --fail-fingerprint validate:test:logic \
  "implement a feature with a repeated validation failure"

# with a config file
PYTHONPATH=src python3 -m orchestrator --config my-config.json "..."

# with SQLite-backed memory and event persistence
PYTHONPATH=src python3 -m orchestrator --sqlite-path data/ledgerloop.db "..."
```

## Docs

- `docs/spec-audit.md` — audit of the original concept spec.
- `docs/loop-orchestrator-functional-spec.md` — tightened functional spec + acceptance criteria.
- `docs/BACKLOG.md` — outstanding work, pruned as items ship.
