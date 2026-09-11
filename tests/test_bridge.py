"""Bridge paste-back path — pre-structured text through the same parser."""

from chat_organizer import db
from chat_organizer.bridge import (
    BRIDGE_PROMPT,
    CLOSE_MARKER,
    OPEN_MARKER,
    extract_blocks,
    looks_like_bridge_paste,
    node_from_block,
    parse_block_fields,
    parse_bridge_paste,
)
from chat_organizer.parser import apply

FULL_BLOCK = f"""{OPEN_MARKER}
node_id: rate_card_v2
node_type: decision
status: active
tags: domain/business-ops, status/active
links: supersedes -> Rate_Card_V1, supports -> [[Stay_Driving_Operations]]
summary: Rate card moves to flat per-trip pricing.
source_chat: Stay Driving pricing chat
body:
  We locked flat per-trip pricing at $45 base.
  Hourly is retired.
{CLOSE_MARKER}"""


def test_the_prompt_carries_both_markers():
    """The prompt Dame pastes out must match the parser that reads the reply."""
    assert OPEN_MARKER in BRIDGE_PROMPT
    assert CLOSE_MARKER in BRIDGE_PROMPT


def test_detects_a_bridge_paste():
    assert looks_like_bridge_paste(FULL_BLOCK)
    assert not looks_like_bridge_paste("We decided on flat pricing.")


def test_extracts_multiple_blocks_from_one_paste():
    paste = f"Sure, here you go:\n\n{FULL_BLOCK}\n\n{FULL_BLOCK}\n\nHope that helps!"
    assert len(extract_blocks(paste)) == 2


def test_surrounding_chatter_is_ignored():
    ops = parse_bridge_paste(f"Absolutely! Here are the blocks:\n{FULL_BLOCK}\nLet me know.")
    assert len(ops) == 1
    assert ops[0].node.node_id == "rate_card_v2"


def test_explicit_fields_win_over_derivation():
    node = node_from_block(extract_blocks(FULL_BLOCK)[0])
    assert node.node_id == "rate_card_v2"
    assert node.node_type == "decision"
    assert node.status == "active"
    assert node.tags == ["domain/business-ops", "status/active"]
    assert node.summary == "Rate card moves to flat per-trip pricing."
    assert node.source_chat == "Stay Driving pricing chat"


def test_body_keeps_its_shape_after_dedent():
    _, body = parse_block_fields(extract_blocks(FULL_BLOCK)[0])
    assert body == "We locked flat per-trip pricing at $45 base.\nHourly is retired."


def test_links_parse_both_arrow_and_wikilink_forms():
    node = node_from_block(extract_blocks(FULL_BLOCK)[0])
    edges = {(l.to, l.relation) for l in node.links}
    assert ("Rate_Card_V1", "supersedes") in edges
    assert ("Stay_Driving_Operations", "supports") in edges


def test_missing_fields_are_derived_not_demanded():
    minimal = f"{OPEN_MARKER}\nbody:\n  We decided to retire hourly billing entirely.\n{CLOSE_MARKER}"
    node = node_from_block(extract_blocks(minimal)[0])
    assert node.node_type == "decision"   # classified, not supplied
    assert node.node_id                    # slug derived
    assert node.tags                       # tags derived
    assert node.summary


def test_an_invented_canon_id_is_discarded():
    """A far-side assistant that hallucinates an ID must not poison the graph."""
    bad = f"{OPEN_MARKER}\ncanon_id: totally-made-up\nbody:\n  Durable content about pricing.\n{CLOSE_MARKER}"
    node = node_from_block(extract_blocks(bad)[0])
    assert node.canon_id == "PENDING.NODE.00000000.0000.Pending.001"


def test_a_real_canon_id_is_honoured():
    real = "COS.SPEC.20260911.0400.GraphTable.001"
    good = f"{OPEN_MARKER}\ncanon_id: {real}\nbody:\n  Durable content about the graph table.\n{CLOSE_MARKER}"
    assert node_from_block(extract_blocks(good)[0]).canon_id == real


def test_yaml_front_matter_is_tolerated():
    paste = (
        "---\n"
        "node_id: invoice_spec\n"
        "node_type: spec\n"
        "body:\n"
        "  Invoices must carry the canon ID in the footer.\n"
        "---\n"
    )
    ops = parse_bridge_paste(paste)
    assert ops[0].node.node_id == "invoice_spec"


def test_a_paste_with_no_block_is_skipped():
    ops = parse_bridge_paste("Sorry, I don't have that information.")
    assert ops[0].kind == "skip"


def test_bridge_reuses_reconciliation_including_updates(organizer):
    first = parse_bridge_paste(FULL_BLOCK, matcher=organizer.matcher)
    apply(organizer.conn, first[0])
    second = parse_bridge_paste(FULL_BLOCK, matcher=organizer.matcher)
    assert second[0].kind == "update"


def test_bridge_writes_through_the_shared_upsert(conn):
    stored = apply(conn, parse_bridge_paste(FULL_BLOCK)[0])
    assert db.get_node(conn, stored.canon_id).node_id == "rate_card_v2"
    assert stored.source_turn_kind == "assistant"
