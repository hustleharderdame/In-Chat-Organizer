"""
---
node_id: "cos_parser_module"
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

Parsing layer for [[Chat_Root_Organizer_Service]] — protocol Sections 2, 8, 9.

``parse_message`` is **pure**: it never touches SQLite. Existing-node matching is
injected as a ``matcher`` callable so classification and reconciliation can be
unit-tested with no database at all. ``apply`` is the only function here that
writes, and it writes solely through :func:`chat_organizer.db.upsert_node`.

    entrypoint:: parse_message(text) -> list[NodeOp]
    writer:: apply(conn, op) -> Node | None
    owner:: [[Damien_Brock]]
"""

from __future__ import annotations

import re
import sqlite3
from typing import Callable, List, Optional, Sequence, Tuple

from . import db
from .nodes import Link, Node, NodeOp, utcnow

Matcher = Callable[[Sequence[str]], List[Tuple[Node, float]]]

# --- reconciliation thresholds (protocol Section 9) --------------------------
#: Coverage at or above this means "this is the same node" -> update, not create.
UPDATE_THRESHOLD = 0.75
#: If a runner-up is this close to the winner, we refuse to pick. Ambiguity is
#: escalated as a question op — silently resolving it is a bug, not a feature.
AMBIGUITY_DELTA = 0.15

# --- filler detection (protocol Section 8) ----------------------------------
_FILLER_PATTERNS = (
    r"^(ok(ay)?|k|kk|yes|yep|yeah|no|nope|sure|right|got it|gotcha|understood)\b",
    r"^(thanks|thank you|ty|cheers|nice|cool|great|perfect|awesome|love it|lol|haha)\b",
    r"^(hi|hey|hello|yo|morning|good morning|good evening|sup)\b",
    r"^(np|no problem|you're welcome|anytime|sounds good|works for me|agreed)\b",
    r"^(continue|go on|next|carry on|keep going|do it|proceed)\b",
    r"^(one sec|hold on|wait|brb|back)\b",
)
_FILLER_RE = re.compile("|".join(_FILLER_PATTERNS), re.IGNORECASE)
_MIN_DURABLE_WORDS = 4

# --- classification cues -----------------------------------------------------
_RELATIONSHIP_RE = re.compile(
    r"\b(depends on|blocked by|blocks|supersedes|superseded by|replaces|"
    r"feeds into|belongs to|part of|supports|contradicts|relates to|"
    r"is a child of|rolls up to)\b",
    re.IGNORECASE,
)
_DECISION_RE = re.compile(
    r"\b(decided|decision|we(?:'re| are) going with|going with|locked(?: in)?|"
    r"settled on|final(?:ised|ized)?|we(?:'ll| will) use|chose|choosing|"
    r"ruling out|not doing|instead of|canon(?:ical)?(?: now)?)\b",
    re.IGNORECASE,
)
_QUESTION_RE = re.compile(
    r"(\?\s*$)|\b(open question|not sure (?:if|whether)|what about|should we|"
    r"do we want|which one|tbd|to be decided)\b",
    re.IGNORECASE,
)
_TASK_RE = re.compile(
    r"^\s*(?:[-*]\s*)?\[\s\]|"
    r"\b(todo|to-do|action item|next step|needs? to|have to|must (?:add|build|wire|write|ship)|"
    r"let'?s |we should|i should|you should|remind me to|don'?t forget|"
    r"build |implement |wire |add |write |ship |fix |migrate |deploy )",
    re.IGNORECASE,
)
_SPEC_RE = re.compile(
    r"```|\b(schema|ddl|endpoint|api|signature|format is|the format|contract|"
    r"spec(?:ification)?|must (?:be|have|match|contain)|always |never |"
    r"column|table|field|payload|protocol)\b",
    re.IGNORECASE,
)
_ROOT_RE = re.compile(
    r"\b(new (?:project|root|thread|workstream)|starting (?:a )?new|"
    r"this (?:whole )?(?:project|thread) is about|root node)\b",
    re.IGNORECASE,
)

# --- tag vocabulary ----------------------------------------------------------
_TECH_TAGS = {
    "sqlite": "tech/sqlite",
    "fts5": "tech/sqlite",
    "flask": "tech/flask",
    "python": "tech/python",
    "claude code": "tech/claude-code",
    "claude-code": "tech/claude-code",
    "mcp": "tech/mcp",
    "json": "tech/json",
    "termux": "tech/termux",
    "obsidian": "tech/obsidian",
    "dataview": "tech/obsidian",
    "git": "tech/git",
    "api": "tech/api",
}
_DOMAIN_TAGS = {
    "domain/software": (
        "code",
        "schema",
        "database",
        "endpoint",
        "parser",
        "service",
        "migration",
        "function",
        "repo",
        "deploy",
    ),
    "domain/business-ops": ("invoice", "client", "revenue", "ops", "driver", "dispatch", "booking"),
    "domain/brand": ("brand", "logo", "voice", "tone", "copy", "positioning"),
}
_STATUS_BY_TYPE = {
    "root": "status/active",
    "idea": "status/planning",
    "task": "status/active",
    "decision": "status/active",
    "spec": "status/active",
    "question": "status/planning",
    "relationship": "status/active",
}
_NODE_STATUS_BY_TYPE = {
    "root": "active",
    "idea": "planning",
    "task": "active",
    "decision": "active",
    "spec": "active",
    "question": "planning",
    "relationship": "active",
}

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "so", "of", "to", "in",
    "on", "for", "with", "at", "by", "from", "as", "is", "are", "was", "were",
    "be", "been", "being", "it", "its", "this", "that", "these", "those", "we",
    "i", "you", "he", "she", "they", "our", "your", "my", "me", "us", "them",
    "will", "would", "can", "could", "should", "shall", "may", "might", "do",
    "does", "did", "done", "have", "has", "had", "not", "no", "yes", "just",
    "about", "into", "than", "too", "very", "also", "up", "out", "over",
}


# --- helpers -----------------------------------------------------------------
def is_filler(text: str) -> bool:
    """True when a turn carries nothing durable (protocol Section 8)."""
    stripped = text.strip()
    if not stripped:
        return True
    if _FILLER_RE.match(stripped) and len(stripped.split()) <= 6:
        return True
    words = re.findall(r"[A-Za-z0-9]+", stripped)
    if len(words) < _MIN_DURABLE_WORDS:
        return True
    return False


def classify(text: str) -> str:
    """Map a durable unit onto one of the seven node types.

    Order matters: a decision that happens to look like a spec is a decision,
    and a question that happens to contain an imperative is still a question.
    """
    if _ROOT_RE.search(text):
        return "root"
    if _RELATIONSHIP_RE.search(text):
        return "relationship"
    if _DECISION_RE.search(text):
        return "decision"
    if _QUESTION_RE.search(text):
        return "question"
    if _TASK_RE.search(text):
        return "task"
    if _SPEC_RE.search(text):
        return "spec"
    return "idea"


def split_units(text: str) -> List[str]:
    """Split one message into candidate node units.

    Fenced code blocks are kept whole — a DDL block is one spec, not six lines.
    """
    units: List[str] = []
    chunks = re.split(r"(```.*?```)", text, flags=re.DOTALL)
    for chunk in chunks:
        if not chunk.strip():
            continue
        if chunk.startswith("```"):
            units.append(chunk.strip())
            continue
        for block in re.split(r"\n\s*\n", chunk):
            block = block.strip()
            if not block:
                continue
            lines = [l.strip() for l in block.splitlines() if l.strip()]
            bullets = [l for l in lines if re.match(r"^(?:[-*+]|\d+[.)])\s+", l)]
            if len(bullets) >= 2 and len(bullets) == len(lines):
                units.extend(re.sub(r"^(?:[-*+]|\d+[.)])\s+", "", l) for l in bullets)
            else:
                units.append(block)
    return units


def keywords(text: str, limit: int = 8) -> List[str]:
    """Salient words for FTS matching — stopwords out, order preserved."""
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}", text.lower())
    out: List[str] = []
    for word in words:
        if word in _STOPWORDS or len(word) < 3:
            continue
        if word not in out:
            out.append(word)
        if len(out) >= limit:
            break
    return out


def derive_tags(text: str, node_type: str) -> List[str]:
    """Hierarchical tags per [[Master_OS_Hub]] conventions: domain / status / tech."""
    lowered = text.lower()
    tags = [f"type/{node_type}", _STATUS_BY_TYPE.get(node_type, "status/active")]
    for tag, cues in _DOMAIN_TAGS.items():
        if any(cue in lowered for cue in cues):
            tags.append(tag)
            break
    else:
        tags.append("domain/software")
    for cue, tag in _TECH_TAGS.items():
        if cue in lowered and tag not in tags:
            tags.append(tag)
    return list(dict.fromkeys(tags))


def derive_links(text: str) -> List[Link]:
    """Pull explicit [[WikiLinks]] and bare canon IDs out of the text."""
    from . import canon

    links: List[Link] = []
    relation_match = _RELATIONSHIP_RE.search(text)
    relation = (
        re.sub(r"\s+", "_", relation_match.group(0).strip().lower())
        if relation_match
        else "relates_to"
    )
    for target in re.findall(r"\[\[([^\]]+)\]\]", text):
        links.append(Link(to=target.strip(), relation=relation))
    for token in re.findall(r"\b[A-Z][A-Z0-9]{1,15}\.[A-Z][A-Z0-9]{1,23}\.\d{8}\.\d{4}\.[A-Za-z0-9_-]+\.\d{3,4}\b", text):
        if canon.is_valid(token):
            links.append(Link(to=canon.scrub(token), relation=relation))
    seen = {}
    for link in links:
        seen.setdefault(link.to + "|" + link.relation, link)
    return list(seen.values())


def derive_node_id(text: str) -> str:
    """Human slug for the node — lowercase, underscore-joined, stable-ish."""
    words = [w for w in keywords(text, limit=5)]
    if not words:
        words = re.findall(r"[a-z0-9]+", text.lower())[:3] or ["node"]
    return "_".join(words)[:64]


def summarise(text: str, limit: int = 180) -> str:
    flat = re.sub(r"\s+", " ", text.strip())
    if flat.startswith("```"):
        flat = re.sub(r"^```\w*\s*", "", flat).rstrip("` ")
    sentence = re.split(r"(?<=[.!?])\s+", flat)[0]
    out = sentence if len(sentence) <= limit else flat[:limit].rsplit(" ", 1)[0]
    return out.strip()


# --- the entrypoint ----------------------------------------------------------
def parse_message(
    text: str,
    *,
    matcher: Optional[Matcher] = None,
    parent_root: Optional[str] = None,
    source_chat: Optional[str] = None,
    source_turn_kind: Optional[str] = None,
) -> List[NodeOp]:
    """Classify a chat turn and emit the graph writes it implies.

    Pure: no SQLite, no clock-dependent IDs. ``matcher`` (usually
    ``partial(db.search_nodes, conn)``) supplies existing-node candidates; with
    no matcher every durable unit becomes a ``create``.
    """
    from . import canon

    ops: List[NodeOp] = []
    if is_filler(text):
        return [NodeOp("skip", reason="filler turn — nothing durable")]

    for unit in split_units(text):
        if is_filler(unit):
            continue
        node_type = classify(unit)
        node = Node(
            canon_id="PENDING.NODE.00000000.0000.Pending.001",
            node_id=derive_node_id(unit),
            node_type=node_type,
            status=_NODE_STATUS_BY_TYPE.get(node_type, "active"),
            parent_root=canon.scrub(parent_root) or None,
            tags=derive_tags(unit, node_type),
            links=derive_links(unit),
            summary=summarise(unit),
            body=unit,
            source_chat=source_chat,
            source_turn_kind=source_turn_kind,
        )
        terms = keywords(unit)
        candidates = matcher(terms) if matcher and terms else []
        ops.append(_reconcile(node, candidates))
    if not ops:
        ops.append(NodeOp("skip", reason="no durable units in turn"))
    return ops


def _reconcile(node: Node, candidates: List[Tuple[Node, float]]) -> NodeOp:
    """Create-vs-update, with mandatory ambiguity escalation (Section 9).

    When two stored nodes are equally plausible targets we never pick one — we
    hand both back as a question. Silent resolution is a bug.
    """
    # An injected matcher is not required to sort, so sort here rather than
    # trusting the caller — a mis-ordered list must not turn into a wrong pick.
    strong = sorted(
        ((c, s) for c, s in candidates if s >= UPDATE_THRESHOLD),
        key=lambda pair: -pair[1],
    )
    if not strong:
        return NodeOp(
            "create",
            node=node,
            reason=f"no stored node scored >= {UPDATE_THRESHOLD}",
            confidence=candidates[0][1] if candidates else 0.0,
        )

    best_node, best_score = strong[0]
    rivals = [(c, s) for c, s in strong[1:] if best_score - s <= AMBIGUITY_DELTA]
    if rivals:
        options = [(best_node, best_score), *rivals]
        return NodeOp(
            "question",
            node=node,
            question=(
                f"This turn could be an update to {len(options)} existing nodes. "
                "Which one should it fold into (or is it a new node)?"
            ),
            candidates=[
                {"canon_id": c.canon_id, "node_id": c.node_id, "summary": c.summary,
                 "score": round(s, 3)}
                for c, s in options
            ],
            reason="ambiguous match — refusing to auto-pick (protocol Section 6/9)",
            confidence=best_score,
        )

    return NodeOp(
        "update",
        node=node,
        target_canon_id=best_node.canon_id,
        reason=f"matched stored node {best_node.node_id} at {best_score:.2f}",
        confidence=best_score,
    )


# --- the writer --------------------------------------------------------------
def apply(conn: sqlite3.Connection, op: NodeOp, *, commit: bool = True) -> Optional[Node]:
    """Perform a :class:`NodeOp` against ``graph``. Returns the stored node.

    ``question`` and ``skip`` ops write nothing and return ``None`` — that is the
    point of them.
    """
    if op.kind in ("skip", "question"):
        return None

    if op.kind == "create":
        assert op.node is not None
        node = op.node
        node.canon_id = db.next_free_canon_id(conn, node.node_type, node.node_id)
        node.created_at = utcnow()
        node.updated_at = node.created_at
        if node.node_type == "root" and not node.parent_root:
            node.parent_root = node.canon_id
        return db.upsert_node(conn, node, commit=commit)

    target_id = op.target_canon_id
    if op.kind == "update":
        assert op.node is not None and target_id
        stored = db.get_node(conn, target_id)
        if stored is None:
            raise KeyError(f"update target not in graph: {target_id}")
        return db.upsert_node(conn, stored.merged_with(op.node), commit=commit)

    if op.kind in ("link", "tag"):
        assert target_id
        stored = db.get_node(conn, target_id)
        if stored is None:
            raise KeyError(f"{op.kind} target not in graph: {target_id}")
        if op.kind == "link":
            existing = {l.to + "|" + l.relation for l in stored.links}
            stored.links.extend(
                l for l in op.links if l.to + "|" + l.relation not in existing
            )
        else:
            stored.tags = list(dict.fromkeys([*stored.tags, *op.tags]))
        return db.upsert_node(conn, stored, commit=commit)

    raise ValueError(f"cannot apply op kind {op.kind!r}")
