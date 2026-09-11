"""
---
node_id: "cos_service_module"
node_type: "code"
version: "1.0.0"
status: "active"
single_source: true
tags:
  - "domain/software"
  - "status/active"
  - "tech/python"
parent_node: "[[Master_OS_Hub]]"
linked_nodes:
  - "[[Chat_Root_Organizer_Service]]"
  - "[[COS_Root_Organizer_Protocol]]"
---

Orchestration for [[Chat_Root_Organizer_Service]] — the one object a host holds.

Every ingestion path converges here and leaves through
:func:`chat_organizer.db.upsert_node`. ``Organizer`` owns the connection and the
optional chat-search provider; the parsing and retrieval modules stay pure.

    entrypoint:: Organizer(db_path).ingest(text)
    owner:: [[Damien_Brock]]
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Dict, List, Optional

from . import bridge, db, parser, retrieval
from .nodes import Node, NodeOp
from .retrieval import ChatSearchProvider


@dataclass
class IngestResult:
    """What one turn did to the graph, and what it needs Dame to answer."""

    path: str
    ops: List[NodeOp] = field(default_factory=list)
    written: List[Node] = field(default_factory=list)
    questions: List[NodeOp] = field(default_factory=list)
    retrieval_triggered: bool = False
    keywords: List[str] = field(default_factory=list)
    hits: List[retrieval.ChatHit] = field(default_factory=list)

    @property
    def needs_answer(self) -> bool:
        return bool(self.questions)

    def to_json(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "retrieval_triggered": self.retrieval_triggered,
            "keywords": list(self.keywords),
            "hits": [h.to_json() for h in self.hits],
            "written": [n.to_json() for n in self.written],
            "questions": [q.to_json() for q in self.questions],
            "ops": [o.to_json() for o in self.ops],
            "needs_answer": self.needs_answer,
        }


class Organizer:
    """The Chat Root Organizer service.

    Instantiate once per process against the existing DDB.OS SQLite file::

        org = Organizer("/home/dame/ddbos/ddb.sqlite3")
        result = org.ingest("We're going with flat per-trip pricing.")
    """

    def __init__(
        self,
        db_path: str = ":memory:",
        *,
        provider: Optional[ChatSearchProvider] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        self.conn = conn if conn is not None else db.connect(db_path)
        if conn is not None:
            db.migrate(self.conn)
        self.provider = provider

    # --- read-side helper handed to the pure parsers -------------------
    @property
    def matcher(self) -> parser.Matcher:
        return partial(db.search_nodes, self.conn)

    # --- the one ingestion entrypoint ----------------------------------
    def ingest(
        self,
        text: str,
        *,
        parent_root: Optional[str] = None,
        source_chat: Optional[str] = None,
        source_turn_kind: Optional[str] = "human",
        apply_ops: bool = True,
    ) -> IngestResult:
        """Route one chat turn: bridge paste, retrieval request, or native turn."""
        if bridge.looks_like_bridge_paste(text):
            ops = bridge.parse_bridge_paste(
                text,
                matcher=self.matcher,
                parent_root=parent_root,
                source_chat=source_chat,
            )
            result = IngestResult(path="bridge", ops=ops)
        else:
            ops = parser.parse_message(
                text,
                matcher=self.matcher,
                parent_root=parent_root,
                source_chat=source_chat,
                source_turn_kind=source_turn_kind,
            )
            result = IngestResult(path="native", ops=ops)
            # A retrieval request is *also* a durable turn: it gets organised
            # and searched, it does not get swallowed by the search.
            if retrieval.detect_retrieval_trigger(text):
                result.retrieval_triggered = True
                result.keywords = retrieval.extract_keywords(text)
                result.hits = retrieval.search_past_chats(
                    result.keywords, self.provider
                )
                result.ops.append(retrieval.resolve_hits(result.hits, text))

        if apply_ops:
            self._apply_all(result)
        else:
            result.questions = [o for o in result.ops if o.kind == "question"]
        return result

    def _apply_all(self, result: IngestResult) -> None:
        for op in result.ops:
            if op.kind == "question":
                result.questions.append(op)
                continue
            stored = parser.apply(self.conn, op, commit=False)
            if stored is not None:
                result.written.append(stored)
        self.conn.commit()

    # --- explicit retrieval, for a host that wants it on its own -------
    def recall(self, text: str) -> IngestResult:
        """Run only the retrieval path for a turn, writing nothing on ambiguity."""
        result = IngestResult(path="recall", retrieval_triggered=True)
        result.keywords = retrieval.extract_keywords(text)
        result.hits = retrieval.search_past_chats(result.keywords, self.provider)
        op = retrieval.resolve_hits(result.hits, text)
        result.ops.append(op)
        self._apply_all(result)
        return result

    def answer_ambiguity(self, chosen: Dict[str, Any], *, parent_root: Optional[str] = None) -> Node:
        """Land the candidate Dame picked after a question op.

        Accepts either a retrieval candidate (``chat_id``) or a graph candidate
        (``canon_id``) — the two shapes a question op can carry.
        """
        if chosen.get("canon_id"):
            stored = db.get_node(self.conn, chosen["canon_id"])
            if stored is None:
                raise KeyError(f"no such node: {chosen['canon_id']}")
            return stored
        hit = retrieval.ChatHit(
            chat_id=str(chosen.get("chat_id", "")),
            title=str(chosen.get("title", "")),
            excerpt=str(chosen.get("excerpt", "")),
            score=float(chosen.get("score", 1.0)),
            url=chosen.get("url"),
            provider=str(chosen.get("provider", "")),
        )
        return retrieval.ingest_hit(self.conn, hit, parent_root=parent_root)

    # --- read helpers used by the Flask endpoints ----------------------
    def nodes(self, **kwargs: Any) -> List[Node]:
        return db.list_nodes(self.conn, **kwargs)

    def open_tasks(self, group_by: str = "parent_root") -> Dict[str, List[Node]]:
        """Open tasks grouped for the Dataview-task-group equivalent."""
        tasks = db.list_nodes(
            self.conn, node_type="task", limit=1000, order_by="updated_at"
        )
        grouped: Dict[str, List[Node]] = {}
        for task in tasks:
            if task.status not in ("active", "planning"):
                continue
            key = str(getattr(task, group_by, None) or "ungrouped")
            grouped.setdefault(key, []).append(task)
        return grouped

    def close(self) -> None:
        self.conn.close()
