# LedgerLoop

LedgerLoop is a mock-first implementation of a cost-aware, memory-persistent loop orchestrator for multi-agent code-build-audit workflows.

Phase 1 intentionally uses deterministic fake provider adapters. The goal is to prove the local contracts before wiring real model APIs:

- bounded execution state machine
- explainable routing decisions
- hard budget enforcement (router estimates and ledger enforcement share one pricing formula)
- deterministic prompt bundle hashing
- scoped persistent memory with deduplication
- safety gate wired into the loop: dependency-changing tasks are rejected unless an approved isolated environment is active
- closed-loop repair: failure fingerprints are fed back into the next prompt, and the loop escalates to a stronger provider tier after the repair cap before blocking
- structured artifact tracking (builder edits, validation/audit results, final report)
- event logging for audit and future memory consolidation
- config file support (JSON or TOML) for budgets, safety policy, and providers

Run the tests with:

```bash
python3 -m unittest discover -s tests
```

Run a mock loop from the terminal:

```bash
PYTHONPATH=src python3 -m orchestrator "implement a small budget ledger improvement"
```

When installed as a package, the preferred CLI name is:

```bash
ledgerloop "implement a small budget ledger improvement"
```

Emit full JSON:

```bash
PYTHONPATH=src python3 -m orchestrator --json "audit the repair loop"
```

Simulate a repeated validation failure and watch the loop escalate through provider tiers, then block:

```bash
PYTHONPATH=src python3 -m orchestrator \
  --max-repair-attempts 1 \
  --fail-fingerprint validate:test:logic \
  "implement a feature with a repeated validation failure"
```

Run with a config file:

```bash
PYTHONPATH=src python3 -m orchestrator \
  --config my-config.json \
  "implement a small budget ledger improvement"
```

Use SQLite-backed memory and event persistence:

```bash
PYTHONPATH=src python3 -m orchestrator \
  --sqlite-path data/ledgerloop.db \
  "implement a small budget ledger improvement"
```

Example config (all sections optional; unset fields keep the mock defaults):

```json
{
  "project_id": "my-project",
  "budget": {"max_usd": 0.5, "max_repair_attempts": 2},
  "safety": {"allow_global_dependency_changes": false},
  "providers": {
    "my-model": {
      "provider": "anthropic",
      "pricing": {"input_per_million": 3.0, "output_per_million": 15.0},
      "supports_cache": true
    }
  }
}
```
