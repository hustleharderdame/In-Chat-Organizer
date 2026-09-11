"""
---
node_id: "cos_db_module"
node_type: "code"
version: "1.0.0"
status: "active"
single_source: true
tags:
  - "domain/software"
  - "status/active"
  - "tech/sqlite"
parent_node: "[[Master_OS_Hub]]"
linked_nodes:
  - "[[Chat_Root_Organizer_Service]]"
  - "[[DDB.OS]]"
---

Storage layer for [[Chat_Root_Organizer_Service]] — one master ``graph`` table
plus the ``graph_fts`` FTS5 index, added to the existing [[DDB.OS]] SQLite DB.

**Single writer.** Every ingestion path (native parsing, bridge paste-back,
retrieval) ends in :func:`upsert_node`. Nothing else writes ``graph``.

**Auto-build on ingestion.** :func:`migrate` is idempotent and cheap, so the
service calls it on open; the table then grows purely by upsert as chats land.

    db_table:: graph
    fts_table:: graph_fts
    owner:: [[Damien_Brock]]
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import canon
from .nodes import Node, utcnow

SCHEMA = """
CREATE TABLE IF NOT EXISTS graph (
  canon_id      TEXT PRIMARY KEY,
  node_id       TEXT NOT NULL,
  node_type     TEXT NOT NULL,
  parent_root   TEXT,
  status        TEXT NOT NULL,
  tags          TEXT,
  links         TEXT,
  summary       TEXT,
  body          TEXT,
  source_chat   TEXT,
  source_turn_kind TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS graph_parent_root_idx ON graph(parent_root);
CREATE INDEX IF NOT EXISTS graph_type_status_idx ON graph(node_type, status);
CREATE INDEX IF NOT EXISTS graph_updated_idx     ON graph(updated_at);

CREATE VIRTUAL TABLE IF NOT EXISTS graph_fts USING fts5(
  canon_id, body, tags, content='graph', content_rowid='rowid'
);

-- Keep graph_fts in lockstep with graph, so no writer can forget to refresh it.
CREATE TRIGGER IF NOT EXISTS graph_ai AFTER INSERT ON graph BEGIN
  INSERT INTO graph_fts(rowid, canon_id, body, tags)
  VALUES (new.rowid, new.canon_id, new.body, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS graph_ad AFTER DELETE ON graph BEGIN
  INSERT INTO graph_fts(graph_fts, rowid, canon_id, body, tags)
  VALUES ('delete', old.rowid, old.canon_id, old.body, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS graph_au AFTER UPDATE ON graph BEGIN
  INSERT INTO graph_fts(graph_fts, rowid, canon_id, body, tags)
  VALUES ('delete', old.rowid, old.canon_id, old.body, old.tags);
  INSERT INTO graph_fts(rowid, canon_id, body, tags)
  VALUES (new.rowid, new.canon_id, new.body, new.tags);
END;
"""


def connect(path: str = ":memory:", *, check_same_thread: bool = False) -> sqlite3.Connection:
    """Open the DDB.OS SQLite DB and make sure the organizer schema exists.

    ``check_same_thread`` defaults to False because any WSGI server — including
    the Flask dev server DDB.OS runs — dispatches requests on worker threads,
    while the connection is opened once at startup. Serialising concurrent use
    is then the connection owner's job; :class:`chat_organizer.service.Organizer`
    holds a lock for exactly this reason.

    ``busy_timeout`` matters because the organizer shares one SQLite file with
    the rest of DDB.OS: without it, a write held by another component surfaces
    here as an immediate "database is locked" instead of a short wait.
    """
    conn = sqlite3.connect(path, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Idempotent migration: ``graph`` + ``graph_fts`` + sync triggers."""
    conn.executescript(SCHEMA)
    conn.commit()


# --- writes ------------------------------------------------------------------
_UPSERT = """
INSERT INTO graph (canon_id, node_id, node_type, parent_root, status, tags,
                   links, summary, body, source_chat, source_turn_kind,
                   created_at, updated_at)
VALUES (:canon_id, :node_id, :node_type, :parent_root, :status, :tags,
        :links, :summary, :body, :source_chat, :source_turn_kind,
        :created_at, :updated_at)
ON CONFLICT(canon_id) DO UPDATE SET
  node_id          = excluded.node_id,
  node_type        = excluded.node_type,
  parent_root      = excluded.parent_root,
  status           = excluded.status,
  tags             = excluded.tags,
  links            = excluded.links,
  summary          = excluded.summary,
  body             = excluded.body,
  source_chat      = COALESCE(excluded.source_chat, graph.source_chat),
  source_turn_kind = COALESCE(excluded.source_turn_kind, graph.source_turn_kind),
  updated_at       = excluded.updated_at
"""


def upsert_node(conn: sqlite3.Connection, node: Node, *, commit: bool = True) -> Node:
    """The single write path into ``graph``. Returns the stored node.

    Native parsing, bridge paste-back and retrieval all funnel through here —
    the table grows by upsert, there is no per-chat migration step.
    """
    node.canon_id = canon.validate(node.canon_id)
    node.updated_at = utcnow()
    conn.execute(_UPSERT, node.to_row())
    if commit:
        conn.commit()
    stored = get_node(conn, node.canon_id)
    assert stored is not None
    return stored


def next_free_canon_id(
    conn: sqlite3.Connection, node_type: str, object_slug: str, **kwargs: Any
) -> str:
    """Mint a canon ID and bump SEQ until it is unused in ``graph``."""
    for seq in range(1, 1000):
        candidate = canon.mint(node_type, object_slug, seq=seq, **kwargs)
        row = conn.execute(
            "SELECT 1 FROM graph WHERE canon_id = ?", (candidate,)
        ).fetchone()
        if row is None:
            return candidate
    raise RuntimeError(f"canon ID space exhausted for {node_type}/{object_slug}")


# --- reads -------------------------------------------------------------------
def get_node(conn: sqlite3.Connection, canon_id: str) -> Optional[Node]:
    row = conn.execute(
        "SELECT * FROM graph WHERE canon_id = ?", (canon.scrub(canon_id),)
    ).fetchone()
    return Node.from_row(row) if row else None


def list_nodes(
    conn: sqlite3.Connection,
    *,
    tag: Optional[str] = None,
    node_type: Optional[str] = None,
    status: Optional[str] = None,
    parent_root: Optional[str] = None,
    order_by: str = "updated_at",
    descending: bool = True,
    limit: int = 200,
    offset: int = 0,
) -> List[Node]:
    """Table view — the Dataview-table equivalent from the protocol Section 5."""
    where: List[str] = []
    params: List[Any] = []
    if tag:
        # tags is a JSON array on the row, so filter with json_each rather than
        # a join table. See the open question in [[Claude_Code_Implementation_Report]].
        where.append(
            "EXISTS (SELECT 1 FROM json_each(graph.tags) WHERE json_each.value = ?)"
        )
        params.append(tag)
    if node_type:
        where.append("node_type = ?")
        params.append(node_type)
    if status:
        where.append("status = ?")
        params.append(status)
    if parent_root:
        where.append("parent_root = ?")
        params.append(canon.scrub(parent_root))

    allowed_order = {"updated_at", "created_at", "node_id", "node_type", "status"}
    if order_by not in allowed_order:
        order_by = "updated_at"
    direction = "DESC" if descending else "ASC"
    sql = "SELECT * FROM graph"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {order_by} {direction} LIMIT ? OFFSET ?"
    params.extend([max(1, min(limit, 1000)), max(0, offset)])
    return [Node.from_row(r) for r in conn.execute(sql, params)]


def nodes_with_link_to(
    conn: sqlite3.Connection, target: str, relation: Optional[str] = None
) -> List[Node]:
    """'Find everything that supports X' — json_each over the links column."""
    sql = """
    SELECT graph.* FROM graph, json_each(graph.links)
    WHERE json_extract(json_each.value, '$.to') = ?
    """
    params: List[Any] = [canon.scrub(target)]
    if relation:
        sql += " AND json_extract(json_each.value, '$.relation') = ?"
        params.append(relation)
    sql += " ORDER BY graph.updated_at DESC"
    return [Node.from_row(r) for r in conn.execute(sql, params)]


# --- FTS5 --------------------------------------------------------------------
_FTS_UNSAFE = re.compile(r'[^0-9A-Za-z_/\-]+')


def fts_query(terms: Sequence[str]) -> str:
    """Build a safe FTS5 MATCH expression from free-text keywords.

    Every term is quoted, so FTS5 operators inside user text are inert.
    """
    quoted = []
    for term in terms:
        cleaned = _FTS_UNSAFE.sub(" ", canon.scrub(term)).strip()
        if len(cleaned) < 2:
            continue
        quoted.append('"' + cleaned.replace('"', "") + '"')
    return " OR ".join(quoted)


def score_against(node: Node, terms: Sequence[str]) -> float:
    """Fraction of distinct query terms that appear in the node's text.

    Deterministic and explainable, unlike a raw bm25() magnitude, so the
    create-vs-update threshold and the ambiguity threshold mean the same thing
    across databases of any size.
    """
    wanted = {canon.scrub(t).lower() for t in terms}
    wanted = {t for t in wanted if len(t) >= 2}
    if not wanted:
        return 0.0
    haystack = " ".join(
        [node.node_id, node.summary, node.body, " ".join(node.tags)]
    ).lower()
    hits = sum(1 for t in wanted if t in haystack)
    return hits / len(wanted)


def search_nodes(
    conn: sqlite3.Connection, terms: Sequence[str], *, limit: int = 10
) -> List[Tuple[Node, float]]:
    """FTS5 candidate fetch over ``graph_fts``, re-scored by term coverage.

    FTS5 does the cheap narrowing (this is the 4GB-RAM device constraint: no
    vector DB, no full scan); :func:`score_against` then produces the 0..1 score
    that the parsing and retrieval layers threshold on. Returns best-first.
    """
    match = fts_query(terms)
    if not match:
        return []
    rows = conn.execute(
        """
        SELECT graph.*, bm25(graph_fts) AS rank
        FROM graph_fts JOIN graph ON graph.rowid = graph_fts.rowid
        WHERE graph_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (match, max(1, min(limit, 100)) * 4),
    ).fetchall()
    scored = []
    for position, row in enumerate(rows):
        node = Node.from_row(row)
        scored.append((node, score_against(node, terms), position))
    # Sort by coverage, then by FTS rank order as the tie-breaker.
    scored.sort(key=lambda item: (-item[1], item[2]))
    return [(node, score) for node, score, _ in scored[: max(1, min(limit, 100))]]


def counts_by_status(conn: sqlite3.Connection) -> Dict[str, int]:
    return {
        r["status"]: r["n"]
        for r in conn.execute("SELECT status, COUNT(*) AS n FROM graph GROUP BY status")
    }
