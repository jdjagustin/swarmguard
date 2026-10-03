"""Contract tests for the message schemas.

They check that the schemas are valid, that the evidence shape is identical in
the two messages that carry it (it is copied, not shared), that the source list
used by the decision matches it, that example messages pass and link to each
other, and that a list of broken messages is rejected.
"""

import copy
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = Path(__file__).resolve().parent / "examples" / "valid"


def load(path):
    return json.loads(path.read_text())


SIGNAL_SCHEMA = load(ROOT / "schemas" / "suspicion_signal.schema.json")
REPORT_SCHEMA = load(ROOT / "schemas" / "hypothesis_report.schema.json")
DECISION_SCHEMA = load(ROOT / "schemas" / "coordinator_decision.schema.json")
ACTION_SCHEMA = load(ROOT / "schemas" / "guardian_action.schema.json")
SIGNAL_EXAMPLE = load(EXAMPLES / "suspicion_signal.json")
REPORT_EXAMPLE = load(EXAMPLES / "hypothesis_report.json")
DECISION_EXAMPLE = load(EXAMPLES / "coordinator_decision.json")
ACTION_EXAMPLE = load(EXAMPLES / "guardian_action.json")


def errors(schema, message):
    """Return the list of validation errors, with format checks (date-time) on."""
    checker = Draft202012Validator.FORMAT_CHECKER
    return list(Draft202012Validator(schema, format_checker=checker).iter_errors(message))


def changed(example, mutate):
    """Return a deep copy of an example after applying a mutation to it."""
    message = copy.deepcopy(example)
    mutate(message)
    return message


# --- the schemas themselves -------------------------------------------------


@pytest.mark.parametrize(
    "schema",
    [SIGNAL_SCHEMA, REPORT_SCHEMA, DECISION_SCHEMA, ACTION_SCHEMA],
    ids=["suspicion_signal", "hypothesis_report", "coordinator_decision", "guardian_action"],
)
def test_schema_is_valid_json_schema(schema):
    Draft202012Validator.check_schema(schema)


def test_evidence_shape_is_identical_in_both_schemas():
    signal_evidence = SIGNAL_SCHEMA["properties"]["evidence"]
    report_evidence = REPORT_SCHEMA["properties"]["hypotheses"]["items"]["properties"]["evidence"]
    assert signal_evidence == report_evidence


def test_decision_sources_match_the_evidence_sources():
    evidence_item = SIGNAL_SCHEMA["properties"]["evidence"]["items"]
    decision_sources = DECISION_SCHEMA["properties"]["corroborating_sources"]["items"]
    assert decision_sources["enum"] == evidence_item["properties"]["source"]["enum"]


# --- valid messages ---------------------------------------------------------


@pytest.mark.parametrize(
    ("schema", "example"),
    [
        (SIGNAL_SCHEMA, SIGNAL_EXAMPLE),
        (REPORT_SCHEMA, REPORT_EXAMPLE),
        (DECISION_SCHEMA, DECISION_EXAMPLE),
        (ACTION_SCHEMA, ACTION_EXAMPLE),
    ],
    ids=["suspicion_signal", "hypothesis_report", "coordinator_decision", "guardian_action"],
)
def test_valid_example_passes(schema, example):
    assert errors(schema, example) == []


def test_example_chain_is_linked_by_ids():
    assert REPORT_EXAMPLE["signal_id"] == SIGNAL_EXAMPLE["signal_id"]
    assert DECISION_EXAMPLE["signal_id"] == SIGNAL_EXAMPLE["signal_id"]
    assert DECISION_EXAMPLE["report_id"] == REPORT_EXAMPLE["report_id"]
    assert ACTION_EXAMPLE["decision_id"] == DECISION_EXAMPLE["decision_id"]


def test_examples_in_contracts_doc_pass():
    text = (ROOT / "docs" / "contracts.md").read_text()
    blocks = re.findall(r"```json\n(.*?)\n```", text, re.DOTALL)
    schemas = [SIGNAL_SCHEMA, DECISION_SCHEMA, ACTION_SCHEMA]
    assert len(blocks) == len(schemas), "docs/contracts.md should have one json example per documented contract"
    for schema, block in zip(schemas, blocks):
        assert errors(schema, json.loads(block)) == []


@pytest.mark.parametrize("severity", ["LOW", "MEDIUM", "HIGH", "CRITICAL"])
def test_all_severities_are_accepted(severity):
    message = changed(SIGNAL_EXAMPLE, lambda m: m.update(severity=severity))
    assert errors(SIGNAL_SCHEMA, message) == []


@pytest.mark.parametrize(
    "category", ["card_testing", "credential_stuffing", "misconfiguration", "benign", "unknown"]
)
def test_all_categories_are_accepted(category):
    message = changed(REPORT_EXAMPLE, lambda m: m["hypotheses"][0].update(category=category))
    assert errors(REPORT_SCHEMA, message) == []


@pytest.mark.parametrize("confidence", [0, 0.5, 1])
def test_confidence_limits_are_accepted(confidence):
    message = changed(REPORT_EXAMPLE, lambda m: m["hypotheses"][0].update(confidence=confidence))
    assert errors(REPORT_SCHEMA, message) == []


@pytest.mark.parametrize("decision", ["discard", "report"])
def test_discard_and_report_need_no_corroboration(decision):
    def mutate(m):
        m.update(decision=decision)
        m.pop("corroborating_sources")

    assert errors(DECISION_SCHEMA, changed(DECISION_EXAMPLE, mutate)) == []


@pytest.mark.parametrize(
    "action_type",
    ["block_ip_temporary", "rate_limit_temporary", "restrict_security_group_temporary"],
)
def test_all_action_types_are_accepted(action_type):
    message = changed(ACTION_EXAMPLE, lambda m: m.update(action_type=action_type))
    assert errors(ACTION_SCHEMA, message) == []


@pytest.mark.parametrize("ttl", [1, 1440])
def test_ttl_limits_are_accepted(ttl):
    message = changed(ACTION_EXAMPLE, lambda m: m.update(ttl_minutes=ttl))
    assert errors(ACTION_SCHEMA, message) == []


# --- broken messages --------------------------------------------------------

BAD_SIGNALS = {
    "missing evidence": lambda m: m.pop("evidence"),
    "empty evidence": lambda m: m.update(evidence=[]),
    "malformed signal_id": lambda m: m.update(signal_id="sig-XYZ"),
    "wrong source_agent": lambda m: m.update(source_agent="investigator"),
    "unknown severity": lambda m: m.update(severity="URGENT"),
    "extra field": lambda m: m.update(action="block_ip"),
    "empty summary": lambda m: m.update(summary=""),
    "summary too long": lambda m: m.update(summary="x" * 501),
    "malformed timestamp": lambda m: m.update(created_at="yesterday"),
    "unknown evidence source": lambda m: m["evidence"][0].update(source="slack"),
    "evidence without reference": lambda m: m["evidence"][0].pop("reference"),
    "extra evidence field": lambda m: m["evidence"][0].update(note="x"),
}

BAD_REPORTS = {
    "missing hypotheses": lambda m: m.pop("hypotheses"),
    "empty hypotheses": lambda m: m.update(hypotheses=[]),
    "malformed report_id": lambda m: m.update(report_id="rep-XYZ"),
    "malformed signal_id": lambda m: m.update(signal_id="sig-XYZ"),
    "wrong source_agent": lambda m: m.update(source_agent="scout"),
    "extra field": lambda m: m.update(action="block_ip"),
    "confidence above 1": lambda m: m["hypotheses"][0].update(confidence=1.01),
    "confidence below 0": lambda m: m["hypotheses"][0].update(confidence=-0.01),
    "unknown category": lambda m: m["hypotheses"][0].update(category="fraud"),
    "title too long": lambda m: m["hypotheses"][0].update(title="x" * 121),
    "hypothesis without evidence": lambda m: m["hypotheses"][0].pop("evidence"),
    "extra hypothesis field": lambda m: m["hypotheses"][0].update(action="block_ip"),
    "unknown evidence source": lambda m: m["hypotheses"][0]["evidence"][0].update(source="slack"),
}

BAD_DECISIONS = {
    "missing rationale": lambda m: m.pop("rationale"),
    "empty rationale": lambda m: m.update(rationale=""),
    "rationale too long": lambda m: m.update(rationale="x" * 1001),
    "malformed decision_id": lambda m: m.update(decision_id="dec-XYZ"),
    "malformed report_id": lambda m: m.update(report_id="rep-XYZ"),
    "malformed signal_id": lambda m: m.update(signal_id="sig-XYZ"),
    "wrong source_agent": lambda m: m.update(source_agent="scout"),
    "unknown decision": lambda m: m.update(decision="block_now"),
    "confidence above 1": lambda m: m.update(confidence=1.01),
    "confidence below 0": lambda m: m.update(confidence=-0.01),
    "extra field": lambda m: m.update(action="block_ip"),
    "malformed timestamp": lambda m: m.update(created_at="yesterday"),
    "proposal without corroboration": lambda m: m.pop("corroborating_sources"),
    "proposal with empty corroboration": lambda m: m.update(corroborating_sources=[]),
    "proposal with one source": lambda m: m.update(corroborating_sources=["stripe_event"]),
    "duplicate corroborating source": lambda m: m.update(
        corroborating_sources=["stripe_event", "stripe_event"]
    ),
    "unknown corroborating source": lambda m: m.update(corroborating_sources=["stripe_event", "slack"]),
}

BAD_ACTIONS = {
    "live mode": lambda m: m.update(mode="live"),
    "missing mode": lambda m: m.pop("mode"),
    "approval not required": lambda m: m.update(requires_human_approval=False),
    "missing approval flag": lambda m: m.pop("requires_human_approval"),
    "unknown action type": lambda m: m.update(action_type="delete_instance"),
    "missing ttl": lambda m: m.pop("ttl_minutes"),
    "ttl zero": lambda m: m.update(ttl_minutes=0),
    "ttl above one day": lambda m: m.update(ttl_minutes=1441),
    "ttl not an integer": lambda m: m.update(ttl_minutes=60.5),
    "empty target": lambda m: m.update(target=""),
    "target too long": lambda m: m.update(target="x" * 201),
    "summary too long": lambda m: m.update(summary="x" * 501),
    "malformed action_id": lambda m: m.update(action_id="act-XYZ"),
    "malformed decision_id": lambda m: m.update(decision_id="dec-XYZ"),
    "wrong source_agent": lambda m: m.update(source_agent="coordinator"),
    "extra field": lambda m: m.update(command="iptables -A INPUT -j DROP"),
    "malformed timestamp": lambda m: m.update(created_at="yesterday"),
}


@pytest.mark.parametrize("name", list(BAD_SIGNALS))
def test_broken_signal_is_rejected(name):
    message = changed(SIGNAL_EXAMPLE, BAD_SIGNALS[name])
    assert errors(SIGNAL_SCHEMA, message), f"accepted a broken signal: {name}"


@pytest.mark.parametrize("name", list(BAD_REPORTS))
def test_broken_report_is_rejected(name):
    message = changed(REPORT_EXAMPLE, BAD_REPORTS[name])
    assert errors(REPORT_SCHEMA, message), f"accepted a broken report: {name}"


@pytest.mark.parametrize("name", list(BAD_DECISIONS))
def test_broken_decision_is_rejected(name):
    message = changed(DECISION_EXAMPLE, BAD_DECISIONS[name])
    assert errors(DECISION_SCHEMA, message), f"accepted a broken decision: {name}"


@pytest.mark.parametrize("name", list(BAD_ACTIONS))
def test_broken_action_is_rejected(name):
    message = changed(ACTION_EXAMPLE, BAD_ACTIONS[name])
    assert errors(ACTION_SCHEMA, message), f"accepted a broken action: {name}"
