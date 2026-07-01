# LedgerLoop Functional Specification

## Objective

Build a local orchestration framework that coordinates multiple agent roles for code-build-audit loops while enforcing cost budgets, preserving useful project memory, and assembling prompts in a cache-aware, deterministic way.

The orchestrator must optimize for:

- Correctness: each loop step has explicit inputs, outputs, validation, and stop conditions.
- Safety: tool execution is sandboxed, auditable, and gated by risk.
- Cost control: routing decisions account for budget, quota, context size, and model capability.
- Persistent learning: project facts and lessons are deduplicated, scoped, versioned, and retrieved only when relevant.
- Cache preservation: stable prompt sections are serialized consistently and separated from turn-specific payloads.

## Core Concepts

### Agent Roles

Agent roles describe work responsibilities. They are not the same as model providers.

- Router: classifies task intent, risk, complexity, and cost profile.
- Planner: breaks a task into executable steps.
- Builder: edits code or project artifacts.
- Auditor: reviews implementation, tests, security, and goal fit.
- Memory Curator: converts validated outcomes into durable memories.
- Reporter: summarizes actions, verification, costs, and remaining risks.

Each role may use a different provider adapter, local heuristic, or toolchain depending on routing policy.

### Provider Adapters

Provider adapters hide vendor-specific API details behind a common interface.

Each adapter must declare:

- provider name
- model id
- supported modalities
- context window
- cache support
- token pricing or local cost estimate
- rate limits and quota source
- tool-use support
- streaming support
- failure and retry policy

Model IDs, prices, and quotas must come from configuration, not hard-coded source.

### Task Envelope

Every loop starts with a structured task envelope:

```json
{
  "task_id": "task_20260626_0001",
  "project_id": "loop-orchestrator",
  "user_goal": "Implement a feature safely",
  "requested_mode": "auto",
  "risk_tolerance": "normal",
  "budget": {
    "max_usd": 2.0,
    "max_input_tokens": 200000,
    "max_output_tokens": 50000,
    "max_repair_attempts": 3
  },
  "constraints": [],
  "artifacts": [],
  "created_at": "2026-06-26T00:00:00Z"
}
```

## Execution State Machine

The orchestrator must execute a bounded state machine:

1. Intake: normalize the user request into a task envelope.
2. Route: select agent roles and provider tiers based on policy.
3. Resolve Memory: retrieve relevant project facts, constraints, and active lessons.
4. Plan: produce a step plan with expected artifacts and validation.
5. Execute: run the builder or other selected agent role.
6. Validate: run tests, static checks, schema checks, or artifact verification.
7. Audit: inspect behavior, safety, cost, and goal fit.
8. Repair: optionally loop back to Execute when validation or audit fails.
9. Consolidate Memory: update durable memory from confirmed outcomes.
10. Report: return final status, files changed, verification, cost, and residual risk.

Repair must be bounded per task and per sub-task. Each failed validation or audit result must produce a failure fingerprint built from the failing check, affected artifact, error class, and concise diagnostic. The orchestrator must track repair attempts for each fingerprint and stop repairing that fingerprint when `max_repair_attempts` is reached. At that point it may escalate to a stronger provider tier if budget and policy allow it; otherwise it must pause at a human gate or report the unresolved failure.

The loop must stop when one of these conditions is met:

- the task is complete and validated
- the iteration limit is reached
- budget is exhausted
- a safety gate requires human approval
- repeated failures match the same unresolved cause
- required external credentials or services are unavailable

## Routing Policy

Routing must consider:

- task intent: explain, edit, test, audit, refactor, research, release
- complexity: low, medium, high
- risk: low, medium, high
- required tools: filesystem, shell, browser, git, network, provider API
- context size: estimated prompt and artifact token load
- budget remaining: daily, run, and step budgets
- memory relevance: whether prior project facts or mistakes affect the task
- confidence: router confidence and fallback behavior
- user override: explicit requested provider, role, or budget

Routing output must be structured:

```json
{
  "tier": "medium",
  "roles": ["planner", "builder", "auditor"],
  "provider_preference": ["balanced-code-model", "cheap-fast-model"],
  "estimated_cost_usd": 0.18,
  "estimated_input_tokens": 42000,
  "estimated_output_tokens": 6000,
  "requires_approval": false,
  "reason": "Code edit with tests; moderate context and normal risk."
}
```

## Cost and Quota Controls

The orchestrator must maintain a budget ledger with:

- configured model prices
- estimated input and output tokens before dispatch
- actual input and output tokens after dispatch
- cache read/write token counts where providers expose them
- per-step, per-run, daily, and project totals
- quota reset time
- routing decisions and downgrade reasons

Budget enforcement rules:

- Do not dispatch a model call if the estimated cost exceeds the remaining hard budget.
- Prefer cheaper models for low-risk classification, formatting, and memory consolidation.
- Escalate to stronger models only when risk, complexity, or repeated failure justifies it.
- Reserve budget for validation, audit, and final reporting before spending the full run budget on execution.
- Pause and report when no safe route fits the remaining budget.

## Persistent Memory

The bootstrap implementation may use JSON files. The durable local implementation should use SQLite for atomic writes, locking, indexing, and migrations.

Memory types:

- Project Fact: stable architecture, framework, style, or domain information.
- Constraint: a rule that must be followed.
- Lesson: a mistake and correction learned from a validated event.
- Decision: an architectural or workflow choice with rationale.
- Artifact Summary: compact summary of important files, modules, or test suites.

Each memory item must include:

```json
{
  "id": "mem_0001",
  "project_id": "loop-orchestrator",
  "type": "lesson",
  "scope": "src/router.py",
  "summary": "Route high-risk code changes through an audit role before final reporting.",
  "status": "active",
  "version": 1,
  "confidence": 0.92,
  "source_event_ids": ["evt_0009"],
  "supersedes": [],
  "content_hash": "sha256:...",
  "tags": ["routing", "safety"],
  "created_at": "2026-06-26T00:00:00Z",
  "updated_at": "2026-06-26T00:00:00Z"
}
```

Memory lifecycle states:

- proposed: extracted but not yet trusted
- active: should be retrieved and applied
- enforced: represented by code, tests, or config
- superseded: replaced by a newer memory
- archived: retained for history but not retrieved by default

Memory updates must use semantic deduplication:

1. Search for similar active or enforced memories in the same scope.
2. Update or supersede existing memory when the new lesson refines it.
3. Create a new memory only when no existing item covers the lesson.
4. Attach evidence from the loop event that caused the update.

Deduplication mechanics must be explicit:

- Normalize summaries before comparison by lowercasing, trimming whitespace, and removing volatile identifiers.
- Use scope, type, tags, and normalized text overlap as the bootstrap candidate filter.
- Optionally use embeddings or vector similarity when an embedding provider is configured.
- Treat similarity thresholds as configuration, not source constants.
- When a candidate appears similar, ask the Memory Curator to classify the relationship as duplicate, refinement, contradiction, or unrelated.
- Merge duplicate or refinement memories by incrementing `version`, preserving `source_event_ids`, and writing superseded IDs into `supersedes`.
- Store the merge decision and evidence in the event log.

The system must never store secrets, private credentials, raw API keys, or unnecessary personal data in memory.

## Cache-Aware Prompt Assembly

Prompt assembly must produce deterministic prompt bundles. It must not rely on incidental dictionary ordering or ad hoc string conversion.

Prompt sections:

1. Static system contract: stable role instructions, safety rules, output schema.
2. Stable project summary: compact versioned project facts and enforced constraints.
3. Cacheable memory summary: stable, ordered summaries that change infrequently.
4. Dynamic retrieved context: task-relevant files, lessons, diagnostics, and prior events.
5. Current task payload: the turn-specific request and execution state.

Sections 1 and 2 should be the strongest cache candidates. Section 3 may be cacheable only when its version does not change. Sections 4 and 5 are dynamic.

The prompt builder must:

- serialize JSON with sorted keys and stable indentation
- include version hashes for cacheable sections
- track prompt hashes in the event log
- support provider-specific cache controls when adapters expose them
- measure cache behavior from provider usage metadata when available

Cache preservation is a measured optimization, not a correctness guarantee.

## Safety Policy

The orchestrator must classify actions by risk before execution.

Low-risk examples:

- read files
- run unit tests
- inspect git status
- format generated prompts

Medium-risk examples:

- edit project files
- install dependencies in the project environment
- start local services
- run integration tests with local writes

High-risk examples:

- network calls
- credential access
- production or cloud access
- destructive filesystem operations
- git push, release, deploy, or irreversible migration

High-risk actions require explicit policy approval or user approval. All actions must be logged with command, working directory, result, duration, and artifact references.

Dependency changes require environment isolation. Before installing packages or modifying dependency lockfiles, the orchestrator must verify that the project is running inside an approved virtual environment, project-local tool environment, or configured container. Global package installation is high-risk and must require explicit approval.

## Event Log

Every loop step must append a structured event:

```json
{
  "event_id": "evt_0010",
  "task_id": "task_20260626_0001",
  "state": "validate",
  "role": "auditor",
  "provider": "local",
  "iteration": 1,
  "repair_attempt": 0,
  "failure_fingerprint": null,
  "input_refs": ["artifact_0002"],
  "output_refs": ["artifact_0003"],
  "status": "succeeded",
  "cost": {
    "estimated_usd": 0.0,
    "actual_usd": 0.0
  },
  "created_at": "2026-06-26T00:00:00Z"
}
```

Event logs are the source of truth for cost accounting, auditability, and memory consolidation.

## Minimum Acceptance Criteria

The first working version is acceptable only when it can:

- run a full local loop using fake provider adapters
- route at least five representative task types with explainable decisions
- enforce a hard run budget
- build deterministic prompt bundles with stable hashes
- retrieve scoped memory and exclude irrelevant memory
- deduplicate a repeated lesson instead of blindly appending it
- stop after a configured iteration limit
- stop or escalate after the configured repair-attempt limit for one failure fingerprint
- reject dependency installation when no approved isolated environment is active
- produce a final report with state transitions, validation results, changed artifacts, and cost summary

## Phase 1 Execution Plan

Phase 1 must be mock-first. No real provider API is required until the local contracts pass tests.

1. Implement configuration loading, task envelopes, the budget ledger, and hard budget circuit breakers.
2. Implement fake provider adapters that return deterministic responses and usage metadata.
3. Implement prompt assembly with stable section hashes and tests proving cacheable section hashes remain unchanged when only the current task payload changes.
4. Implement JSON-backed memory with deduplication scaffolding, then add SQLite once the schema stabilizes.
5. Implement the bounded loop runner with repair counters, event logging, and final reports.
6. Add real provider adapters only after the mock loop passes the minimum acceptance criteria.

## Suggested Initial File Layout

```text
src/
  orchestrator/
    __init__.py
    config.py
    loop.py
    router.py
    budget.py
    memory.py
    prompts.py
    providers.py
    safety.py
    events.py
tests/
  test_router.py
  test_budget.py
  test_memory.py
  test_prompts.py
  test_loop.py
data/
  memory/
    project_store.json
```

## Non-Goals for the First Version

- autonomous deployment
- production credential management
- remote cloud execution
- unbounded self-repair loops
- provider-specific optimization before the local contracts are tested
- storing full transcripts as long-term memory
