"""Orchestration — routing, the single write path, and ambiguity surfacing."""

from chat_organizer import db
from chat_organizer.bridge import CLOSE_MARKER, OPEN_MARKER
from chat_organizer.retrieval import ChatHit
from chat_organizer.service import Organizer


def test_native_turn_is_routed_and_written(organizer):
    result = organizer.ingest("We decided the graph table is the single master table.")
    assert result.path == "native"
    assert len(result.written) == 1
    assert result.written[0].node_type == "decision"


def test_bridge_paste_is_routed_to_the_bridge_path(organizer):
    paste = f"{OPEN_MARKER}\nnode_id: x\nnode_type: task\nbody:\n  Update the booking form.\n{CLOSE_MARKER}"
    result = organizer.ingest(paste)
    assert result.path == "bridge"
    assert result.written[0].node_id == "x"


def test_filler_turn_writes_nothing(organizer):
    result = organizer.ingest("ok thanks")
    assert result.written == []
    assert result.ops[0].kind == "skip"


def test_one_turn_many_nodes(organizer):
    result = organizer.ingest(
        "We decided tags are JSON columns.\n\nTODO: add the read endpoints.\n\n"
        "Should we defer the offline fallback?"
    )
    assert {n.node_type for n in result.written} == {"decision", "task", "question"}


def test_repeating_a_turn_updates_rather_than_duplicates(organizer):
    text = "We're going with flat per-trip pricing for Stay Driving."
    organizer.ingest(text)
    organizer.ingest(text)
    assert organizer.conn.execute("SELECT COUNT(*) AS n FROM graph").fetchone()["n"] == 1


def test_retrieval_request_is_organised_and_searched(conn, fake_provider):
    provider = fake_provider([
        ChatHit(chat_id="chat-1", title="Stay Driving rate card",
                excerpt="flat per trip", score=0.95),
    ])
    org = Organizer(conn=conn, provider=provider)
    result = org.ingest("what was that thing we talked about with the Stay Driving rate card?")
    assert result.retrieval_triggered
    assert result.keywords
    assert any(n.source_chat == "chat-1" for n in result.written)


def test_ambiguous_retrieval_surfaces_a_question_and_writes_no_chat_node(conn, fake_provider):
    provider = fake_provider([
        ChatHit(chat_id="chat-1", title="pricing v1", score=0.9),
        ChatHit(chat_id="chat-2", title="pricing v2", score=0.9),
    ])
    org = Organizer(conn=conn, provider=provider)
    result = org.ingest("remember when we talked about pricing?")
    assert result.needs_answer
    assert len(result.questions[0].candidates) == 2
    assert not any(n.source_chat in ("chat-1", "chat-2") for n in result.written)


def test_answering_an_ambiguity_lands_the_chosen_chat(conn, fake_provider):
    provider = fake_provider([
        ChatHit(chat_id="chat-1", title="pricing v1", score=0.9),
        ChatHit(chat_id="chat-2", title="pricing v2", score=0.9),
    ])
    org = Organizer(conn=conn, provider=provider)
    result = org.ingest("remember when we talked about pricing?")
    chosen = result.questions[0].candidates[1]
    stored = org.answer_ambiguity(chosen)
    assert stored.source_chat == "chat-2"
    assert db.get_node(conn, stored.canon_id) is not None


def test_recall_runs_retrieval_only(conn, fake_provider):
    provider = fake_provider([ChatHit(chat_id="chat-1", title="pricing", score=0.9)])
    org = Organizer(conn=conn, provider=provider)
    result = org.recall("my pricing spec")
    assert result.path == "recall"
    assert len(result.written) == 1


def test_no_provider_means_no_crash(organizer):
    result = organizer.ingest("remember when we talked about pricing?")
    assert result.retrieval_triggered
    assert result.hits == []


def test_apply_ops_false_writes_nothing(organizer):
    result = organizer.ingest("We decided the graph table is the master table.", apply_ops=False)
    assert result.written == []
    assert organizer.conn.execute("SELECT COUNT(*) AS n FROM graph").fetchone()["n"] == 0


def test_open_tasks_group_by_parent_root(organizer):
    root = organizer.ingest("Starting a new project for driver onboarding.").written[0]
    organizer.ingest("TODO: design the driver signup form.", parent_root=root.canon_id)
    organizer.ingest("TODO: write the background check step.", parent_root=root.canon_id)
    grouped = organizer.open_tasks()
    assert len(grouped[root.canon_id]) == 2


def test_archived_tasks_are_not_open(organizer):
    task = organizer.ingest("TODO: retire the hourly billing code path.").written[0]
    task.status = "archived"
    db.upsert_node(organizer.conn, task)
    assert organizer.open_tasks() == {}


def test_result_json_is_serialisable(organizer):
    import json
    result = organizer.ingest("We decided the graph table is the master table.")
    assert json.loads(json.dumps(result.to_json()))["path"] == "native"


# --- the fixtures, replayed --------------------------------------------------
def test_replaying_a_chat_export_builds_a_graph(organizer, chat_exports):
    export = chat_exports["ddbos-build-2026-09-02"]
    for turn in export["turns"]:
        organizer.ingest(turn["text"], source_chat=export["chat_id"],
                         source_turn_kind=turn["kind"])
    nodes = organizer.nodes(limit=100)
    kinds = {n.node_type for n in nodes}
    assert {"decision", "task", "question", "spec", "relationship"} <= kinds
    # Filler turns ('hey', 'Understood.', 'ok cool thanks') left no nodes.
    assert all("thanks" not in n.body.lower() for n in nodes)
    assert all(n.source_chat == export["chat_id"] for n in nodes)


def test_replaying_the_same_export_twice_is_idempotent_in_shape(organizer, chat_exports):
    export = chat_exports["staydriving-pricing-2026-08-21"]
    for _ in range(2):
        for turn in export["turns"]:
            organizer.ingest(turn["text"], source_chat=export["chat_id"])
    first_pass_ids = {n.node_id for n in organizer.nodes(limit=100)}
    for turn in export["turns"]:
        organizer.ingest(turn["text"], source_chat=export["chat_id"])
    assert {n.node_id for n in organizer.nodes(limit=100)} == first_pass_ids
