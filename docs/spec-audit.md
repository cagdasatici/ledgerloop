# LedgerLoop Specification Audit

## Verdict

The pasted specification matches the project direction at a concept level: it names the three central concerns this project needs to solve, namely routing, persistent memory, and cache-aware prompt assembly. It is not yet strict enough to serve as an implementation contract for a safe multi-agent loop.

The draft should be treated as a seed, not the build spec. The corrected working spec is in [loop-orchestrator-functional-spec.md](loop-orchestrator-functional-spec.md).

## What Already Fits

- The objective is aligned with a multi-agent code-build-audit loop.
- The system correctly separates routing, memory resolution, and prompt assembly.
- The design recognizes prompt cache preservation as a first-class architectural constraint.
- The memory model includes project facts and a mistakes/learnings ledger, which are both essential for persistent improvement.
- The consolidation hook after each loop is the right place to convert failures into durable guardrails.

## Critical Gaps

### 1. The loop controller is underspecified

The draft describes routing and prompt construction, but not the actual orchestration loop. A multi-agent system needs explicit loop states, stop conditions, retry limits, handoff contracts, and artifact tracking.

Required correction: define an execution state machine covering intake, routing, memory resolution, execution, validation, audit, repair, memory consolidation, and final reporting.

### 2. Safety is only implied

The objective says "safely automates," but the draft does not specify sandboxing, tool permissions, branch isolation, destructive-command controls, secret handling, or human approval gates.

Required correction: safety policy must be a core subsystem, not an implementation detail.

### 3. Cost awareness lacks enforceable accounting

The router is described as reading quota limits and costs, but no budget ledger, token estimator, actual usage recorder, cache discount model, or hard cutoff behavior is defined.

Required correction: add project, daily, run, and step budgets; record estimated and actual token usage; require graceful downgrade or pause when budget is exhausted.

### 4. Routing rules are too brittle

The example router uses keyword checks such as "git" or "audit." That is useful as pseudocode, but it will misroute ambiguous or high-risk tasks.

Required correction: routing should use a policy matrix based on task intent, risk, complexity, context size, required tools, confidence, budget availability, and user override.

### 5. Cache strategy conflicts with frequently changing memory

The draft puts the learnings ledger above the cache boundary. Since the ledger changes after loop iterations, it can invalidate the provider cache.

Required correction: split memory into stable cacheable summaries and dynamic retrieved facts. Use deterministic serialization and provider-specific cache controls where available. Treat cache preservation as best-effort, measured behavior, not a guarantee.

### 6. Memory lifecycle is not fully defined

The draft says the ledger deduplicates and updates itself, but the maintenance section says to append new rules. Those instructions conflict.

Required correction: define create, update, supersede, archive, deduplicate, and enforce states. Each memory item needs provenance, confidence, scope, status, timestamps, and evidence.

### 7. Provider/model names are too hard-coded

The draft names Claude, Google Antigravity, Codex, and specific model-like labels directly in the architecture. Provider catalogs, names, capabilities, and prices change.

Required correction: model choices must be config-driven through provider adapters. The spec should describe capability tiers, not depend on fixed model names.

### 8. Codex is not the same kind of backend as a text model API

The draft lists Codex beside model APIs. In this project, Codex should be represented as a coding agent/tool executor, while model APIs are reasoning or generation backends.

Required correction: distinguish "agent roles" from "LLM providers." A role may use one or more providers plus tools.

### 9. The datastore needs concurrency and migration rules

Flat JSON is acceptable for an early prototype, but multi-agent loops need atomic writes, locks, migrations, and queryable memory.

Required correction: define JSON as the bootstrap backend and SQLite as the preferred durable local backend.

### 10. Acceptance criteria are missing

The draft does not say how to know the orchestrator works.

Required correction: add tests for routing, budget enforcement, prompt determinism, cache-block stability, memory dedupe, safety gates, and loop termination.

## Recommended Build Priority

1. Implement the data contracts first: task envelope, routing decision, budget ledger, memory item, prompt bundle, agent result, and loop event.
2. Build a deterministic local runner with fake provider adapters before calling real APIs.
3. Add safety gates and cost enforcement before adding autonomous repair loops.
4. Add memory consolidation only after execution/audit artifacts are structured enough to trust.
5. Add real provider adapters behind config once the local loop is testable.

## Second-Pass Edge Cases Applied

Additional review feedback identified three implementation risks worth turning into hard requirements:

- Auditor-builder thrashing: the working spec now requires per-failure repair counters, failure fingerprints, and escalation or pause behavior after the repair limit is reached.
- Memory merge ambiguity: the working spec now defines explicit deduplication mechanics, version increments, supersession links, and event-log evidence for merge decisions.
- Environment leakage: the working spec now requires approved virtual environment, project-local environment, or container validation before dependency installation.

One point from the review was intentionally not adopted as a guarantee: cache savings must be measured from provider metadata, not promised as a fixed percentage. The working spec preserves deterministic cache candidates, but treats cache behavior as an optimization rather than a correctness guarantee.

## Fit Assessment

Current draft fit: partial.

After applying the corrected working spec: strong fit for a cost-aware, memory-persistent, cache-conscious multi-agent Loop Orchestrator.
