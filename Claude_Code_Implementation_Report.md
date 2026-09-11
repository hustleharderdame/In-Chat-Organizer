---
node_id: "cos_claude_code_implementation_report"
node_type: "report"
canon_id: "COS.REPORT.20260911.0400.ClaudeCodeImplementation.001"
version: "1.0.0"
status: "active"
single_source: true
tags:
  - "domain/software"
  - "status/active"
  - "tech/claude-code"
  - "tech/mcp"
parent_node: "[[Master_OS_Hub]]"
linked_nodes:
  - "[[Chat_Root_Organizer_Service]]"
  - "[[Chat_Root_Organizer_Bridge_Block]]"
  - "[[Chat_Root_Organizer_Android]]"
  - "[[COS_Root_Organizer_Protocol]]"
  - "[[DDB.OS]]"
  - "[[Canon_ID_System]]"
---

# [[Claude_Code_Implementation_Report]]

owner:: [[Damien_Brock]]
target_agent:: Claude Code
depends_on:: "[[COS_Root_Organizer_Protocol]] v2.0.0"
implemented_by:: "[[Chat_Root_Organizer_Service]] v1.0.0"
build_context:: Moto G / Termux proot Ubuntu, existing [[DDB.OS]] Flask+SQLite stack, FTS5 (no vector DB — 4GB RAM ceiling)

> **Node role.** This is the incoming build brief, kept verbatim below as the
> historical record. It is **not** the live spec — [[Chat_Root_Organizer_Service]]
> is, and the DDL in Section 2 below is superseded in place by
> `chat_organizer/db.py::SCHEMA`.

## 0. Delivery Ledger

status:: #status/active

| # | Build-order step | State |
|---|---|---|
| 1 | `graph` + `graph_fts` migration | **built** |
| 2 | `parse_message` / `apply` / `upsert_node` + fixtures | **built** |
| 3 | Bridge paste-back path | **built** |
| 4 | `detect_retrieval_trigger` / `extract_keywords` + unit tests | **built** |
| 5 | `search_past_chats` → host tools (path 1) | **built** |
| 6 | The two read endpoints | **built** |
| 7 | Standalone offline fallback (path 3) | **deferred — awaiting Dame** |
| + | Phone front-end (PWA + Android project) | **added** — see [[Chat_Root_Organizer_Android]] |

### Scope added after the brief

Dame asked for an Android APK. The brief's HTTP surface was read-only, which
would have made the phone app a viewer only, so `POST /ingest` and
`POST /ingest/answer` were added — refusing any non-loopback peer. The APK
itself could not be compiled in that session (no network route to
`dl.google.com` for the Android SDK), so the repo carries a complete, validated
Gradle project plus an installable PWA that works today.
Building it also surfaced a latent bug the test client could never catch: the
shared SQLite connection was not usable from a WSGI worker thread. See
[[Chat_Root_Organizer_Android]] Section 5.

### Drift notes against this brief

* **Table naming.** Section 3 says `nodes_fts` and Section 5 says
  `nodes`/`tags`/`links`; Section 2 locks a single `graph` table with JSON
  columns. Section 2 was taken as the SSOT — the implementation has exactly
  `graph` + `graph_fts` and no join tables.
* **Scoring.** Raw `bm25()` magnitudes on an external-content FTS5 table are
  far too small to threshold on directly. FTS5 still does the cheap narrowing
  (the 4GB-RAM constraint holds), then hits are re-scored by term coverage so
  the 0.75 update threshold and the ambiguity delta mean the same thing on a
  10-row and a 10,000-row graph.
* **Protocol Section 13.1** was not available to this build, so the bridge block
  grammar was defined here and is now the SSOT:
  [[Chat_Root_Organizer_Bridge_Block]]. Reconcile it against the protocol text
  if the two differ — the parser is deliberately tolerant either way.

---

## 1. What To Build

A **Chat Root Organizer service** that sits on top of the existing DDB.OS database and turns raw conversation turns into the node/tag/link graph defined in `[[COS_Root_Organizer_Protocol]]`. This is not a new system — it's a new table set and a parsing layer inside the DDB.OS Flask app already running at `127.0.0.1:8410`.

## 2. Data Model — One Master Table

Single table, added to the existing SQLite DB (alongside Council, Memories, Skills, Dossier). Tags and links live as JSON columns on the same row instead of separate join tables — one row per node is the whole node:

```sql
CREATE TABLE graph (
  canon_id      TEXT PRIMARY KEY,   -- DOMAIN.TYPE.YYYYMMDD.HHMM.OBJECT.SEQ
  node_id       TEXT NOT NULL,      -- human slug
  node_type     TEXT NOT NULL,      -- root|idea|task|decision|spec|question|relationship
  parent_root   TEXT,               -- canon_id of the node_type='root' row it belongs to
  status        TEXT NOT NULL,      -- active|planning|archived|superseded
  tags          TEXT,               -- JSON array: ["domain/software","status/active"]
  links         TEXT,               -- JSON array: [{"to":"CANON_ID","relation":"supports"}]
  summary       TEXT,
  body          TEXT,               -- full node content
  source_chat   TEXT,               -- chat url/id/title if retrieved or bridged in, else NULL
  source_turn_kind TEXT,            -- 'human'|'assistant'|NULL
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

CREATE VIRTUAL TABLE graph_fts USING fts5(
  canon_id, body, tags, content='graph', content_rowid='rowid'
);
```

**Auto-build on ingestion**: there's no separate migration step per new chat. Every ingestion path (native parsing, retrieval, or a pasted bridge block — Section 4) ends in the same single `upsert_node(row)` call, which writes/updates one row in `graph` and refreshes `graph_fts`. The table grows by upsert as chats come in; nothing else has to run.

This mirrors the two-layer identity model already locked for DDB.OS (`uuid` for plumbing is skipped here since `canon_id` is already unique and stable — reuse the existing `ddb_index.py` enforcement script unmodified).

## 3. Parsing Layer (Sections 2, 8, 9 of the protocol)

A single function, called on every incoming message:

```
parse_message(text) -> list[NodeOp]
```

- Classify: filler vs. durable (idea/task/decision/spec/question/relationship).
- If durable: match against existing nodes (FTS5 query on `nodes_fts`) to decide create-vs-update.
- Emit a `NodeOp` (create/update/link/tag) rather than writing directly — keep this pure and testable.
- A separate `apply(NodeOp)` function does the actual SQLite write, assigns `canon_id` via `ddb_index.py`, and stamps `created_at`/`updated_at`.

Reuse the existing zero-width-space regex fix from `ddb_index.py` — don't re-derive canon ID validation from scratch.

## 4. Retrieval Layer (Sections 6–7 of the protocol)

This is the genuinely new piece — it does not exist in DDB.OS today.

```
detect_retrieval_trigger(text) -> bool
extract_keywords(text) -> list[str]        # 2-6 words, strip meta-words
search_past_chats(keywords) -> list[ChatHit]
```

Three integration paths feed the same `upsert_node(row)` call from Section 2 — retrieval doesn't get its own table, it's just another writer:

1. **In-session (Claude/Claude Code host tools)** — when this organizer is running as a skill/plugin inside Claude.ai or Claude Code, `search_past_chats` should call the host's own `conversation_search` / `recent_chats` / `read_conversation` primitives directly. Do not re-crawl or re-index chat history that the host already indexes — that's wasted RAM on a 4GB device.
2. **Bridge paste-back (manual, zero new infra)** — the protocol's copy/paste block (Section 13.1) is the cheapest possible ingestion path: Dame pastes it into any chat, that chat's assistant returns one filled-in canon block, Dame pastes the reply back here. Parse that block with the same `parse_message`/`apply` functions from Section 3 — it's just a pre-structured message, no new parser needed. Build this path first; it works today with zero backend changes.
3. **Standalone (local DDB.OS DB only)** — if run outside a Claude host with chat-history access, fall back to FTS5 search over any chat transcripts Dame has explicitly exported into DDB.OS. Lowest priority — build only if Dame wants the organizer usable fully offline.

**Ambiguity resolution is mandatory, not optional**: if `search_past_chats` returns more than one plausible hit, the service must surface the candidates back to the parsing layer as a question, never auto-pick the top-ranked result. This is a hard behavioral constraint from the protocol (Section 6, Step 4) — a bug that silently resolves ambiguity is a bug, not a convenience feature.

## 5. Views / Query Layer (Section 5)

Expose two read endpoints on the existing Flask app:

- `GET /nodes?tag=status/active` — table view, sortable by `updated_at` — this is the Dataview-table equivalent.
- `GET /nodes/tasks?open=true&group_by=parent_root` — the Dataview-task-group equivalent.

No new query language needed — plain SQL against `nodes`/`tags`/`links` covers both Dataview examples in the protocol.

## 6. Build Order

1. Add the single `graph` table + `graph_fts` virtual table to the existing DDB.OS SQLite DB (one small migration, no new infra).
2. Implement `parse_message` / `apply` / `upsert_node` against a handful of real past chat exports as test fixtures — validate node creation/update/tagging matches Section 9's reconciliation rules.
3. Wire the **bridge paste-back path** (Section 4, path 2) — reuses `parse_message` on the pasted canon block, zero new infra, usable immediately.
4. Implement `detect_retrieval_trigger` / `extract_keywords` as pure functions with unit tests against the phrase examples in Section 7 of the protocol (possessives, definite articles, past tense, direct asks).
5. Wire `search_past_chats` to the in-session host tools path (path 1).
6. Add the two read endpoints (Section 5).
7. Only then: standalone offline fallback (path 3), if still wanted.

## 7. Open Questions For Dame

- Standalone fallback (Section 4, path 3) — build now or defer until there's an actual need to run this outside a Claude host?
- `links` and `tags` as JSON columns on `graph` means relationship queries (`find everything that supports X`) are done with SQLite's `json_each()` rather than a plain join — fine at Dame's data volume, but flag if you want a real join table back once the graph gets big enough that JSON scanning gets slow.

**END REPORT**
