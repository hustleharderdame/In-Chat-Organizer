"""Canon ID enforcement — [[Canon_ID_System]] grammar and the zero-width fix."""

import pytest

from chat_organizer import canon

VALID = "COS.REPORT.20260911.0400.ClaudeCodeImplementation.001"


def test_validates_the_report_canon_id():
    assert canon.validate(VALID) == VALID
    assert canon.is_valid(VALID)


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "COS.REPORT.20260911.0400.Object",          # missing SEQ
        "cos.report.20260911.0400.Object.001",      # lowercase DOMAIN/TYPE
        "COS.REPORT.2026911.0400.Object.001",       # short date
        "COS.REPORT.20260911.400.Object.001",       # short time
        "COS.REPORT.20260911.0400.Object.1",        # SEQ not padded
        "COS.REPORT.20260911.0400..001",            # empty OBJECT
    ],
)
def test_rejects_malformed_ids(bad):
    assert not canon.is_valid(bad)
    with pytest.raises(canon.CanonIdError):
        canon.validate(bad)


@pytest.mark.parametrize("invisible", ["​", "‌", "‍", "⁠", "﻿", "­"])
def test_zero_width_characters_are_scrubbed(invisible):
    """A pasted canon ID carrying invisible characters must still match."""
    polluted = f"COS.{invisible}REPORT.20260911.0400.ClaudeCode{invisible}Implementation.001"
    assert canon.scrub(polluted) == VALID
    assert canon.validate(polluted) == VALID


def test_scrub_handles_none_and_whitespace():
    assert canon.scrub(None) == ""
    assert canon.scrub("  COS.IDEA.20260911.0400.X.001  ") == "COS.IDEA.20260911.0400.X.001"


def test_parts_round_trip():
    parsed = canon.parts(VALID)
    assert parsed["domain"] == "COS"
    assert parsed["type"] == "REPORT"
    assert parsed["date"] == "20260911"
    assert parsed["object"] == "ClaudeCodeImplementation"
    assert parsed["seq"] == "001"


def test_mint_produces_valid_ids_from_messy_slugs():
    minted = canon.mint("idea", "bridge paste-back path!!")
    assert canon.is_valid(minted)
    assert ".BridgePasteBackPath." in minted


def test_mint_pads_sequence():
    assert canon.mint("task", "x", seq=7).endswith(".007")


def test_slug_to_object_never_empty():
    assert canon.slug_to_object("!!!") == "Node"
