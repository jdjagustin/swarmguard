"""Contract tests for the message schemas.

They check that the schemas are valid, that the evidence shape is identical in
both of them (it is copied, not shared), that example messages pass, and that
a list of broken messages is rejected.
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
SIGNAL_EXAMPLE = load(EXAMPLES / "suspicion_signal.json")
REPORT_EXAMPLE = load(EXAMPLES / "hypothesis_report.json")


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
    "schema", [SIGNAL_SCHEMA, REPORT_SCHEMA], ids=["suspicion_signal", "hypothesis_report"]
)
def test_schema_is_valid_json_schema(schema):
    Draft202012Validator.check_schema(schema)


def test_evidence_shape_is_identical_in_both_schemas():
    signal_evidence = SIGNAL_SCHEMA["properties"]["evidence"]
    report_evidence = REPORT_SCHEMA["properties"]["hypotheses"]["items"]["properties"]["evidence"]
    assert signal_evidence == report_evidence


# --- valid messages ---------------------------------------------------------


@pytest.mark.parametrize(
    ("schema", "example"),
    [(SIGNAL_SCHEMA, SIGNAL_EXAMPLE), (REPORT_SCHEMA, REPORT_EXAMPLE)],
    ids=["suspicion_signal", "hypothesis_report"],
)
def test_valid_example_passes(schema, example):
    assert errors(schema, example) == []


def test_report_example_points_to_signal_example():
    assert REPORT_EXAMPLE["signal_id"] == SIGNAL_EXAMPLE["signal_id"]


def test_example_in_contracts_doc_passes():
    text = (ROOT / "docs" / "contracts.md").read_text()
    block = re.search(r"```json\n(.*?)\n```", text, re.DOTALL)
    assert block is not None, "docs/contracts.md has no json example"
    assert errors(SIGNAL_SCHEMA, json.loads(block.group(1))) == []


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


@pytest.mark.parametrize("name", list(BAD_SIGNALS))
def test_broken_signal_is_rejected(name):
    message = changed(SIGNAL_EXAMPLE, BAD_SIGNALS[name])
    assert errors(SIGNAL_SCHEMA, message), f"accepted a broken signal: {name}"


@pytest.mark.parametrize("name", list(BAD_REPORTS))
def test_broken_report_is_rejected(name):
    message = changed(REPORT_EXAMPLE, BAD_REPORTS[name])
    assert errors(REPORT_SCHEMA, message), f"accepted a broken report: {name}"
