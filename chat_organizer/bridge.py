"""
---
node_id: "cos_bridge_module"
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
  - "[[Chat_Root_Organizer_Bridge_Block]]"
---

Bridge paste-back path (protocol Section 13.1 / report Section 4, path 2).

The cheapest possible ingestion route and the first one built: Dame pastes
:data:`BRIDGE_PROMPT` into any chat, that chat's assistant answers with one
filled-in canon block, Dame pastes the reply back here. No backend, no crawler,
no host tools — it works today.

A bridge block is **pre-structured text, not a new document type**. Explicit
fields win; anything the far-side assistant left out is derived by the ordinary
:mod:`chat_organizer.parser` helpers, and every block goes through the same
``_reconcile`` create-vs-update logic — including its ambiguity escalation.

    block_open:: ===COS-BRIDGE-V1===
    block_close:: ===END-COS-BRIDGE===
    owner:: [[Damien_Brock]]
"""

from __future__ import annotations

import re
import textwrap
from typing import Dict, List, Optional, Tuple

from . import canon
from .nodes import Link, Node, NodeOp
from .parser import (
    Matcher,
    _reconcile,
    classify,
    derive_links,
    derive_node_id,
    derive_tags,
    keywords,
    summarise,
)

OPEN_MARKER = "===COS-BRIDGE-V1==="
CLOSE_MARKER = "===END-COS-BRIDGE==="

_BLOCK_RE = re.compile(
    re.escape(OPEN_MARKER) + r"\s*(.*?)\s*" + re.escape(CLOSE_MARKER),
    re.DOTALL,
)
# Tolerated alternative: a plain YAML front-matter block, since that is the
# house format and far-side assistants reach for it by reflex.
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*$", re.DOTALL | re.MULTILINE)

_KNOWN_FIELDS = {
    "canon_id", "node_id", "node_type", "parent_root", "status", "tags",
    "links", "summary", "body", "source_chat", "source_turn_kind",
}

#: What Dame pastes into the far-side chat. Kept here as the SSOT for the
#: prompt text so it is never re-typed by hand in two places.
BRIDGE_PROMPT = f"""\
Summarise everything durable from this conversation as canon blocks for my
graph. Emit one block per durable item (idea, task, decision, spec, question,
relationship). Skip small talk. Use exactly this format, nothing else:

{OPEN_MARKER}
node_id: short_slug_here
node_type: idea | task | decision | spec | question | relationship
status: active | planning | archived | superseded
tags: domain/x, status/y, tech/z
links: supports -> Other_Node, depends on -> Another_Node
summary: one line
source_chat: <title or url of this chat>
body:
  The full durable content, indented or not — everything up to the closing
  marker is the body.
{CLOSE_MARKER}
"""


def extract_blocks(text: str) -> List[str]:
    """Pull every bridge block out of a pasted reply. Order is preserved."""
    blocks = [m.group(1) for m in _BLOCK_RE.finditer(text or "")]
    if blocks:
        return blocks
    return [m.group(1) for m in _FRONTMATTER_RE.finditer(text or "")]


def parse_block_fields(block: str) -> Tuple[Dict[str, str], str]:
    """Split a block into its ``key: value`` fields and its free-text body.

    Everything after a ``body:`` line belongs to the body, verbatim, so DDL and
    prose survive the round trip intact.
    """
    fields: Dict[str, str] = {}
    body_lines: List[str] = []
    in_body = False

    for line in (block or "").splitlines():
        if in_body:
            body_lines.append(line)
            continue
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*::?\s*(.*)$", line)
        if match and match.group(1).lower() in _KNOWN_FIELDS:
            key, value = match.group(1).lower(), match.group(2).strip()
            if key == "body":
                in_body = True
                if value:
                    body_lines.append(value)
                continue
            fields[key] = canon.scrub(value)
        elif line.strip():
            # Unlabelled prose before any body: marker is still content.
            body_lines.append(line)

    # Uniform leading indentation from the template is cosmetic — dedent before
    # stripping, or the first line's indent is lost and the block looks ragged.
    body = textwrap.dedent("\n".join(body_lines)).strip()
    return fields, body


def _split_list(value: str) -> List[str]:
    if not value:
        return []
    value = value.strip().strip("[]")
    return [part.strip().strip("\"'") for part in re.split(r"[,\n]", value) if part.strip()]


def _parse_links(value: str) -> List[Link]:
    """Accept 'relation -> Target', 'Target', and '[[Target]]' in one field."""
    links: List[Link] = []
    for part in _split_list(value):
        if "->" in part:
            relation, _, target = part.partition("->")
            relation = re.sub(r"\s+", "_", relation.strip().lower()) or "relates_to"
            target = target.strip()
        else:
            relation, target = "relates_to", part
        target = re.sub(r"^\[\[|\]\]$", "", target).strip()
        if target:
            links.append(Link(to=target, relation=relation))
    return links


def node_from_block(
    block: str,
    *,
    parent_root: Optional[str] = None,
    source_chat: Optional[str] = None,
) -> Optional[Node]:
    """Build a :class:`Node` from one block. ``None`` when the block is empty."""
    fields, body = parse_block_fields(block)
    if not body and not fields.get("summary"):
        return None

    text_for_derivation = body or fields.get("summary", "")
    node_type = (fields.get("node_type") or "").split("|")[0].strip().lower()
    if node_type not in {"root", "idea", "task", "decision", "spec", "question", "relationship"}:
        node_type = classify(text_for_derivation)

    status = (fields.get("status") or "").split("|")[0].strip().lower()
    if status not in {"active", "planning", "archived", "superseded"}:
        status = "active"

    tags = _split_list(fields.get("tags", "")) or derive_tags(text_for_derivation, node_type)
    links = _parse_links(fields.get("links", "")) or derive_links(text_for_derivation)

    incoming_canon = fields.get("canon_id", "")
    return Node(
        # A far-side assistant may echo a real canon ID; if it invented one,
        # ignore it and let apply() mint a valid one.
        canon_id=incoming_canon if canon.is_valid(incoming_canon)
        else "PENDING.NODE.00000000.0000.Pending.001",
        node_id=fields.get("node_id") or derive_node_id(text_for_derivation),
        node_type=node_type,
        status=status,
        parent_root=canon.scrub(fields.get("parent_root") or parent_root or "") or None,
        tags=tags,
        links=links,
        summary=fields.get("summary") or summarise(text_for_derivation),
        body=body or fields.get("summary", ""),
        source_chat=fields.get("source_chat") or source_chat,
        source_turn_kind="assistant",
    )


def parse_bridge_paste(
    text: str,
    *,
    matcher: Optional[Matcher] = None,
    parent_root: Optional[str] = None,
    source_chat: Optional[str] = None,
) -> List[NodeOp]:
    """Bridge paste -> NodeOps, via the same reconciliation as a normal turn.

    Pure, like :func:`chat_organizer.parser.parse_message`: ``matcher`` injects
    existing-node candidates and nothing here touches SQLite.
    """
    blocks = extract_blocks(text)
    if not blocks:
        return [NodeOp("skip", reason="no bridge block found in paste")]

    ops: List[NodeOp] = []
    for block in blocks:
        node = node_from_block(block, parent_root=parent_root, source_chat=source_chat)
        if node is None:
            continue
        terms = keywords(f"{node.node_id} {node.summary} {node.body}")
        candidates = matcher(terms) if matcher and terms else []
        op = _reconcile(node, candidates)
        if canon.is_valid(node.canon_id) and op.kind == "create":
            # The far side quoted a canon ID we already trust: address it directly.
            op.reason += " (canon ID supplied by bridge block)"
        ops.append(op)

    return ops or [NodeOp("skip", reason="bridge blocks contained no content")]


def looks_like_bridge_paste(text: str) -> bool:
    return bool(extract_blocks(text))
