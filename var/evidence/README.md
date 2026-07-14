# Strategy evidence ledger

This directory is the cross-line evidence index. It does not replace or copy the
A/B/C/D source ledgers.

| File | Mutability | Meaning |
|---|---|---|
| `evidence_objects.jsonl` | append-only | One immutable root per C-line prediction. The root binds the A report identity, frozen B snapshot, frozen C action, and the stable D join key. |
| `evidence_reviews.jsonl` | append-only | Optional LLM or human interpretations bound to an exact `hydrated_facts_digest`. These rows are not facts and cannot change production rules automatically. |
| `evidence_summary_<trade_date>.md` | derived/replaceable | Human-readable as-of view with own-stock T+1/5/10/30, dynamic T+now, action review, and D evidence status. |
| `evidence_summary_latest.md` | derived/replaceable | Latest as-of view. |

## Truth rules

- The decision price is the frozen B snapshot price used by C. B and C prices
  must match or the root is rejected.
- A report trade date and stock identity must exist. If an old report was rerun
  and its `realtime` block belongs to a later date, that block is marked
  `a_realtime_drift` and is not used to rewrite the frozen B/C decision facts.
- Returns are the stock's own returns. Index excess is retained only as an audit
  field.
- T+now is rebuilt from every mature C result and has no T+30 ceiling.
- D joins by `(target_trade_date, code, plan_version)` and never reads user
  executions.
- LLM reviews are hypotheses/interpretations. A production change requires a
  separately reviewed, forward-only `rule_version`.

Manual idempotent rebuild:

```bash
PYTHONPATH=src python -m vaxstock.services.evidence_ledger --as-of YYYYMMDD
```
