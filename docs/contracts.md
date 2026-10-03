# Message contracts

Agents in SwarmGuard never talk to each other in free text. Every message has a fixed shape, defined in a JSON Schema file under [`schemas/`](../schemas/). That shape is the contract.

## What a contract is

A contract is an agreement about what a message must look like: which fields exist, which are required, what type each one has and which values are allowed. Think of an alarm in a network management system. It always carries an identifier, a severity, the affected object and a timestamp, so any system that receives it knows where to find each piece of data without guessing.

## Why SwarmGuard uses them

- **Reject bad messages early.** An LLM can return something malformed. With a schema, the code rejects it before anyone acts on it.
- **Limit what untrusted text can do.** Logs and payment fields can contain text written by an attacker. Schemas set maximum lengths, allowed values and no extra fields, so such text cannot add new fields to a message.
- **Build and test agents independently.** Each agent can be tested with fixture messages, without running the others.
- **Keep an audit trail.** Structured messages are easy to record, search and replay.
- **Measure the system.** The evaluation harness can count severities, categories and confidence values because they are structured data.

## Contracts today

| Contract | Emitted by | Schema |
|----------|------------|--------|
| `SuspicionSignal` | Scout | [`suspicion_signal.schema.json`](../schemas/suspicion_signal.schema.json) |
| `HypothesisReport` | Investigator | [`hypothesis_report.schema.json`](../schemas/hypothesis_report.schema.json) |
| `CoordinatorDecision` | Coordinator | [`coordinator_decision.schema.json`](../schemas/coordinator_decision.schema.json) |
| `GuardianAction` | Guardian (Phase 4) | [`guardian_action.schema.json`](../schemas/guardian_action.schema.json) |

Messages link to each other by identifier, so one incident can be followed from end to end: a signal (`sig-...`) leads to a report (`rep-...`), then to a decision (`dec-...`) and finally to a proposed action (`act-...`).

## Example: SuspicionSignal

```json
{
  "signal_id": "sig-8f3a2c",
  "created_at": "2026-10-02T14:30:00Z",
  "source_agent": "scout",
  "severity": "HIGH",
  "summary": "Burst of failed card payments plus a request spike from one IP range",
  "affected_resources": ["api-gateway/payments"],
  "evidence": [
    {
      "source": "stripe_event",
      "reference": "evt_test_123",
      "excerpt": "charge failed: card_declined (42 in 5 minutes)"
    },
    {
      "source": "vpc_flow_logs",
      "reference": "flow-log-stream/2026-10-02T14"
    }
  ]
}
```

The values are made up, for illustration only.

## Example: CoordinatorDecision

```json
{
  "decision_id": "dec-7c2e41",
  "created_at": "2026-10-02T14:32:10Z",
  "source_agent": "coordinator",
  "signal_id": "sig-8f3a2c",
  "report_id": "rep-4b1d9e",
  "decision": "propose_action",
  "rationale": "Card testing is the leading hypothesis and two independent sources agree: declined charges in Stripe and a request spike from one range in the flow logs.",
  "confidence": 0.8,
  "corroborating_sources": ["stripe_event", "vpc_flow_logs"]
}
```

The decision is one of `discard`, `report` or `propose_action`. A `propose_action` decision must list at least two different evidence sources in `corroborating_sources`. This is the schema-level side of threat T2 in the [security model](security.md): a single forged source should not be enough to trigger containment.

## Example: GuardianAction

```json
{
  "action_id": "act-93d0a5",
  "created_at": "2026-10-02T14:32:40Z",
  "source_agent": "guardian",
  "decision_id": "dec-7c2e41",
  "mode": "dry_run",
  "action_type": "block_ip_temporary",
  "target": "203.0.113.0/24",
  "ttl_minutes": 60,
  "summary": "Block the IP range behind the declined-card burst for one hour, pending human approval.",
  "requires_human_approval": true
}
```

The schema encodes the safety principles from the [security model](security.md):

- `mode` can only be `dry_run`, and `requires_human_approval` can only be `true`. A message that says otherwise is rejected.
- `action_type` is a closed list of reversible actions. Anything else, such as deleting an instance, is not a valid message.
- `ttl_minutes` is required and capped at 1440 (one day), so every action expires.
- There is no free-form command field. The deterministic policy layer, not the message, decides how an action is carried out.

The Guardian arrives in Phase 4, but its contract is defined now so that the Coordinator and the policy layer can be designed against it. Documentation addresses (for example `203.0.113.0/24`) are used in examples.

## What a contract does not guarantee

- **A valid shape is not a true statement.** A message can match its schema perfectly and still contain false claims, whether from a confused model or from an attacker who shaped the input.
- **Free-text fields can still carry instructions.** A schema limits length and allowed fields, but it cannot tell whether a string such as `summary` contains an instruction. Code that reads those fields must treat them as data, never as commands.
- **Passing the tests means the shape is right, nothing more.** The tests below check shape and limits. They cannot tell whether a message is true or safe.

## Testing the contracts

Automated tests in [`tests/test_schemas.py`](../tests/test_schemas.py) run with pytest (see the README for how to run them). They check that:

- both schemas are valid JSON Schema documents;
- the evidence shape is identical in both schemas, so the decision to copy it stays safe;
- the example messages in `tests/examples/valid/` pass, and so does the example in this document;
- broken messages are rejected: missing or empty evidence, malformed identifiers, the wrong source agent, unknown values, confidence out of range, text that is too long, malformed timestamps and extra fields. For decisions this includes a proposal with fewer than two distinct sources. For actions it includes live mode, approval not required, an action type outside the list and a missing or too long expiry.

## Changing a contract

- A contract changes through a pull request that updates the schema, the examples in this document, the test examples under `tests/examples/` and the README or architecture docs in the same PR.
- Adding an optional field is usually safe. Removing or renaming a field, or making an optional field required, can break agents that depend on it, so the PR description must say so.
- The evidence shape is copied in both schemas that carry it, so a change to it must be made in both. The source list in `CoordinatorDecision` must follow it too. See the decision in [`architecture.md`](architecture.md#evidence-shape-is-copied-not-shared). A test fails if the two copies differ.
