"""Storage layer — the single ``graph`` table, its FTS5 index, and upsert."""

import json

from chat_organizer import db
from chat_organizer.nodes import Link, Node


def make_node(conn, node_id, body, **kwargs):
    node = Node(
        canon_id=db.next_free_canon_id(conn, kwargs.get("node_type", "idea"), node_id),
        node_id=node_id,
        node_type=kwargs.get("node_type", "idea"),
        status=kwargs.get("status", "active"),
        parent_root=kwargs.get("parent_root"),
        tags=kwargs.get("tags", ["domain/software"]),
        links=kwargs.get("links", []),
        summary=kwargs.get("summary", ""),
        body=body,
    )
    return db.upsert_node(conn, node)


def test_migrate_is_idempotent(conn):
    db.migrate(conn)
    db.migrate(conn)
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"graph", "graph_fts"} <= tables


def test_upsert_inserts_then_updates_same_row(conn):
    node = make_node(conn, "pricing", "flat per trip pricing")
    node.body = "flat per trip pricing, hourly retired"
    db.upsert_node(conn, node)
    rows = conn.execute("SELECT COUNT(*) AS n FROM graph").fetchone()["n"]
    assert rows == 1
    assert "hourly retired" in db.get_node(conn, node.canon_id).body


def test_fts_index_follows_updates_and_deletes(conn):
    node = make_node(conn, "pricing", "flat per trip pricing")
    assert db.search_nodes(conn, ["pricing"])

    node.body = "totally unrelated content about kangaroos"
    db.upsert_node(conn, node)
    assert not [n for n, _ in db.search_nodes(conn, ["flat"]) if n.canon_id == node.canon_id]
    assert db.search_nodes(conn, ["kangaroos"])

    conn.execute("DELETE FROM graph WHERE canon_id = ?", (node.canon_id,))
    conn.commit()
    assert not db.search_nodes(conn, ["kangaroos"])


def test_tags_and_links_round_trip_as_json(conn):
    node = make_node(
        conn, "spec", "the schema", tags=["domain/software", "tech/sqlite"],
        links=[Link(to="COS.IDEA.20260911.0400.X.001", relation="supports")],
    )
    raw = conn.execute("SELECT tags, links FROM graph WHERE canon_id=?", (node.canon_id,)).fetchone()
    assert json.loads(raw["tags"]) == ["domain/software", "tech/sqlite"]
    assert json.loads(raw["links"])[0]["relation"] == "supports"
    assert db.get_node(conn, node.canon_id).links[0].to == "COS.IDEA.20260911.0400.X.001"


def test_next_free_canon_id_bumps_sequence(conn):
    first = make_node(conn, "same_slug", "one").canon_id
    second = db.next_free_canon_id(conn, "idea", "same_slug")
    assert first != second


def test_list_nodes_filters_by_tag_via_json_each(conn):
    make_node(conn, "a", "alpha", tags=["status/active", "domain/software"])
    make_node(conn, "b", "beta", tags=["status/archived"])
    active = db.list_nodes(conn, tag="status/active")
    assert [n.node_id for n in active] == ["a"]


def test_nodes_with_link_to_finds_supporters(conn):
    target = make_node(conn, "target", "the decision").canon_id
    make_node(conn, "supporter", "backs it", links=[Link(to=target, relation="supports")])
    make_node(conn, "unrelated", "nothing", links=[])
    found = db.nodes_with_link_to(conn, target, relation="supports")
    assert [n.node_id for n in found] == ["supporter"]


def test_fts_query_neutralises_operators(conn):
    """User text containing FTS5 syntax must not blow up or change the query."""
    make_node(conn, "safe", "ordinary content here")
    assert db.search_nodes(conn, ['OR AND NOT "', "ordinary"]) is not None
    assert db.fts_query(["a"]) == ""  # too short to be a useful term


def test_score_against_is_term_coverage(conn):
    node = Node(canon_id="COS.IDEA.20260911.0400.X.001", node_id="x",
                node_type="idea", body="alpha beta")
    assert db.score_against(node, ["alpha", "beta"]) == 1.0
    assert db.score_against(node, ["alpha", "gamma"]) == 0.5
    assert db.score_against(node, []) == 0.0


def test_lookup_tolerates_invisible_characters(conn):
    node = make_node(conn, "pricing", "flat pricing")
    polluted = node.canon_id[:4] + "​" + node.canon_id[4:]
    assert db.get_node(conn, polluted) is not None


def test_migrating_an_existing_ddbos_database_leaves_it_intact(tmp_path):
    """The real deployment: graph lands beside Council/Memories/Skills/Dossier."""
    import sqlite3

    path = str(tmp_path / "ddbos.sqlite3")
    existing = sqlite3.connect(path)
    existing.execute("CREATE TABLE council (id INTEGER PRIMARY KEY, note TEXT)")
    existing.execute("INSERT INTO council (note) VALUES ('pre-existing row')")
    existing.commit()
    existing.close()

    conn = db.connect(path)
    make_node(conn, "pricing", "flat per trip pricing")
    conn.close()

    reopened = sqlite3.connect(path)
    reopened.row_factory = sqlite3.Row
    assert reopened.execute("SELECT note FROM council").fetchone()["note"] == "pre-existing row"
    assert reopened.execute("SELECT COUNT(*) AS n FROM graph").fetchone()["n"] == 1
    reopened.close()


def test_graph_survives_a_reopen(tmp_path):
    path = str(tmp_path / "ddbos.sqlite3")
    conn = db.connect(path)
    canon_id = make_node(conn, "pricing", "flat per trip pricing").canon_id
    conn.close()

    reopened = db.connect(path)
    assert db.get_node(reopened, canon_id) is not None
    assert db.search_nodes(reopened, ["pricing"])   # FTS index persisted too
    reopened.close()
