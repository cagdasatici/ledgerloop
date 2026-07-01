# LedgerLoop

LedgerLoop is a mock-first implementation of a cost-aware, memory-persistent loop orchestrator for multi-agent code-build-audit workflows.

Phase 1 intentionally uses deterministic fake provider adapters. The goal is to prove the local contracts before wiring real model APIs:

- bounded execution state machine
- explainable routing decisions
- hard budget enforcement
- deterministic prompt bundle hashing
- scoped persistent memory with deduplication
- environment safety checks
- event logging for audit and future memory consolidation

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

Simulate a repeated validation failure and watch the repair cap block the loop:

```bash
PYTHONPATH=src python3 -m orchestrator \
  --max-repair-attempts 1 \
  --fail-fingerprint validate:test:logic \
  "implement a feature with a repeated validation failure"
```
