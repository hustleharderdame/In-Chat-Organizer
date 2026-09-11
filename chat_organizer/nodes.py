"""
---
node_id: "cos_nodes_module"
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

Value types for [[Chat_Root_Organizer_Service]]: ``Node``, ``Link``, ``NodeOp``.

SSOT for the row shape is the ``graph`` DDL in [[Chat_Root_Organizer_Service]]
Section 2; :class:`Node` mirrors it one-to-one and nothing else re-declares it.

``NodeOp`` is the pure output of ``parse_message`` — it describes an intended
write without performing one, so classification stays testable without a DB.

    owner:: [[Damien_Brock]]
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

NODE_TYPES = (
    "root",
    "idea",
    "task",
    "decision",
    "spec",
    "question",
    "relationship",
)

STATUSES = ("active", "planning", "archived", "superseded")

# NodeOp kinds. 'question' is not a write: it is the mandatory ambiguity
# escalation from the protocol (Section 6, Step 4 / Section 9 reconciliation).
OP_KINDS = ("create", "update", "link", "tag", "question", "skip")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Link:
    """A typed edge to another node, stored inside ``graph.links`` as JSON."""

    to: str
    relation: str = "relates_to"

    def as_dict(self) -> Dict[str, str]:
        return {"to": self.to, "relation": self.relation}

    @classmethod
    def from_any(cls, value: Any) -> "Link":
        if isinstance(value, Link):
            return value
        if isinstance(value, dict):
            return cls(to=str(value.get("to", "")), relation=str(value.get("relation") or "relates_to"))
        return cls(to=str(value))


@dataclass
class Node:
    """One row of ``graph``. Tags and links live on the row, not in join tables."""

    canon_id: str
    node_id: str
    node_type: str
    status: str = "active"
    parent_root: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    links: List[Link] = field(default_factory=list)
    summary: str = ""
    body: str = ""
    source_chat: Optional[str] = None
    source_turn_kind: Optional[str] = None
    created_at: str = field(default_factory=utcnow)
    updated_at: str = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        self.links = [Link.from_any(link) for link in self.links]
        self.tags = [t for t in dict.fromkeys(self.tags) if t]

    # --- serialisation -------------------------------------------------
    def to_row(self) -> Dict[str, Any]:
        return {
            "canon_id": self.canon_id,
            "node_id": self.node_id,
            "node_type": self.node_type,
            "parent_root": self.parent_root,
            "status": self.status,
            "tags": json.dumps(self.tags),
            "links": json.dumps([l.as_dict() for l in self.links]),
            "summary": self.summary,
            "body": self.body,
            "source_chat": self.source_chat,
            "source_turn_kind": self.source_turn_kind,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: Any) -> "Node":
        data = dict(row)
        return cls(
            canon_id=data["canon_id"],
            node_id=data["node_id"],
            node_type=data["node_type"],
            status=data["status"],
            parent_root=data.get("parent_root"),
            tags=json.loads(data.get("tags") or "[]"),
            links=[Link.from_any(l) for l in json.loads(data.get("links") or "[]")],
            summary=data.get("summary") or "",
            body=data.get("body") or "",
            source_chat=data.get("source_chat"),
            source_turn_kind=data.get("source_turn_kind"),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    def to_json(self) -> Dict[str, Any]:
        """API-shaped dict: tags/links as real lists, not JSON strings."""
        return {
            "canon_id": self.canon_id,
            "node_id": self.node_id,
            "node_type": self.node_type,
            "parent_root": self.parent_root,
            "status": self.status,
            "tags": list(self.tags),
            "links": [l.as_dict() for l in self.links],
            "summary": self.summary,
            "body": self.body,
            "source_chat": self.source_chat,
            "source_turn_kind": self.source_turn_kind,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def merged_with(self, other: "Node") -> "Node":
        """Fold an incoming node into this stored one (update reconciliation).

        Body is appended rather than replaced so a chat never silently destroys
        earlier reasoning; tags and links union; ``created_at`` is preserved.
        """
        body = self.body
        incoming = (other.body or "").strip()
        if incoming and incoming not in self.body:
            body = f"{self.body.rstrip()}\n\n{incoming}".strip()
        seen: Dict[str, Link] = {l.to + "|" + l.relation: l for l in self.links}
        for link in other.links:
            seen.setdefault(link.to + "|" + link.relation, link)
        return replace(
            self,
            node_type=other.node_type or self.node_type,
            status=other.status or self.status,
            parent_root=other.parent_root or self.parent_root,
            tags=list(dict.fromkeys([*self.tags, *other.tags])),
            links=list(seen.values()),
            summary=other.summary or self.summary,
            body=body,
            source_chat=other.source_chat or self.source_chat,
            source_turn_kind=other.source_turn_kind or self.source_turn_kind,
            updated_at=utcnow(),
        )


@dataclass
class NodeOp:
    """An intended graph write. Pure data — ``apply()`` is what touches SQLite."""

    kind: str
    node: Optional[Node] = None
    target_canon_id: Optional[str] = None
    links: List[Link] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    reason: str = ""
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    question: str = ""
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if self.kind not in OP_KINDS:
            raise ValueError(f"unknown NodeOp kind: {self.kind!r}")
        self.links = [Link.from_any(l) for l in self.links]

    def to_json(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "node": self.node.to_json() if self.node else None,
            "target_canon_id": self.target_canon_id,
            "links": [l.as_dict() for l in self.links],
            "tags": list(self.tags),
            "reason": self.reason,
            "candidates": list(self.candidates),
            "question": self.question,
            "confidence": round(self.confidence, 3),
        }
