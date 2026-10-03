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

Messages for decisions and actions do not have a contract yet.

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

## What a contract does not guarantee

- **A valid shape is not a true statement.** A message can match its schema perfectly and still contain false claims, whether from a confused model or from an attacker who shaped the input.
- **Free-text fields can still carry instructions.** A schema limits length and allowed fields, but it cannot tell whether a string such as `summary` contains an instruction. Code that reads those fields must treat them as data, never as commands.
- **Passing the tests means the shape is right, nothing more.** The tests below check shape and limits. They cannot tell whether a message is true or safe.

## Testing the contracts

Automated tests in [`tests/test_schemas.py`](../tests/test_schemas.py) run with pytest (see the README for how to run them). They check that:

- both schemas are valid JSON Schema documents;
- the evidence shape is identical in both schemas, so the decision to copy it stays safe;
- the example messages in `tests/examples/valid/` pass, and so does the example in this document;
- broken messages are rejected: missing or empty evidence, malformed identifiers, the wrong source agent, unknown values, confidence out of range, text that is too long, malformed timestamps and extra fields.

## Changing a contract

- A contract changes through a pull request that updates the schema, the examples in this document, the test examples under `tests/examples/` and the README or architecture docs in the same PR.
- Adding an optional field is usually safe. Removing or renaming a field, or making an optional field required, can break agents that depend on it, so the PR description must say so.
- The evidence shape is copied in both schemas, so a change to it must be made in both. See the decision in [`architecture.md`](architecture.md#evidence-shape-is-copied-not-shared). A test fails if the two copies differ.
