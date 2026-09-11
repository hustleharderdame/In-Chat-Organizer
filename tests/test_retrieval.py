"""Retrieval layer — Section 7 trigger phrasings, keywords, Section 6 ambiguity."""

import pytest

from chat_organizer import db
from chat_organizer.retrieval import (
    AMBIGUITY_DELTA,
    MAX_KEYWORDS,
    MIN_KEYWORDS,
    PLAUSIBLE_FLOOR,
    ChatHit,
    HostToolProvider,
    detect_retrieval_trigger,
    extract_keywords,
    ingest_hit,
    node_from_hit,
    resolve_hits,
    score_hit,
    search_past_chats,
    trigger_families,
)


# --- Section 7: the four phrase families ------------------------------------
@pytest.mark.parametrize(
    "text,family",
    [
        # past tense
        ("what was that thing we talked about with the rate card?", "past_tense"),
        ("you said earlier that hourly billing was retired", "past_tense"),
        ("I mentioned the canon ID rule at some point", "past_tense"),
        ("we landed on a flat rate somewhere", "past_tense"),
        # definite article
        ("the thing about the booking form", "definite_article"),
        ("that spec we never finished", "definite_article"),
        ("the approach with the JSON columns", "definite_article"),
        # possessive
        ("my Stay Driving pricing spec", "possessive"),
        ("our invoice template", "possessive"),
        ("your notes on the graph table", "possessive"),
        # direct ask
        ("find the chat where we discussed the canon ID format", "direct_ask"),
        ("pull up the conversation about pricing", "direct_ask"),
        ("search our chats for the rate card", "direct_ask"),
        # explicit recall
        ("remember when we set up the invoice template?", "explicit_recall"),
        ("didn't we already decide on the SQLite schema?", "explicit_recall"),
        ("have we ever costed out the driver bonus?", "explicit_recall"),
    ],
)
def test_trigger_fires_for_each_phrase_family(text, family):
    assert detect_retrieval_trigger(text)
    assert family in trigger_families(text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "ok thanks",
        "add a new column to the graph table",
        "TODO: wire the bridge paste-back path",
        "We're going with flat per-trip pricing.",
        "The graph table must have canon_id as its primary key.",
        "Build the retrieval layer next.",
    ],
)
def test_trigger_does_not_fire_on_ordinary_turns(text):
    assert not detect_retrieval_trigger(text)


# --- keyword extraction ------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected_subset",
    [
        ("what was that thing we talked about with the Stay Driving rate card?",
         {"stay driving", "rate", "card"}),
        ("remember when we set up the invoice template?", {"invoice", "template"}),
        ("find the chat where we discussed the canon ID format", {"canon", "format"}),
        ("my Stay Driving pricing spec", {"stay driving", "pricing", "spec"}),
        ("didn't we already decide on the SQLite schema?", {"sqlite", "schema"}),
    ],
)
def test_keywords_are_the_subject_not_the_act_of_remembering(text, expected_subset):
    found = set(extract_keywords(text))
    assert expected_subset <= found


@pytest.mark.parametrize(
    "text",
    [
        "what was that thing we talked about with the Stay Driving rate card?",
        "remember when we discussed the booking form and the driver bonus and the rate card and pricing?",
    ],
)
def test_keyword_count_stays_in_the_two_to_six_band(text):
    found = extract_keywords(text)
    assert MIN_KEYWORDS <= len(found) <= MAX_KEYWORDS


def test_meta_words_are_stripped():
    found = extract_keywords("remember that conversation we had earlier about pricing")
    assert "remember" not in found
    assert "conversation" not in found
    assert "earlier" not in found
    assert "pricing" in found


def test_quoted_phrases_are_kept_whole_and_ranked_first():
    found = extract_keywords('find the chat about "flat per trip pricing"')
    assert found[0] == "flat per trip pricing"


def test_multiword_proper_nouns_survive():
    assert "stay driving" in extract_keywords("my Stay Driving rate card")


def test_no_keywords_from_an_empty_request():
    assert extract_keywords("") == []


# --- providers ---------------------------------------------------------------
def test_search_past_chats_without_a_provider_is_a_no_op():
    assert search_past_chats(["pricing"], None) == []


def test_search_past_chats_returns_best_first(fake_provider):
    provider = fake_provider([
        ChatHit(chat_id="b", title="other", score=0.2),
        ChatHit(chat_id="a", title="pricing", score=0.9),
    ])
    hits = search_past_chats(["pricing"], provider)
    assert [h.chat_id for h in hits] == ["a", "b"]
    assert provider.calls == [["pricing"]]


def test_host_provider_normalises_loose_payloads():
    def conversation_search(query):
        return {"results": [
            {"uri": "chat-1", "title": "Stay Driving pricing", "excerpt": "flat rate card"},
            {"id": "chat-2", "name": "Unrelated", "snippet": "kangaroos"},
        ]}

    hits = HostToolProvider(conversation_search).search(["pricing", "rate"])
    assert hits[0].chat_id == "chat-1"
    assert hits[0].score > hits[1].score
    assert hits[0].provider == "host"


def test_host_provider_handles_a_bare_list():
    hits = HostToolProvider(lambda query: [{"id": "x", "title": "pricing"}]).search(["pricing"])
    assert hits[0].chat_id == "x"


def test_host_provider_read_is_optional():
    assert HostToolProvider(lambda query: []).read("chat-1") == ""


def test_score_hit_is_term_coverage():
    hit = ChatHit(chat_id="x", title="pricing", excerpt="rate card")
    assert score_hit(hit, ["pricing", "rate"]) == 1.0
    assert score_hit(hit, ["pricing", "kangaroo"]) == 0.5


# --- Section 6, Step 4: ambiguity is mandatory ------------------------------
def test_two_plausible_hits_become_a_question_not_a_guess():
    hits = [
        ChatHit(chat_id="a", title="pricing v1", score=0.9),
        ChatHit(chat_id="b", title="pricing v2", score=0.9 - AMBIGUITY_DELTA / 2),
    ]
    op = resolve_hits(hits, "the pricing chat")
    assert op.kind == "question"
    assert {c["chat_id"] for c in op.candidates} == {"a", "b"}
    assert op.node is None  # nothing is written on ambiguity


def test_three_plausible_hits_all_surface_as_candidates():
    hits = [ChatHit(chat_id=c, title="pricing", score=0.9) for c in "abc"]
    op = resolve_hits(hits)
    assert op.kind == "question"
    assert len(op.candidates) == 3


def test_a_single_clear_hit_is_taken():
    hits = [
        ChatHit(chat_id="a", title="pricing", excerpt="flat rate", score=0.95),
        ChatHit(chat_id="b", title="other", score=0.95 - AMBIGUITY_DELTA - 0.1),
    ]
    op = resolve_hits(hits)
    assert op.kind == "create"
    assert op.node.source_chat == "a"


def test_no_plausible_hit_writes_nothing():
    op = resolve_hits([ChatHit(chat_id="a", score=PLAUSIBLE_FLOOR - 0.01)])
    assert op.kind == "skip"


def test_empty_hits_write_nothing():
    assert resolve_hits([]).kind == "skip"


# --- retrieved chats use the shared write path ------------------------------
def test_retrieved_hit_lands_in_graph_via_upsert(conn):
    hit = ChatHit(chat_id="chat-1", title="Stay Driving pricing",
                  excerpt="flat rate card", url="https://example/chat-1", score=1.0)
    stored = ingest_hit(conn, hit)
    assert db.get_node(conn, stored.canon_id) is not None
    assert stored.source_chat == "https://example/chat-1"
    assert "source/retrieved" in stored.tags
    # Retrieval owns no table of its own.
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not any(t.startswith("retriev") for t in tables)


def test_node_from_hit_slugifies_the_title():
    assert node_from_hit(ChatHit(chat_id="x", title="Stay Driving! Pricing")).node_id == "stay_driving_pricing"


def test_node_from_hit_falls_back_to_chat_id():
    assert node_from_hit(ChatHit(chat_id="chat-1")).node_id == "chat_1"


def test_resolve_hits_does_not_trust_incoming_order():
    """resolve_hits must sort for itself, not assume the provider did."""
    hits = [
        ChatHit(chat_id="weak", title="a", score=0.5),
        ChatHit(chat_id="strong", title="b", score=0.95),
    ]
    op = resolve_hits(hits)
    assert op.kind == "create"
    assert op.node.source_chat == "strong"
