"""Tests for services/disposition.py."""

import pytest

from backend.services.disposition import (
    DEFAULT_DISPOSITION,
    DISPOSITIONS,
    FINDING_TRIAGE,
    normalize_disposition,
    normalize_finding_triage,
)


def test_dispositions_set():
    assert "open" in DISPOSITIONS
    assert "parse_bug" in DISPOSITIONS
    assert "source_defect" in DISPOSITIONS
    assert "deliberate" in DISPOSITIONS
    assert "not_a_defect" in DISPOSITIONS
    assert len(DISPOSITIONS) == 5


def test_finding_triage_set():
    assert "new" in FINDING_TRIAGE
    assert "fixed" in FINDING_TRIAGE
    assert "parse_bug" in FINDING_TRIAGE
    assert len(FINDING_TRIAGE) == 6


def test_normalize_disposition_valid():
    assert normalize_disposition("open") == "open"
    assert normalize_disposition("PARSE_BUG") == "parse_bug"
    assert normalize_disposition("  source-defect  ") == "source_defect"
    assert normalize_disposition(None) == DEFAULT_DISPOSITION


def test_normalize_disposition_invalid():
    with pytest.raises(ValueError, match="invalid disposition"):
        normalize_disposition("garbage")


def test_normalize_finding_triage_valid():
    assert normalize_finding_triage("new") == "new"
    assert normalize_finding_triage("fixed") == "fixed"
    assert normalize_finding_triage("parse_bug") == "parse_bug"


def test_normalize_finding_triage_aliases():
    assert normalize_finding_triage("accepted") == "parse_bug"
    assert normalize_finding_triage("dismissed") == "not_a_defect"


def test_normalize_finding_triage_invalid():
    with pytest.raises(ValueError, match="invalid finding triage"):
        normalize_finding_triage("unknown_value")
