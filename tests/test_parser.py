"""Parsing layer — classification, reconciliation (Section 9), and apply()."""

import pytest

from chat_organizer import db
from chat_organizer.nodes import Node, NodeOp
from chat_organizer.parser import (
    AMBIGUITY_DELTA,
    UPDATE_THRESHOLD,
    apply,
    classify,
    derive_links,
    derive_tags,
    is_filler,
    parse_message,
    split_units,
    summarise,
)


# --- Section 8: filler vs durable -------------------------------------------
@pytest.mark.parametrize(
    "text",
    ["ok", "thanks!", "yep", "got it", "sounds good", "hey", "brb", "", "   ", "lol"],
)
def test_filler_turns_are_dropped(text):
    assert is_filler(text)
    assert parse_message(text)[0].kind == "skip"


@pytest.mark.parametrize(
    "text",
    [
        "We're going with flat per-trip pricing for Stay Driving.",
        "TODO: wire the bridge paste-back path first.",
        "The graph table must have canon_id as its primary key.",
    ],
)
def test_durable_turns_are_kept(text):
    assert not is_filler(text)
    assert parse_message(text)[0].kind == "create"


def test_short_acknowledgement_with_content_is_still_filler():
    assert is_filler("yes exactly")


# --- classification ----------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected",
    [
        ("We decided tags are JSON columns on the row.", "decision"),
        ("We're going with flat per-trip pricing.", "decision"),
        ("TODO: add the two read endpoints to the Flask app.", "task"),
        ("Let's wire the bridge paste-back path first.", "task"),
        ("Should we build the standalone fallback now?", "question"),
        ("Open question: does the join table come back later?", "question"),
        ("The graph table must have canon_id as its primary key.", "spec"),
        ("The retrieval layer depends on [[COS_Root_Organizer_Protocol]].", "relationship"),
        ("The new rate card supersedes [[Rate_Card_V1]].", "relationship"),
        ("Starting a new project for the driver onboarding flow.", "root"),
        ("Pricing might work better as a subscription for repeat riders.", "idea"),
    ],
)
def test_classification(text, expected):
    assert classify(text) == expected


def test_question_beats_task_when_both_cues_present():
    assert classify("Should we add the endpoint now?") == "question"


def test_decision_beats_spec_when_both_cues_present():
    assert classify("We decided the schema must use canon_id.") == "decision"


# --- segmentation ------------------------------------------------------------
def test_paragraphs_become_separate_units():
    units = split_units("First durable thought here.\n\nSecond durable thought here.")
    assert len(units) == 2


def test_a_fenced_code_block_stays_one_unit():
    text = "```sql\nCREATE TABLE graph (\n  canon_id TEXT\n);\n```"
    assert split_units(text) == [text.strip()]


def test_bullet_lists_split_per_item():
    units = split_units("- first action item here\n- second action item here\n- third one here")
    assert len(units) == 3
    assert not units[0].startswith("-")


def test_one_message_can_produce_several_nodes():
    ops = parse_message(
        "We decided tags are JSON columns.\n\nTODO: add the read endpoints.\n\n"
        "Should we defer the offline fallback?"
    )
    assert [op.node.node_type for op in ops] == ["decision", "task", "question"]


# --- derived metadata --------------------------------------------------------
def test_tags_are_hierarchical():
    tags = derive_tags("We decided the SQLite schema is locked.", "decision")
    assert "type/decision" in tags
    assert "status/active" in tags
    assert "domain/software" in tags
    assert "tech/sqlite" in tags


def test_questions_are_tagged_planning():
    assert "status/planning" in derive_tags("Should we defer it?", "question")


def test_wikilinks_and_canon_ids_become_links():
    links = derive_links(
        "The parser depends on [[COS_Root_Organizer_Protocol]] and "
        "COS.SPEC.20260911.0400.GraphTable.001."
    )
    targets = {l.to for l in links}
    assert "COS_Root_Organizer_Protocol" in targets
    assert "COS.SPEC.20260911.0400.GraphTable.001" in targets
    assert all(l.relation == "depends_on" for l in links)


def test_summary_is_the_first_sentence():
    assert summarise("Flat pricing is locked. Hourly is retired.") == "Flat pricing is locked."


# --- Section 9: reconciliation ----------------------------------------------
def test_no_match_creates(organizer):
    ops = parse_message("A brand new thought about driver onboarding flow.",
                        matcher=organizer.matcher)
    assert ops[0].kind == "create"


def test_strong_match_updates_instead_of_duplicating(organizer):
    text = "We're going with flat per-trip pricing for Stay Driving."
    organizer.ingest(text)
    ops = parse_message(text, matcher=organizer.matcher)
    assert ops[0].kind == "update"
    assert ops[0].confidence >= UPDATE_THRESHOLD


def test_ambiguous_match_asks_and_never_auto_picks():
    """Two equally plausible targets must come back as a question."""
    rival_a = Node(canon_id="COS.IDEA.20260911.0400.A.001", node_id="a",
                   node_type="idea", body="flat per trip pricing stay driving")
    rival_b = Node(canon_id="COS.IDEA.20260911.0400.B.001", node_id="b",
                   node_type="idea", body="flat per trip pricing stay driving")

    def matcher(terms):
        return [(rival_a, 1.0), (rival_b, 1.0 - AMBIGUITY_DELTA / 2)]

    ops = parse_message("We're going with flat per-trip pricing for Stay Driving.",
                        matcher=matcher)
    assert ops[0].kind == "question"
    assert {c["canon_id"] for c in ops[0].candidates} == {rival_a.canon_id, rival_b.canon_id}
    assert ops[0].target_canon_id is None


def test_clear_winner_is_not_treated_as_ambiguous():
    winner = Node(canon_id="COS.IDEA.20260911.0400.A.001", node_id="a",
                  node_type="idea", body="x")
    loser = Node(canon_id="COS.IDEA.20260911.0400.B.001", node_id="b",
                 node_type="idea", body="y")

    def matcher(terms):
        return [(winner, 1.0), (loser, 1.0 - AMBIGUITY_DELTA - 0.1)]

    ops = parse_message("We're going with flat per-trip pricing.", matcher=matcher)
    assert ops[0].kind == "update"
    assert ops[0].target_canon_id == winner.canon_id


# --- apply() -----------------------------------------------------------------
def test_apply_create_mints_a_valid_canon_id(conn):
    op = parse_message("We decided the graph table is the single master table.")[0]
    stored = apply(conn, op)
    assert stored.canon_id.startswith("COS.DECISION.")
    assert db.get_node(conn, stored.canon_id) is not None


def test_apply_update_appends_body_and_unions_tags(conn):
    created = apply(conn, parse_message("Flat per-trip pricing is the plan for Stay Driving.")[0])
    op = parse_message("Flat per-trip pricing is the plan for Stay Driving, hourly retired.")[0]
    op.kind = "update"
    op.target_canon_id = created.canon_id
    updated = apply(conn, op)
    assert "hourly retired" in updated.body
    assert created.created_at == updated.created_at
    assert conn.execute("SELECT COUNT(*) AS n FROM graph").fetchone()["n"] == 1


def test_apply_question_and_skip_write_nothing(conn):
    assert apply(conn, NodeOp("question", question="which?")) is None
    assert apply(conn, NodeOp("skip", reason="filler")) is None
    assert conn.execute("SELECT COUNT(*) AS n FROM graph").fetchone()["n"] == 0


def test_apply_update_to_missing_target_raises(conn):
    op = parse_message("Some durable content here for the graph.")[0]
    op.kind = "update"
    op.target_canon_id = "COS.IDEA.20260911.0400.Missing.001"
    with pytest.raises(KeyError):
        apply(conn, op)


def test_apply_link_and_tag_ops(conn):
    node = apply(conn, parse_message("The graph table is the single master table here.")[0])
    apply(conn, NodeOp("tag", target_canon_id=node.canon_id, tags=["status/archived"]))
    apply(conn, NodeOp("link", target_canon_id=node.canon_id,
                       links=[{"to": "COS.IDEA.20260911.0400.X.001", "relation": "supports"}]))
    reloaded = db.get_node(conn, node.canon_id)
    assert "status/archived" in reloaded.tags
    assert reloaded.links[0].relation == "supports"


def test_root_node_is_its_own_parent(conn):
    stored = apply(conn, parse_message("Starting a new project for driver onboarding.")[0])
    assert stored.node_type == "root"
    assert stored.parent_root == stored.canon_id


def test_parse_message_is_pure(conn):
    """No matcher, no DB: parse_message must still work and write nothing."""
    ops = parse_message("We decided the graph table is the master table.")
    assert ops[0].kind == "create"
    assert conn.execute("SELECT COUNT(*) AS n FROM graph").fetchone()["n"] == 0


def test_reconcile_does_not_trust_matcher_ordering():
    """A matcher that returns candidates out of order must not cause a wrong pick."""
    weak = Node(canon_id="COS.IDEA.20260911.0400.Weak.001", node_id="weak",
                node_type="idea", body="x")
    strong = Node(canon_id="COS.IDEA.20260911.0400.Strong.001", node_id="strong",
                  node_type="idea", body="y")

    def unsorted_matcher(terms):
        # Worst-first, and inside the ambiguity band.
        return [(weak, 1.0 - AMBIGUITY_DELTA / 2), (strong, 1.0)]

    ops = parse_message("We're going with flat per-trip pricing.", matcher=unsorted_matcher)
    assert ops[0].kind == "question"
    assert ops[0].candidates[0]["canon_id"] == strong.canon_id

    def unsorted_clear(terms):
        # Worst-first, and outside the ambiguity band: a clear winner.
        return [(weak, 1.0 - AMBIGUITY_DELTA - 0.05), (strong, 1.0)]

    ops = parse_message("We're going with flat per-trip pricing.", matcher=unsorted_clear)
    assert ops[0].kind == "update"
    assert ops[0].target_canon_id == strong.canon_id
