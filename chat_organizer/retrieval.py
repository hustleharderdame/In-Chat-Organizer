"""
---
node_id: "cos_retrieval_module"
node_type: "code"
version: "1.0.0"
status: "active"
single_source: true
tags:
  - "domain/software"
  - "status/active"
  - "tech/claude-code"
parent_node: "[[Master_OS_Hub]]"
linked_nodes:
  - "[[Chat_Root_Organizer_Service]]"
  - "[[COS_Root_Organizer_Protocol]]"
---

Retrieval layer for [[Chat_Root_Organizer_Service]] — protocol Sections 6-7.

The genuinely new piece: notice that Dame is reaching for something from an
earlier chat, pull the keywords out, and go find it. Three provider paths feed
the SAME :func:`chat_organizer.db.upsert_node` call — retrieval owns no table.

    path_1:: host tools (conversation_search / recent_chats / read_conversation)
    path_2:: bridge paste-back -> see [[Chat_Root_Organizer_Bridge_Block]]
    path_3:: standalone local FTS5 -- DEFERRED, see open questions
    hard_constraint:: more than one plausible hit MUST become a question
    owner:: [[Damien_Brock]]
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence

from . import canon
from .nodes import Node, NodeOp

#: A hit must clear this to count as "plausible" at all.
PLAUSIBLE_FLOOR = 0.35
#: Runner-up within this distance of the winner => ambiguous => ask, never pick.
AMBIGUITY_DELTA = 0.2

# --- Section 7: trigger phrasings -------------------------------------------
# Four families, each drawn from the protocol's phrase examples.
_TRIGGER_FAMILIES: Dict[str, str] = {
    # past tense — "we talked about", "you said", "I mentioned"
    "past_tense": r"\b(?:we|you|i)\s+(?:\w+\s+){0,2}"
    r"(?:talked about|discussed|said|mentioned|covered|went over|worked out|"
    r"landed on|decided|figured out|wrote|built|set up|had)\b",
    # definite article — "the X we did", "that thing", "the one where"
    "definite_article": r"\b(?:that|the)\s+(?:\w+\s+){0,3}"
    r"(?:thing|one|note|doc|spec|plan|list|idea|version|approach|setup|format|"
    r"chat|convo|conversation|thread)\b",
    # possessive — "my X", "our X", "Dame's X"
    "possessive": r"\b(?:my|our|your|[A-Z][a-z]+'s)\s+"
    r"(?:\w+\s+){0,3}(?:spec|plan|notes?|list|setup|format|doc|file|system|"
    r"process|rates?|prices?|template|script|config)\b",
    # direct ask — "find the chat where", "pull up", "search our chats"
    "direct_ask": r"\b(?:find|search|look up|pull up|dig up|check|remind me)\b"
    r"[^.?!]{0,40}\b(?:chats?|conversations?|convos?|threads?|earlier|before|"
    r"previous|last time|history|we|you|talked|said|discussed)\b",
    # explicit recall — "remember when", "what was that", "didn't we"
    "explicit_recall": r"\b(?:remember (?:when|that|what)|what was (?:that|the)|"
    r"didn'?t we|weren'?t we|have we (?:already|ever)|did we ever|"
    r"where did we|from (?:that|the) (?:other|last|earlier) (?:chat|conversation|thread))\b",
}
_TRIGGER_RES = {
    name: re.compile(pattern, re.IGNORECASE)
    for name, pattern in _TRIGGER_FAMILIES.items()
}

# Meta-words describe the *act of remembering*, never the subject. Stripped
# before keywords go to a provider, or every search matches every chat.
_META_WORDS = {
    "remember", "remembered", "recall", "chat", "chats", "conversation",
    "conversations", "convo", "convos", "thread", "threads", "talked", "talk",
    "talking", "discussed", "discuss", "discussing", "said", "say", "saying",
    "mentioned", "mention", "told", "tell", "asked", "ask", "earlier",
    "before", "previously", "previous", "last", "time", "back", "ago",
    "yesterday", "thing", "things", "stuff", "one", "ones", "find", "search",
    "look", "looking", "pull", "dig", "check", "want", "need", "know",
    "what", "when", "where", "which", "who", "why", "how", "was", "were",
    "did", "didnt", "didn", "doing", "again", "already", "ever", "that",
    "this", "the", "a", "an", "and", "or", "of", "to", "in", "on", "for",
    "with", "at", "by", "from", "about", "we", "you", "i", "our", "your",
    "my", "me", "us", "it", "its", "is", "are", "be", "been", "have", "has",
    "had", "do", "does", "up", "out", "over", "there", "here", "some", "any",
    "like", "just", "really", "actually", "maybe", "please", "can", "could",
    "would", "should", "will", "make", "made", "get", "got", "give", "gave",
}

MIN_KEYWORDS = 2
MAX_KEYWORDS = 6


def detect_retrieval_trigger(text: str) -> bool:
    """True when the turn is reaching for something from an earlier chat."""
    if not text or not text.strip():
        return False
    return any(rx.search(text) for rx in _TRIGGER_RES.values())


def trigger_families(text: str) -> List[str]:
    """Which Section 7 phrase families fired — useful for debugging misses."""
    return sorted(name for name, rx in _TRIGGER_RES.items() if rx.search(text))


def extract_keywords(text: str) -> List[str]:
    """The 2-6 subject words of a retrieval request, meta-words stripped.

    Proper nouns and quoted phrases are kept whole and ranked first: 'the Stay
    Driving rate card we worked out' should search for the rate card, not for
    the fact that a conversation happened.
    """
    cleaned = canon.scrub(text)
    ranked: List[str] = []

    # Quoted phrases are explicit subject markers — take them verbatim.
    for phrase in re.findall(r"[\"'“]([^\"'”]{3,40})[\"'”]", cleaned):
        token = phrase.strip().lower()
        if token and token not in ranked:
            ranked.append(token)

    # Multi-word proper nouns ("Stay Driving", "House Of Brock").
    for proper in re.findall(r"\b(?:[A-Z][a-zA-Z0-9]+(?:\s+(?:[A-Z][a-zA-Z0-9]+|of|Of))*)\b", cleaned):
        words = proper.split()
        if len(words) < 2:
            continue
        token = proper.strip().lower()
        if token not in _META_WORDS and token not in ranked:
            ranked.append(token)

    # Everything else, in order of appearance.
    for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]*", cleaned):
        lowered = word.lower()
        if lowered in _META_WORDS or len(lowered) < 3:
            continue
        if any(lowered in existing.split() for existing in ranked):
            continue
        if lowered not in ranked:
            ranked.append(lowered)

    return ranked[:MAX_KEYWORDS]


# --- providers ---------------------------------------------------------------
@dataclass
class ChatHit:
    """One candidate past conversation. ``score`` is 0..1, higher is better."""

    chat_id: str
    title: str = ""
    excerpt: str = ""
    score: float = 0.0
    url: Optional[str] = None
    provider: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> Dict[str, Any]:
        return {
            "chat_id": self.chat_id,
            "title": self.title,
            "excerpt": self.excerpt,
            "score": round(self.score, 3),
            "url": self.url,
            "provider": self.provider,
        }


class ChatSearchProvider(Protocol):
    """What every retrieval path must implement. Path 3 slots in here."""

    name: str

    def search(self, keywords: Sequence[str], *, limit: int = 10) -> List[ChatHit]:
        ...


class HostToolProvider:
    """Path 1 — delegate to the Claude host's own chat-history primitives.

    We never re-crawl or re-index chat history the host already indexes; that
    would be wasted RAM on a 4GB device. ``conversation_search`` and friends are
    injected as plain callables so this stays testable outside a Claude host.
    """

    name = "host"

    def __init__(
        self,
        conversation_search: Callable[..., Any],
        recent_chats: Optional[Callable[..., Any]] = None,
        read_conversation: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._conversation_search = conversation_search
        self._recent_chats = recent_chats
        self._read_conversation = read_conversation

    def search(self, keywords: Sequence[str], *, limit: int = 10) -> List[ChatHit]:
        if not keywords:
            return []
        raw = self._conversation_search(query=" ".join(keywords))
        return _normalise_host_results(raw, keywords, limit=limit, provider=self.name)

    def read(self, chat_id: str) -> str:
        """Full transcript for a confirmed hit, when the host exposes it."""
        if self._read_conversation is None:
            return ""
        result = self._read_conversation(uri=chat_id)
        if isinstance(result, str):
            return result
        return str(result)


def _normalise_host_results(
    raw: Any, keywords: Sequence[str], *, limit: int, provider: str
) -> List[ChatHit]:
    """Host tools return loosely-shaped payloads; coerce them into ChatHits."""
    items: List[Any]
    if isinstance(raw, dict):
        items = raw.get("results") or raw.get("conversations") or raw.get("data") or []
    elif isinstance(raw, list):
        items = raw
    else:
        items = []

    hits: List[ChatHit] = []
    for item in items[: max(1, limit)]:
        if not isinstance(item, dict):
            item = {"excerpt": str(item)}
        title = str(item.get("title") or item.get("name") or "")
        excerpt = str(
            item.get("excerpt") or item.get("snippet") or item.get("summary")
            or item.get("text") or ""
        )
        chat_id = str(
            item.get("uri") or item.get("id") or item.get("chat_id") or item.get("url") or title
        )
        hit = ChatHit(
            chat_id=chat_id,
            title=title,
            excerpt=excerpt,
            url=item.get("url"),
            provider=provider,
            meta={k: v for k, v in item.items() if k not in {"title", "excerpt", "uri"}},
        )
        supplied = item.get("score")
        hit.score = float(supplied) if isinstance(supplied, (int, float)) else score_hit(hit, keywords)
        hits.append(hit)
    hits.sort(key=lambda h: -h.score)
    return hits


def score_hit(hit: ChatHit, keywords: Sequence[str]) -> float:
    """Term coverage of a hit's title+excerpt — same scale as db.score_against."""
    wanted = {k.lower() for k in keywords if len(k) >= 3}
    if not wanted:
        return 0.0
    haystack = f"{hit.title} {hit.excerpt}".lower()
    return sum(1 for k in wanted if k in haystack) / len(wanted)


# --- the entrypoint ----------------------------------------------------------
def search_past_chats(
    keywords: Sequence[str],
    provider: Optional[ChatSearchProvider] = None,
    *,
    limit: int = 10,
) -> List[ChatHit]:
    """Run the configured provider. No provider configured -> no hits, no crash."""
    if provider is None or not keywords:
        return []
    hits = provider.search(list(keywords), limit=limit)
    hits.sort(key=lambda h: -h.score)
    return hits


def resolve_hits(hits: Sequence[ChatHit], query_text: str = "") -> NodeOp:
    """Turn provider hits into exactly one op — and never guess.

    Protocol Section 6, Step 4 is a hard behavioural constraint: more than one
    plausible hit MUST come back as a question. A version of this function that
    silently returns ``hits[0]`` is a bug, not a convenience.
    """
    # Sort defensively: resolve_hits must be correct on any list of hits, not
    # only on one search_past_chats happened to order.
    plausible = sorted(
        (h for h in hits if h.score >= PLAUSIBLE_FLOOR), key=lambda h: -h.score
    )
    if not plausible:
        return NodeOp("skip", reason="no past chat cleared the plausibility floor")

    best = plausible[0]
    rivals = [h for h in plausible[1:] if best.score - h.score <= AMBIGUITY_DELTA]
    if rivals:
        options = [best, *rivals]
        return NodeOp(
            "question",
            question=(
                f"{len(options)} past chats match that. Which one did you mean?"
                + (f" (looking for: {query_text.strip()})" if query_text.strip() else "")
            ),
            candidates=[h.to_json() for h in options],
            reason="ambiguous retrieval — refusing to auto-pick (protocol Section 6, Step 4)",
            confidence=best.score,
        )

    return NodeOp(
        "create",
        node=node_from_hit(best),
        reason=f"single plausible past chat: {best.chat_id}",
        confidence=best.score,
    )


def node_from_hit(hit: ChatHit, *, parent_root: Optional[str] = None) -> Node:
    """Build the graph row for a retrieved chat. Written via upsert_node like
    every other path — retrieval gets no table of its own."""
    slug = re.sub(r"[^a-z0-9]+", "_", (hit.title or hit.chat_id).lower()).strip("_")
    return Node(
        canon_id="PENDING.NODE.00000000.0000.Pending.001",
        node_id=(slug or "retrieved_chat")[:64],
        node_type="idea",
        status="active",
        parent_root=parent_root,
        tags=["type/idea", "status/active", "domain/software", "source/retrieved"],
        summary=hit.title or hit.excerpt[:180],
        body=hit.excerpt,
        source_chat=hit.url or hit.chat_id,
        source_turn_kind=None,
    )


def ingest_hit(
    conn: sqlite3.Connection, hit: ChatHit, *, parent_root: Optional[str] = None
) -> Node:
    """Land a confirmed hit in ``graph`` through the one shared write path."""
    from .parser import apply

    op = NodeOp("create", node=node_from_hit(hit, parent_root=parent_root))
    stored = apply(conn, op)
    assert stored is not None
    return stored
