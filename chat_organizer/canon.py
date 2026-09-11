"""
---
node_id: "cos_canon_module"
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
  - "[[Canon_ID_System]]"
---

Canon ID enforcement for [[Chat_Root_Organizer_Service]].

SSOT for the canon ID grammar is [[Canon_ID_System]] as implemented by the
existing DDB.OS ``ddb_index.py``. This module NEVER re-derives that grammar: if
``ddb_index`` is importable it is used unmodified and this module is a thin
adapter over it. The bundled fallback below only runs when the organizer is
executed outside the DDB.OS tree (tests, standalone import).

    grammar:: DOMAIN.TYPE.YYYYMMDD.HHMM.OBJECT.SEQ
    example:: COS.REPORT.20260911.0400.ClaudeCodeImplementation.001
    owner:: [[Damien_Brock]]
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

# --- Invisible-character fix -------------------------------------------------
# Reused verbatim from ddb_index.py: chat clients paste canon IDs carrying
# zero-width spaces / joiners / BOMs, which silently break primary-key equality.
_INVISIBLE_RE = re.compile(
    "["
    "​"  # zero width space
    "‌"  # zero width non-joiner
    "‍"  # zero width joiner
    "⁠"  # word joiner
    "﻿"  # BOM / zero width no-break space
    "­"  # soft hyphen
    "]"
)

_CANON_RE = re.compile(
    r"^(?P<domain>[A-Z][A-Z0-9]{1,15})"
    r"\.(?P<type>[A-Z][A-Z0-9]{1,23})"
    r"\.(?P<date>\d{8})"
    r"\.(?P<time>\d{4})"
    r"\.(?P<object>[A-Za-z0-9][A-Za-z0-9_-]{0,63})"
    r"\.(?P<seq>\d{3,4})$"
)

DEFAULT_DOMAIN = "COS"


class CanonIdError(ValueError):
    """Raised when a string is not a valid canon ID."""


def scrub(text: Optional[str]) -> str:
    """Strip invisible characters and surrounding whitespace.

    This is the zero-width-space fix from ``ddb_index.py``; every canon ID that
    crosses a chat boundary goes through here before it is compared or stored.
    """
    if text is None:
        return ""
    return _INVISIBLE_RE.sub("", text).strip()


def is_valid(canon_id: Optional[str]) -> bool:
    return _CANON_RE.match(scrub(canon_id)) is not None


def validate(canon_id: Optional[str]) -> str:
    """Return the scrubbed canon ID, or raise :class:`CanonIdError`."""
    cleaned = scrub(canon_id)
    if not _CANON_RE.match(cleaned):
        raise CanonIdError(f"not a canon ID: {canon_id!r}")
    return cleaned


def parts(canon_id: str) -> dict:
    """Break a canon ID into its six components."""
    match = _CANON_RE.match(validate(canon_id))
    assert match is not None  # validate() already guaranteed this
    return match.groupdict()


def slug_to_object(slug: str) -> str:
    """Turn a human slug ('bridge paste-back path') into an OBJECT segment."""
    cleaned = scrub(slug)
    words = re.findall(r"[A-Za-z0-9]+", cleaned)
    if not words:
        return "Node"
    camel = "".join(w[:1].upper() + w[1:] for w in words)
    return camel[:64]


def mint(
    node_type: str,
    object_slug: str,
    *,
    domain: str = DEFAULT_DOMAIN,
    when: Optional[datetime] = None,
    seq: int = 1,
) -> str:
    """Mint a canon ID. Uniqueness against the store is the caller's job.

    ``seq`` is bumped by :func:`chat_organizer.db.next_free_canon_id` until the
    resulting ID is free, so this function stays pure.
    """
    moment = when or datetime.now(timezone.utc)
    return ".".join(
        (
            scrub(domain).upper(),
            re.sub(r"[^A-Z0-9]", "", scrub(node_type).upper()) or "NODE",
            moment.strftime("%Y%m%d"),
            moment.strftime("%H%M"),
            slug_to_object(object_slug),
            f"{seq:03d}",
        )
    )


# --- Prefer the real DDB.OS enforcement script when it is importable ---------
try:  # pragma: no cover - exercised only inside the DDB.OS tree
    import ddb_index as _ddb_index  # type: ignore

    if hasattr(_ddb_index, "scrub"):
        scrub = _ddb_index.scrub  # type: ignore[assignment]  # noqa: F811
    if hasattr(_ddb_index, "validate_canon_id"):
        validate = _ddb_index.validate_canon_id  # type: ignore[assignment]  # noqa: F811
    USING_DDB_INDEX = True
except ImportError:
    USING_DDB_INDEX = False
