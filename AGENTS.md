# LedgerLoop — working instructions

## Durable constraints

Mock-first bounded build/audit execution loop. Fake-provider success is not useful production code generation or measured cost saving. `ModelPricing.cost_for` is the single token-to-USD formula. Preserve hard budgets, per-attempt accounting, bounded repair/escalation, durable scoped memory and artifacts, and default-deny action safety. Temporary test paths must be platform-neutral. Same-item memory merge is documented last-writer-wins; do not call it a multiwriter transaction. Switchboard is an optional router dependency via the adapter contract, not a reason to duplicate its learning system here. No real provider calls or public licensing claims without evidence/authorization.

## Efficient working loop

- For orientation or continuation, read [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md), then only the linked section relevant to the task. For a precise edit, inspect the named code and nearby tests first. Historical reviews are references, not a startup reading list.
- Search filenames with `rg --files`, then symbols with scoped `rg -n`. Read bounded sections; exclude dependencies, generated output and runtime/private data unless needed.
- Preserve existing working-tree changes. Use the smallest coherent change and focused verification first; run the full required gate before declaring completion. Do not repeat successful checks without a new change or unresolved concern.
- Default to one agent. Delegate only when requested and the independent work justifies its context cost. Keep completion evidence concise: result, relevant checks, remaining blocker.
- Update the current context when a milestone changes; replace stale summaries and link evidence instead of appending another review essay. Dates and test counts are snapshots, not permanent guarantees. Markdown guidance does not set model, effort, billing or hard token limits.

## Verification

```sh
PYTHONPATH=src python3 -m unittest discover -s tests
```

Run only checks relevant to the change, then any required release gate. Report environment limitations and failed checks explicitly.
