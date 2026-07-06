# LedgerLoop — Implementation Guide (Phase 2)

_Written 2026-07-06. Audience: an implementation agent (small/fast model).
Follow this document literally. When it conflicts with your own judgment,
follow the document. When something is genuinely impossible as written, stop
and report — do not improvise a different design._

---

## 0. Rules of engagement (read first, apply always)

1. **Repo root:** `/Users/cagdas/Documents/Loop_Orchestrator_CA`. Source in
   `src/orchestrator/`, tests in `tests/`.
2. **No third-party dependencies.** Standard library only. The project must
   keep working on Python 3.9, 3.11, and 3.13 (CI matrix). That means:
   - typing via `List`, `Dict`, `Optional` from `typing` (NOT `list[str]`).
   - no `match` statements, no `tomllib` outside the existing guarded import.
3. **Match house style:** dataclasses, `%`-formatting for strings (not
   f-strings), double quotes, docstrings on public classes/functions.
4. **Tests:** plain `unittest`. Every test file starts with the same 3-line
   `sys.path` bootstrap you see in `tests/test_loop.py`. Use
   `tempfile.TemporaryDirectory()` with NO `dir=` argument (a hardcoded
   `/private/tmp` broke Ubuntu CI once).
5. **After every work item:** run `python3 -m unittest discover -s tests` —
   the FULL suite, not just your new file. All tests must pass. Currently 56.
6. **One commit per work item**, using the commit message given in that work
   item. Do not combine work items in one commit.
7. **Docs stay in sync:** when a work item ships, (a) remove/strike its entry
   in `docs/BACKLOG.md` and add a one-line `Done` note there, (b) add the new
   capability to the "What's implemented" list in `docs/PROJECT_SUMMARY.md`.
   Do this in the same commit as the code.
8. **Do not refactor code unrelated to your work item.** Do not rename
   existing public classes, functions, dataclass fields, or event states.
   Existing tests define the contract — never change an existing test unless
   the work item explicitly says so.
9. Work items are ordered by dependency. **Do them in order.** WI-2 and WI-3
   are the core feature; do not skip WI-1 (it is small and unblocks nothing
   but has user-facing impact).

## 1. Codebase anchors (so you do not have to hunt)

| Thing | Where | Shape today |
|---|---|---|
| Routing decision | `src/orchestrator/router.py` | `RoutingDecision` frozen dataclass: tier, roles, provider_preference, estimated_cost_usd, estimated_input_tokens, estimated_output_tokens, requires_approval, reason, risk, complexity, intent |
| Router | same file | `Router` dataclass: cheap_models, balanced_models, strong_models, `pricing: Optional[Dict[str, ModelPricing]]`; method `route_task(task_description, user_override="")` |
| Provider config | `src/orchestrator/config.py` | `ProviderModelConfig`: provider, model_id, pricing, context_window, supports_cache, supports_tools, supports_streaming, modalities |
| Budget limits | same file | `BudgetConfig`: max_usd, max_input_tokens, max_output_tokens, max_repair_attempts, max_iterations, reserved_final_report_usd |
| Default mock config | same file | `default_config()` builds three fake models: `cheap-fast-model` (in 0.05/out 0.10), `balanced-code-model` (0.25/0.75), `strong-audit-model` (1.00/3.00) |
| Loop | `src/orchestrator/loop.py` | `LoopRunner.__init__(config, router, memory, providers, events, safety, retry_policy)`; `run(user_goal, task_id, validator, auditor)`; helpers `_select_provider`, `_stronger_provider`, `_execute_provider`, `_complete_provider_with_retry`, `_gate_proposed_actions`, `_handle_repair`, `_build_bundle`, `_result` |
| Provider errors | `src/orchestrator/providers.py` | `ProviderError` base with `kind`, `retryable`, `consumes_repair_attempt`, `retry_after_seconds`; subclasses Timeout/RateLimit/Auth/Refusal/MalformedOutput; `RetryPolicy(max_attempts, base_delay_seconds, max_delay_seconds)` with `can_retry`, `delay_for` |
| Safety | `src/orchestrator/safety.py` | `SafetyPolicy.evaluate_task(description, command, env)` intake gate; `evaluate_action(ProposedAction, env)` execution gate; term tuples `DEPENDENCY_TERMS`, `HIGH_RISK_TERMS`, `LOW_RISK_COMMAND_PREFIXES` |
| SQLite | `src/orchestrator/sqlite_store.py` | `SQLiteMixin._ensure_schema` (CREATE TABLE IF NOT EXISTS + `_ensure_column` for additive migration), `SCHEMA_VERSION = 2`, tables: ledgerloop_schema_migrations, memory_items, loop_events, run_results |
| Events | `src/orchestrator/events.py` | `EventLog(project_id, run_id)`, `append(task_id, state, role, provider, iteration, repair_attempt, failure_fingerprint, status, message, cost, input_refs, output_refs)`; `redact_text` |
| Artifacts | `src/orchestrator/artifacts.py` | `ArtifactStore.add(task_id, kind, content, summary, iteration)`; kinds today: edit, validation, audit, report; `CHANGED_KINDS = ("edit", "file")` |
| CLI | `src/orchestrator/cli.py` | flags: goal, --task-id, --config, --memory-path, --sqlite-path, --json, --events-out, --max-usd, --max-iterations, --max-repair-attempts, --fail-fingerprint, --fail-until |

Event states emitted today (do not remove any): intake, route, safety_gate,
resolve_memory, plan, provider_call, provider_error, provider_retry,
action_safety_gate, execute, validate, audit, repair, consolidate_memory,
report.

---

## WI-1 — Safety classifier precision fixes

**Why.** Verified 2026-07-06: (a) intake gate blocks innocent goals like
"improve the package structure" / "requirements of phase 2" / "installer
messages" because `DEPENDENCY_TERMS` matches substrings; (b) the low-risk
command prefix `"ls"` has no trailing space, so `lsof -i` classifies low;
(c) `HIGH_RISK_TERMS` contains bare `"token"`, so an edit described as
"improve token accounting" blocks. Over-blocking is the safe direction but
(a) and (c) create real friction.

**Files:** `src/orchestrator/safety.py`, `tests/test_safety.py`.

**Changes, exactly:**

1. Add at module top (after the existing imports): `import re`.
2. Replace the tuple `DEPENDENCY_TERMS` with a compiled regex using word
   boundaries, and a helper:

   ```python
   DEPENDENCY_RE = re.compile(
       r"\b(install|installs|installing|dependency|dependencies|lockfile|"
       r"requirements\.txt|pip|poetry|npm|yarn)\b"
   )

   def _mentions_dependency_change(text: str) -> bool:
       return bool(DEPENDENCY_RE.search(text))
   ```

   Notes: `requirements` alone is NOT in the pattern (too common a word) —
   only `requirements.txt`. `installer` will no longer match because of the
   word boundary. Keep the old name `DEPENDENCY_TERMS` removed; update both
   call sites (`evaluate_task`, `evaluate_action`) to call
   `_mentions_dependency_change(text)`.
3. In `LOW_RISK_COMMAND_PREFIXES`, replace `"ls"` with `"ls "` and `"pwd"`
   with `"pwd"` kept — but the matching already handles exact equality via
   `stripped_command == prefix.strip()`, so `ls` alone still classifies low
   while `lsof -i` no longer matches. Do the same for any other prefix that
   lacks a trailing space and is a word-prefix hazard (`"pwd"` is safe:
   `pwdx` is not a realistic proposed command, leave it).
4. In `HIGH_RISK_TERMS`, replace the bare `"token"` and `"secret"` entries
   with shapes that indicate access rather than mention: `"token="`,
   `"secret="`, `"secrets."`, `".token"`. Keep `"api_key"`, `"api-key"`,
   `"credential"`, `"credentials"` as they are.

**New tests** (append to `tests/test_safety.py`):

```python
def test_intake_allows_goals_that_merely_mention_packagey_words(self):
    policy = SafetyPolicy(project_root="/tmp/project")
    for goal in [
        "improve the package structure of the orchestrator",
        "write documentation for the requirements of phase 2",
        "refactor the installer message strings",
    ]:
        decision = policy.evaluate_task(goal, env={})
        self.assertTrue(decision.allowed, goal)

def test_intake_still_blocks_real_dependency_changes_without_env(self):
    policy = SafetyPolicy(project_root="/tmp/project")
    decision = policy.evaluate_task("pip install requests", env={})
    self.assertFalse(decision.allowed)

def test_lsof_is_not_lowlisted_by_ls_prefix(self):
    policy = SafetyPolicy(project_root="/tmp/project")
    action = ProposedAction("a", "command", "Check ports", "lsof -i :8080")
    decision = policy.evaluate_action(action, env={})
    self.assertFalse(decision.allowed)

def test_token_mention_in_edit_description_is_not_high_risk(self):
    policy = SafetyPolicy(project_root="/tmp/project")
    action = ProposedAction("a", "edit", "Improve token accounting math", "")
    decision = policy.evaluate_action(action, env={})
    self.assertTrue(decision.allowed)
```

**Definition of done:** the four new tests pass; the full suite passes; the
existing hardening tests (curl|sh blocked, `cat ~/.aws/credentials` blocked,
unknown command blocked) still pass unchanged.

**Commit message:** `Fix safety classifier precision: word-boundary dependency terms, ls prefix, token mentions`

---

## WI-2 — Capability matrix + per-phase provider binding (CORE FEATURE)

**Why.** Today `RoutingDecision.roles` is a label list; `_select_provider`
picks ONE provider for the whole run and every call is `role="builder"`. The
product thesis is: score the task, then bind each phase (plan / build /
audit) to the **cheapest model capable of that phase at that complexity** —
e.g. a strong model plans and audits while a cheap model implements.
Escalation-on-failure already provides the quality floor.

**Files:** `src/orchestrator/config.py`, `src/orchestrator/router.py`,
`src/orchestrator/loop.py`, `tests/test_router.py`, `tests/test_loop.py`,
`tests/test_config.py`.

### Step 2a — config.py

Add a `capabilities` field to `ProviderModelConfig`:

```python
capabilities: Dict[str, int] = field(default_factory=dict)
```

Semantics (put this comment in the code): score 0–3 per phase; 0 = do not
use, 1 = usable for low-complexity, 2 = solid for medium, 3 = strong enough
for high. Phases are exactly `"plan"`, `"build"`, `"audit"`.

In `default_config()`, set:

| model | plan | build | audit |
|---|---|---|---|
| cheap-fast-model | 1 | 1 | 1 |
| balanced-code-model | 2 | 3 | 2 |
| strong-audit-model | 3 | 2 | 3 |

In `_provider_from_dict`, `capabilities` needs no special handling (it is a
plain dict field and the existing "known keys" filter passes it through) —
but ADD a test proving a config file can set it (see tests below).

### Step 2b — router.py

1. Module-level constant:

   ```python
   # Minimum capability score a model needs for a phase, per routed tier.
   REQUIRED_CAPABILITY = {"low": 1, "medium": 2, "high": 3}

   PHASES = ("plan", "build", "audit")
   ```

2. `Router` gains one field:

   ```python
   capabilities: Optional[Dict[str, Dict[str, int]]] = None
   ```

   (model_id → phase → score; injected by LoopRunner the same way `pricing`
   already is.)

3. `RoutingDecision` gains one field (and its `to_dict` entry):

   ```python
   phase_providers: Dict[str, List[str]] = field(default_factory=dict)
   ```

   NOTE: `RoutingDecision` is `@dataclass(frozen=True)` — a mutable default
   requires `field(default_factory=dict)` and the field must come AFTER all
   non-default fields. Put it last.

4. In `route_task`, after `tier` is decided, compute:

   ```python
   phase_providers = self._phase_providers(tier)
   ```

   and pass it into the `RoutingDecision`.

5. New method on `Router`:

   ```python
   def _phase_providers(self, tier: str) -> Dict[str, List[str]]:
       """Cheapest-capable-first provider list per phase.

       For each phase, keep models whose declared capability for that phase
       meets REQUIRED_CAPABILITY[tier], sorted by input price ascending.
       If no model qualifies, fall back to all known models sorted by that
       phase's capability descending then price ascending, so the loop can
       still run (escalation and audit provide the quality floor).
       """
   ```

   Implementation rules:
   - If `self.capabilities` is `None` or empty, return `{}` (callers fall
     back to legacy single-provider selection).
   - Price for sorting comes from `self.pricing[model_id].input_per_million`
     (treat missing pricing as `0.0`).
   - Qualifying set: `capability >= REQUIRED_CAPABILITY[tier]` and
     `capability > 0`.
   - Sort qualifying models by `(input_price, model_id)` — model_id as
     tie-break keeps it deterministic.
   - Fallback sort: `(-capability, input_price, model_id)`.

   With the default config this yields, for tier `medium`:
   plan → `["balanced-code-model", "strong-audit-model"]`,
   build → `["balanced-code-model"]` (only balanced has build ≥ 2 at a
   lower price than strong; strong has build 2 so it also qualifies —
   result: `["balanced-code-model", "strong-audit-model"]`),
   audit → `["balanced-code-model", "strong-audit-model"]`.
   For tier `high`: plan → `["strong-audit-model"]`, build → fallback list
   (no model has build 3 except balanced — balanced build is 3, so build →
   `["balanced-code-model"]`), audit → `["strong-audit-model"]`.
   Check your implementation against these expected lists; they are also
   encoded in the tests below.

### Step 2c — loop.py

1. In `LoopRunner.__init__`, extend the default router construction to also
   inject capabilities:

   ```python
   self.router = router or Router(
       pricing={...as today...},
       capabilities={
           model_id: dict(provider.capabilities)
           for model_id, provider in self.config.providers.items()
       },
   )
   ```

2. Replace the single `provider = self._select_provider(routing)` call in
   `run()` with:

   ```python
   provider = self._select_provider_for_phase(routing, "build")
   audit_provider = self._select_provider_for_phase(routing, "audit")
   plan_provider = self._select_provider_for_phase(routing, "plan")
   ```

3. New method:

   ```python
   def _select_provider_for_phase(self, routing: RoutingDecision, phase: str) -> ProviderAdapter:
       preference = routing.phase_providers.get(phase) or routing.provider_preference
       for model_id in preference:
           if model_id in self.providers:
               return self.providers[model_id]
       return self._select_provider(routing)
   ```

   Keep `_select_provider` as the legacy fallback; do not delete it.

4. Record the bindings so they are auditable: in the existing `plan` event
   (`state="plan"`), set `provider=plan_provider.model_id`. In the existing
   `audit` event, set `provider=audit_provider.model_id` (it currently says
   `provider="local"` — change it; the local auditor callable still runs,
   but the event now names the model that WOULD audit / will audit once
   role contracts land). Update the existing test
   `test_full_mock_loop_succeeds` ONLY if it asserts on those provider
   fields (it does not today).

5. `_stronger_provider` stays exactly as it is (global price ladder). Do NOT
   scope escalation to the phase list in this work item.

### Step 2d — tests

Append to `tests/test_router.py`:

```python
def test_phase_providers_cheapest_capable_first_medium(self):
    config = default_config()
    router = Router(
        pricing={m: p.pricing for m, p in config.providers.items()},
        capabilities={m: dict(p.capabilities) for m, p in config.providers.items()},
    )
    decision = router.route_task("implement budget ledger tests")  # medium tier
    self.assertEqual(decision.phase_providers["build"][0], "balanced-code-model")
    self.assertEqual(
        decision.phase_providers["plan"],
        ["balanced-code-model", "strong-audit-model"],
    )

def test_phase_providers_high_tier_requires_strong_plan_and_audit(self):
    config = default_config()
    router = Router(
        pricing={m: p.pricing for m, p in config.providers.items()},
        capabilities={m: dict(p.capabilities) for m, p in config.providers.items()},
    )
    decision = router.route_task("audit the repair loop for safety regressions")  # high tier
    self.assertEqual(decision.phase_providers["plan"], ["strong-audit-model"])
    self.assertEqual(decision.phase_providers["audit"], ["strong-audit-model"])

def test_phase_providers_empty_without_capabilities(self):
    decision = Router().route_task("implement budget ledger tests")
    self.assertEqual(decision.phase_providers, {})
```

Append to `tests/test_loop.py`:

```python
def test_loop_binds_phases_to_capable_providers(self):
    runner = LoopRunner(config=default_config())
    result = runner.run("implement a small budget ledger improvement", task_id="task_phase")

    self.assertEqual(result.status, "succeeded")
    plan_events = [e for e in result.events if e["state"] == "plan"]
    audit_events = [e for e in result.events if e["state"] == "audit"]
    execute_events = [e for e in result.events if e["state"] == "execute"]
    self.assertEqual(plan_events[0]["provider"], "balanced-code-model")
    self.assertEqual(audit_events[0]["provider"], "balanced-code-model")
    self.assertEqual(execute_events[0]["provider"], "balanced-code-model")
```

Append to `tests/test_config.py`:

```python
def test_config_file_can_set_capabilities(self):
    config = config_from_dict(
        {
            "providers": {
                "mini-coder": {
                    "provider": "openai",
                    "pricing": {"input_per_million": 0.1, "output_per_million": 0.4},
                    "capabilities": {"plan": 1, "build": 2, "audit": 1},
                }
            }
        }
    )
    self.assertEqual(config.providers["mini-coder"].capabilities["build"], 2)
```

**Definition of done:** all new tests pass; ALL 56 pre-existing tests pass
unchanged (especially `test_repair_cap_escalates_to_stronger_tier_before_blocking`
and `test_full_mock_loop_succeeds`); `--json` output now contains
`routing.phase_providers`.

**Commit message:** `Add capability matrix and per-phase provider binding`

---

## WI-3 — Planner output schema and plan handoff

**Why.** The "strong model plans, cheap model implements" flow needs a real
handoff artifact: the plan phase must produce a structured `PlanSpec` that
the build prompt consumes. Today the plan event just says "Prompt bundle
assembled" and no planner model is ever called.

**Files:** new `src/orchestrator/plan.py`, `src/orchestrator/loop.py`,
`src/orchestrator/artifacts.py`, `src/orchestrator/__init__.py`,
new `tests/test_plan.py`, `tests/test_loop.py`.

### Step 3a — plan.py (new module)

```python
"""Planner output schema."""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class PlanSpec:
    """Structured plan handed from the plan phase to the build phase."""

    goal: str
    produced_by: str
    steps: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    acceptance: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "goal": self.goal,
            "produced_by": self.produced_by,
            "steps": list(self.steps),
            "constraints": list(self.constraints),
            "acceptance": list(self.acceptance),
        }


def plan_from_provider_text(goal: str, model_id: str, text: str) -> PlanSpec:
    """Build a PlanSpec from a (mock) provider response.

    Phase 1 mock: each non-empty line of the response becomes one step. Real
    adapters will emit structured output later; this function is the single
    seam where that parsing will live.
    """

    steps = [line.strip() for line in text.splitlines() if line.strip()]
    if not steps:
        steps = [text.strip() or "no plan produced"]
    return PlanSpec(goal=goal, produced_by=model_id, steps=steps)
```

### Step 3b — loop.py

In `run()`, at the existing plan stage (where the `plan` event is emitted),
BEFORE emitting that event:

1. Call the plan provider through the budget, mirroring `_execute_provider`
   but with `reason="plan"` and `role="planner"`:

   ```python
   plan_estimate = plan_provider.estimate_usage(prompt_bundle.full_prompt)
   plan_estimated_usd = self.budget.assert_can_spend(
       plan_provider.model_id, plan_estimate, "plan"
   )
   plan_response = plan_provider.complete(
       prompt_bundle.full_prompt, role="planner", metadata={"task_id": task_id}
   )
   self.budget.record_actual(
       plan_provider.model_id, plan_response.usage,
       reason="plan", estimated_usd=plan_estimated_usd,
   )
   plan_spec = plan_from_provider_text(
       user_goal, plan_provider.model_id, plan_response.text
   )
   ```

   Wrap ONLY the `plan_provider.complete(...)` call in
   `self._complete_provider_with_retry`-equivalent handling? NO — keep it
   simple: if a `ProviderError` escapes here, let the existing generic
   `except ProviderError` in `run()` NOT catch it (it is outside the loop
   body). Instead wrap the whole plan block in its own
   `try/except ProviderError` that reports `blocked` and returns, mirroring
   the `BudgetExceeded` block right below it in the iteration loop. A plan
   failure is a run failure; no repair.
2. Record the plan artifact:

   ```python
   plan_artifact = self.artifacts.add(
       task_id, "plan", plan_response.text,
       summary="Plan from %s." % plan_provider.model_id,
   )
   ```
3. Change the existing `plan` event: `provider=plan_provider.model_id`,
   `message="Plan produced with %d steps." % len(plan_spec.steps)`,
   `output_refs=[plan_artifact.artifact_id]`.
4. Hand the plan to the builder: in `_build_bundle`, add a parameter
   `plan_spec: Optional[PlanSpec] = None` and, when not None, include
   `"plan": plan_spec.to_dict()` inside `current_task_payload`. Update both
   `_build_bundle` call sites in `run()` to pass `plan_spec`. (The initial
   `_build_bundle` call happens BEFORE the plan exists — restructure so the
   ordering in `run()` becomes: build a PRELIMINARY bundle without plan →
   run plan phase on it → rebuild the bundle WITH the plan → emit plan
   event → iterate. The cacheable prefix is unaffected because the plan
   lands in `current_task_payload`, a non-cacheable section.)

### Step 3c — artifacts.py

No structural change needed; `"plan"` is just a new kind. Do NOT add it to
`CHANGED_KINDS`.

### Step 3d — exports and tests

Add `PlanSpec` and `plan_from_provider_text` to `src/orchestrator/__init__.py`
(imports + `__all__`, alphabetical).

New `tests/test_plan.py`:

```python
def test_plan_from_provider_text_splits_lines(self):
    spec = plan_from_provider_text("goal", "model-x", "step one\n\nstep two\n")
    self.assertEqual(spec.steps, ["step one", "step two"])
    self.assertEqual(spec.produced_by, "model-x")

def test_plan_from_empty_text_produces_placeholder(self):
    spec = plan_from_provider_text("goal", "model-x", "")
    self.assertEqual(spec.steps, ["no plan produced"])
```

Append to `tests/test_loop.py`:

```python
def test_plan_phase_calls_planner_and_records_artifact(self):
    runner = LoopRunner(config=default_config())
    result = runner.run("implement a small budget ledger improvement", task_id="task_planned")

    self.assertEqual(result.status, "succeeded")
    plan_artifacts = [a for a in result.artifacts if a["kind"] == "plan"]
    self.assertEqual(len(plan_artifacts), 1)
    plan_events = [e for e in result.events if e["state"] == "plan"]
    self.assertTrue(plan_events[0]["output_refs"])
    # budget now includes the plan call: 2 records for a 1-iteration run
    self.assertEqual(result.budget["records"], 2)
```

CAUTION: `test_successful_run_tracks_artifacts` asserts the artifact-kind
set equals `{"edit", "validation", "audit", "report"}`. This work item adds
`"plan"` — update that ONE assertion to
`{"plan", "edit", "validation", "audit", "report"}`. This is the only
existing-test change authorized in WI-3. Also check
`test_action_time_safety_blocks_builder_proposed_dependency_install`:
it asserts `len(provider_call_events) == 1`; the plan call does not emit a
`provider_call` event (only `_execute_provider` does), so it still passes —
verify, don't assume.

**Definition of done:** new tests pass; full suite passes with only the one
authorized assertion update; a `--json` run shows the plan inside
`events` → `plan` and artifacts.

**Commit message:** `Add planner output schema and plan-phase provider call`

---

## WI-4 — Cross-run budgets (persisted cost records + global caps)

**Why.** `BudgetLedger` dies with the process: 100 runs × $1 cap = unbounded
spend. The cost pillar needs per-call records persisted and a cross-run cap
checked at intake.

**Files:** `src/orchestrator/config.py`, `src/orchestrator/sqlite_store.py`,
`src/orchestrator/loop.py`, `src/orchestrator/cli.py`,
`tests/test_sqlite_store.py`, `tests/test_loop.py`.

**Changes:**

1. `BudgetConfig` gains one field: `global_max_usd: float = 0.0` — 0.0 means
   "no cross-run cap" (backward compatible).
2. `sqlite_store.py`: bump `SCHEMA_VERSION` to 3. In `_ensure_schema`, add:

   ```sql
   CREATE TABLE IF NOT EXISTS cost_records (
       record_id INTEGER PRIMARY KEY,
       project_id TEXT NOT NULL,
       run_id TEXT NOT NULL,
       task_id TEXT NOT NULL,
       provider_model TEXT NOT NULL,
       reason TEXT NOT NULL,
       input_tokens INTEGER NOT NULL,
       output_tokens INTEGER NOT NULL,
       cache_read_tokens INTEGER NOT NULL,
       cache_write_tokens INTEGER NOT NULL,
       estimated_usd REAL NOT NULL,
       actual_usd REAL NOT NULL,
       created_at TEXT NOT NULL
   )
   ```

   plus index `idx_cost_records_project_created ON cost_records
   (project_id, created_at)`.
3. `SQLiteEventLog` gains two methods:
   - `record_cost(task_id, provider_model, reason, usage, estimated_usd,
     actual_usd)` — INSERT one row (project_id/run_id from self, created_at
     `utc_now_iso()`).
   - `total_spend_usd() -> float` — `SELECT COALESCE(SUM(actual_usd), 0)
     FROM cost_records WHERE project_id = ?`.
4. `loop.py`: in `_execute_provider` and the WI-3 plan block, after
   `record_actual`, mirror the record durably when the event log supports it:

   ```python
   recorder = getattr(self.events, "record_cost", None)
   if recorder:
       recorder(task_id, provider.model_id, "execute", response.usage,
                record.estimated_usd, record.actual_usd)
   ```

   (Use `reason="plan"` in the plan block.)
5. `loop.py`: in `run()`, immediately after the intake event, enforce the
   cross-run cap:

   ```python
   if self.config.budget.global_max_usd > 0:
       spent = getattr(self.events, "total_spend_usd", None)
       if spent and spent() >= self.config.budget.global_max_usd:
           # emit report event status="blocked",
           # message="Cross-run budget exhausted." and return blocked result
   ```

   Follow the exact shape of the existing `requires_approval` block.
6. `cli.py`: add `--global-budget-usd` float flag, wired into `make_config`
   overrides like `--max-usd`.

**New tests** — `tests/test_sqlite_store.py`:

```python
def test_cost_records_accumulate_across_runs(self):
    # two SQLiteEventLog instances on one db, record_cost on each,
    # assert total_spend_usd() equals the sum
```

`tests/test_loop.py`:

```python
def test_cross_run_budget_blocks_at_intake(self):
    # build a SQLiteEventLog on a temp db, pre-record cost of 1.0 usd,
    # config with BudgetConfig(global_max_usd=0.5),
    # LoopRunner(events=that_log).run(...) -> status "blocked",
    # message contains "Cross-run budget"
```

Write both tests fully; follow the existing style in each file.

**Definition of done:** new tests pass, full suite passes, JSON-backed runs
(no SQLite) still work with `global_max_usd` set (cap silently skipped —
`getattr` returns None).

**Commit message:** `Add persisted cost records and cross-run budget cap`

---

## WI-5 — Retry sleep hook + per-attempt usage recording

**Why.** Two carried P2s: (a) `RetryPolicy.delay_for` is computed and logged
but nobody waits — real 429s would be re-hit instantly; (b) failed attempts
record zero budget, but real providers bill per attempt.

**Files:** `src/orchestrator/providers.py`, `src/orchestrator/loop.py`,
`tests/test_loop.py`.

**Changes:**

1. `RetryPolicy` gains a field:

   ```python
   sleeper: Callable[[float], None] = field(default=time.sleep)
   ```

   (`RetryPolicy` is `@dataclass(frozen=True)` — a callable default is fine
   with plain `field(default=...)`. Import `time`, and `Callable` from
   typing.) Add method:

   ```python
   def wait(self, error: "ProviderError", attempt: int) -> float:
       delay = self.delay_for(error, attempt)
       self.sleeper(delay)
       return delay
   ```
2. `loop.py` `_complete_provider_with_retry`: replace the bare
   `delay = self.retry_policy.delay_for(exc, attempt)` with
   `delay = self.retry_policy.wait(exc, attempt)` — the event message stays
   the same.
3. ALL existing tests that exercise retries must not sleep for real: in
   `tests/test_loop.py`, every `RetryPolicy(...)` construction gains
   `sleeper=lambda _s: None`. (There are two: the timeout test and the
   malformed-output test.) This IS an authorized existing-test change.
4. Per-attempt usage: `ProviderError` gains an optional field in
   `__init__`: `usage: Optional[UsageMetadata] = None` (import via module —
   careful: `providers.py` already imports `UsageMetadata` from budget).
   In `_complete_provider_with_retry`, when catching a `ProviderError` with
   `exc.usage is not None`, record it before deciding on retry:

   ```python
   self.budget.record_actual(provider.model_id, exc.usage, reason="failed_attempt")
   ```

   and mirror to `record_cost` with the same `getattr` guard as WI-4 if
   available. Note `record_actual` can itself raise `BudgetExceeded` — that
   is CORRECT behavior (a failed attempt that busts the budget must stop the
   run); do not swallow it.

**New test** (`tests/test_loop.py`):

```python
def test_failed_attempt_usage_is_recorded(self):
    config = default_config()
    providers = {m: FakeProviderAdapter(model_id=m) for m in config.providers}
    providers["balanced-code-model"] = FakeProviderAdapter(
        model_id="balanced-code-model",
        failures=[ProviderTimeoutError(
            "slow", "balanced-code-model",
        )],
    )
    # give the error usage metadata:
    providers["balanced-code-model"].failures[0].usage = UsageMetadata(
        input_tokens=500, output_tokens=0
    )
    runner = LoopRunner(config=config, providers=providers,
                        retry_policy=RetryPolicy(max_attempts=2, sleeper=lambda _s: None))
    result = runner.run("implement retry accounting", task_id="task_attempt_cost")

    self.assertEqual(result.status, "succeeded")
    reasons = [r.reason for r in runner.budget.records]
    self.assertIn("failed_attempt", reasons)
```

(`UsageMetadata` and `ProviderTimeoutError` are already imported in
`test_loop.py` — verify, add if missing.)

**Definition of done:** new test passes; full suite passes and completes in
under ~5 seconds (proving no real sleeping in tests).

**Commit message:** `Honor retry backoff via injectable sleeper; record failed-attempt usage`

---

## WI-6 — Persist artifacts to SQLite

**Why.** Artifacts are in-memory per run; the audit trail loses builder
output artifacts and reports as soon as the process exits, while events
reference their ids.

**Files:** `src/orchestrator/sqlite_store.py`, `src/orchestrator/loop.py`,
`tests/test_sqlite_store.py`.

**Changes:**

1. Bump `SCHEMA_VERSION` to 4; add table:

   ```sql
   CREATE TABLE IF NOT EXISTS artifacts (
       project_id TEXT NOT NULL,
       run_id TEXT NOT NULL,
       artifact_id TEXT NOT NULL,
       task_id TEXT NOT NULL,
       kind TEXT NOT NULL,
       ref TEXT NOT NULL,
       summary TEXT NOT NULL,
       iteration INTEGER NOT NULL,
       created_at TEXT NOT NULL,
       PRIMARY KEY (project_id, run_id, artifact_id)
   )
   ```
2. `SQLiteEventLog` gains `record_artifacts(artifacts: List[Dict])` —
   INSERT OR REPLACE all rows in one transaction; apply `redact_text` to
   `summary`.
3. `loop.py` `_result`: next to the existing `record_run_result` guard, add
   the same `getattr(self.events, "record_artifacts", None)` guard and call
   it with `self.artifacts.to_list()`.

**New test** (`tests/test_sqlite_store.py`): run the CLI `main` with
`--sqlite-path` (copy the shape of `test_cli_uses_sqlite_backend_for_events`),
then open a fresh connection and assert the `artifacts` table row count
equals `len(payload["artifacts"])` and every event `output_ref` beginning
with `art_` exists in the artifacts table.

**Definition of done:** test passes; full suite passes.

**Commit message:** `Persist run artifacts to SQLite`

---

## WI-7 — Lesson-from-failure memory consolidation

**Why.** `consolidate_memory` is a no-op placeholder; blocked runs teach the
system nothing. Failure fingerprints are the natural lesson seed and the
memory store already dedupes/merges.

**Files:** `src/orchestrator/loop.py`, `tests/test_loop.py`.

**Changes:**

1. In `run()`, just before the final report event, when
   `final_status == "blocked"` and `last_failure is not None` (a repair-cap
   block, not an approval/safety/budget block), create and store a lesson:

   ```python
   lesson = MemoryItem(
       id="mem_%s_%s" % (self.events.run_id, last_failure.failure_fingerprint or "unknown"),
       project_id=self.config.project_id,
       type="lesson",
       scope="global",
       summary="Repeated failure %s was not repairable within limits for goal: %s"
       % (last_failure.failure_fingerprint, user_goal),
       tags=["failure", "repair"],
   )
   merge = self.memory.add_or_merge(lesson)
   self.events.append(
       task_id, "consolidate_memory", "memory_curator",
       status="succeeded",
       message="Lesson %s (%s)." % (merge["memory_id"], merge["action"]),
   )
   ```

   Import `MemoryItem` from `orchestrator.memory` at the top of `loop.py`.
2. Guard: only when `self.memory` is not None (it never is — skip the guard)
   and do NOT do this for `requires_approval` / safety-gate / budget blocks
   (those return early before the loop body, so placing the code at the
   post-loop report site is sufficient — verify by reading `run()`).

**New test** (`tests/test_loop.py`):

```python
def test_blocked_repair_run_writes_failure_lesson(self):
    base = default_config()
    config = OrchestratorConfig(
        project_id=base.project_id,
        budget=BudgetConfig(max_repair_attempts=0, max_iterations=2),
        safety=base.safety,
        providers=base.providers,
    )

    def always_fail(iteration, response_text):
        return ValidationResult.failure("validate:test:logic", "still failing")

    runner = LoopRunner(config=config)
    result = runner.run("implement something unfixable", task_id="task_lesson",
                        validator=always_fail)

    self.assertEqual(result.status, "blocked")
    lessons = [i for i in runner.memory.items if i.type == "lesson"]
    self.assertEqual(len(lessons), 1)
    self.assertIn("validate:test:logic", lessons[0].summary)
```

NOTE: `runner.memory` here is an in-memory `MemoryStore` with `path=None`,
so `save()` is a no-op — safe.

Also verify the second blocked run of the same fingerprint MERGES rather
than duplicates (the ids differ per run, but `add_or_merge` matches on
summary similarity): add a second `runner2 = LoopRunner(config=config,
memory=runner.memory)` run in the same test and assert
`len([i for i in runner.memory.items if i.type == "lesson"]) == 1` still.

**Definition of done:** test passes; full suite passes; a normal succeeded
run still emits the existing no-op `consolidate_memory` event unchanged.

**Commit message:** `Write failure lessons to memory when repair blocks a run`

---

## WI-8 — Housekeeping (last, small)

1. **CHANGELOG.md** at repo root: start with `## 0.2.0` summarizing WI-1
   through WI-7 in one bullet each, and `## 0.1.0 — initial mock framework`.
   Bump `version` in `pyproject.toml` to `0.2.0`.
2. **Untrack runtime data:** add `data/memory/project_store.json` to
   `.gitignore`, run `git rm --cached data/memory/project_store.json`.
   The code path already handles a missing file (`MemoryStore.load` checks
   `os.path.exists`).
3. **LICENSE:** do NOT choose a license yourself. Add a `LICENSE` decision
   note to `docs/BACKLOG.md` housekeeping if not already there, and leave it
   for the repo owner.

**Commit message:** `Housekeeping: changelog, version bump, untrack runtime memory store`

---

## Final checklist (run after WI-8)

1. `python3 -m unittest discover -s tests` → everything green.
2. `PYTHONPATH=src python3 -m orchestrator --json "implement a small budget ledger improvement"` → status `succeeded`, `routing.phase_providers` present, artifacts include a `plan`.
3. `PYTHONPATH=src python3 -m orchestrator --sqlite-path /tmp/x.db "explain the architecture"` twice → second run still succeeds; `run_results` has 2 rows; `artifacts` table populated.
4. `git push` and confirm CI green on GitHub Actions.
5. `docs/BACKLOG.md` contains no entry for anything you implemented;
   `docs/PROJECT_SUMMARY.md` lists every new capability; both files'
   `_Last updated_` dates are current.
