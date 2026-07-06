## 0.2.0

- Tightened safety-classifier precision for dependency terms, low-risk prefixes, and token/secret mention handling.
- Added a capability matrix and phase-aware provider binding for plan, build, and audit.
- Added `PlanSpec`, a planner-model call, and structured plan handoff into the build prompt payload.
- Persisted provider-call cost records in SQLite and enforced optional cross-run budget caps.
- Added an injectable retry sleeper and recorded budget usage for failed provider attempts.
- Persisted run artifacts to SQLite so event artifact references survive process exit.
- Consolidated failure lessons into memory when repair exhaustion blocks a run.

## 0.1.0

- Initial mock-first LedgerLoop framework with bounded orchestration, deterministic prompts, persistent memory, safety gates, SQLite events, and CI.
