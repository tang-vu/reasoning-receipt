# Receipt profiles — recipes for common agent actions

Profiles are **conventions, not requirements**. The protocol core knows
nothing about them — they are shared vocabularies of node `kind`s and
edge `rel`s so receipts from different agents read consistently. Use the
pieces you need; a receipt never has to contain every stage.

Node kinds below are drawn from the open vocabulary (lowercase-snake).
Edges point **forward in the causal story** — `x →y produced` reads
"y was produced by x".

## Coding agent

```
intent ──produced──► decision ──invoked──► tool_call ──returned──► tool_result
policy ────────────► (decision evaluated_against policy)
evidence ──────────► (decision supported_by evidence)
approval ──────────► (decision approved_by approval)
decision ──caused──► execution ──produced──► outcome
```

```jsonc
{
  "subject": "code:fix-1234",
  "metadata": {"repo": "org/app", "base_sha": "0x…"},
  "nodes": [
    {"id": "intent", "kind": "intent",
     "payload": {"issue": "#1234", "request": "fix off-by-one"}},
    {"id": "policy", "kind": "policy",
     "payload": {"rules": ["no force-push", "tests must pass"]}},
    {"id": "repo-state", "kind": "evidence",
     "payload": {"base_sha": "0x…", "files_changed": ["src/x.py"]}},
    {"id": "diff", "kind": "decision",
     "payload": {"summary": "clamp index to len-1"}},
    {"id": "tests", "kind": "tool_call",
     "payload": {"cmd": "pytest -q"}},
    {"id": "test-result", "kind": "tool_result",
     "payload": {"passed": 148, "failed": 0}},
    {"id": "approval", "kind": "approval",
     "payload": {"by": "human:tangm"}},
    {"id": "commit", "kind": "execution",
     "payload": {"sha": "0x…"}},
    {"id": "outcome", "kind": "outcome",
     "payload": {"status": "merged"}}
  ],
  "edges": [
    {"from": "diff", "to": "policy", "rel": "evaluated_against"},
    {"from": "diff", "to": "repo-state", "rel": "supported_by"},
    {"from": "diff", "to": "tests", "rel": "invoked"},
    {"from": "tests", "to": "test-result", "rel": "returned"},
    {"from": "commit", "to": "approval", "rel": "approved_by"},
    {"from": "diff", "to": "commit", "rel": "caused"},
    {"from": "commit", "to": "outcome", "rel": "produced"}
  ]
}
```

## Support agent

```
request ──evaluated_against──► policy
decision ──supported_by──► evidence ──approved_by──► approval
decision ──invoked──► refund_call ──returned──► refund_result ──produced──► outcome
```

```jsonc
{
  "subject": "support:refund-approval",
  "metadata": {"workflow": "customer-support"},
  "nodes": [
    {"id": "request", "kind": "request", "payload": {"refund_usd": 49}},
    {"id": "policy", "kind": "policy", "payload": {"limit_usd": 100}},
    {"id": "history", "kind": "evidence",
     "payload": {"prior_refunds": 0, "account_age_days": 400}},
    {"id": "decision", "kind": "decision", "payload": {"approved": true}},
    {"id": "call", "kind": "tool_call",
     "payload": {"api": "refunds.create", "amount_usd": 49}},
    {"id": "result", "kind": "tool_result",
     "payload": {"refund_id": "re_…", "status": "succeeded"}},
    {"id": "outcome", "kind": "outcome", "payload": {"state": "resolved"}}
  ],
  "edges": [
    {"from": "decision", "to": "policy", "rel": "evaluated_against"},
    {"from": "decision", "to": "history", "rel": "supported_by"},
    {"from": "decision", "to": "call", "rel": "invoked"},
    {"from": "call", "to": "result", "rel": "returned"},
    {"from": "result", "to": "outcome", "rel": "produced"}
  ]
}
```

## Finance agent

```jsonc
{
  "subject": "finance:vendor-payment",
  "metadata": {"env": "testnet"},
  "nodes": [
    {"id": "intent", "kind": "intent", "payload": {"payee": "acme", "usd": 250}},
    {"id": "policy", "kind": "policy", "payload": {"daily_limit": 1000}},
    {"id": "quote", "kind": "evidence", "payload": {"rate": 1.0, "fee": 0.01}},
    {"id": "risk", "kind": "policy", "payload": {"sanctions_check": "clear"}},
    {"id": "decision", "kind": "decision", "payload": {"proceed": true}},
    {"id": "approval", "kind": "approval", "payload": {"by": "auto:limit<500"}},
    {"id": "tx", "kind": "execution", "payload": {"tx_hash": "0x…"}},
    {"id": "final", "kind": "state_change", "payload": {"balance_usd": 750}}
  ],
  "edges": [
    {"from": "decision", "to": "policy", "rel": "evaluated_against"},
    {"from": "decision", "to": "risk", "rel": "evaluated_against"},
    {"from": "decision", "to": "quote", "rel": "supported_by"},
    {"from": "tx", "to": "approval", "rel": "approved_by"},
    {"from": "decision", "to": "tx", "rel": "caused"},
    {"from": "tx", "to": "final", "rel": "produced"}
  ]
}
```

## Human-in-the-loop

Approvals are ordinary nodes — the protocol does not model pending
states. Emit two receipts, or include a `review` node linking the
approval's evidence:

```jsonc
{"id": "review", "kind": "review",
 "payload": {"queued_at": "…", "decided_at": "…"},
 "meta": {"channel": "slack"}}
```

## Guidance

- **Kinds** name the *role* a node plays, not the event that produced it.
- **`meta`** is the place for non-evidentiary context (source system,
  capture method) — it is committed but separate from `payload`.
- **Never embed chain-of-thought.** Capture observable events: inputs,
  tool calls, results, policy events, approvals, outcomes.
- Low-entropy payloads are dictionary-attackable through their hashes —
  see `docs/security-model.md` before committing secrets or PII.
