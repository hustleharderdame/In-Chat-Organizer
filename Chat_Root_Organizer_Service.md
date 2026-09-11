---
node_id: "chat_root_organizer_service"
node_type: "spec"
version: "1.0.0"
status: "active"
single_source: true
tags:
  - "domain/software"
  - "status/active"
  - "tech/python"
  - "tech/sqlite"
  - "tech/flask"
parent_node: "[[Master_OS_Hub]]"
linked_nodes:
  - "[[Master_OS_Hub]]"
  - "[[Claude_Code_Implementation_Report]]"
  - "[[Chat_Root_Organizer_Bridge_Block]]"
  - "[[Chat_Root_Organizer_Android]]"
  - "[[COS_Root_Organizer_Protocol]]"
  - "[[DDB.OS]]"
  - "[[Canon_ID_System]]"
---

# [[Chat_Root_Organizer_Service]]

owner:: [[Damien_Brock]]
implements:: "[[Claude_Code_Implementation_Report]] v1.0.0"
depends_on:: "[[COS_Root_Organizer_Protocol]] v2.0.0"
host:: "[[DDB.OS]] — Flask + SQLite, 127.0.0.1:8410"
build_context:: Moto G / Termux proot Ubuntu · 4GB RAM ceiling · FTS5, no vector DB
status:: #status/active

**What it is:** a parsing layer and one table set inside the existing [[DDB.OS]]
Flask app that turns raw conversation turns into the node/tag/link graph defined
by [[COS_Root_Organizer_Protocol]]. Not a new system, not a new process.

## 1. Module Map

| Module | Role | Touches SQLite |
|---|---|---|
| `chat_organizer/canon.py` | [[Canon_ID_System]] grammar adapter | no |
| `chat_organizer/nodes.py` | `Node`, `Link`, `NodeOp` value types | no |
| `chat_organizer/db.py` | `graph` + `graph_fts`, `upsert_node`, FTS search | **yes — only writer** |
| `chat_organizer/parser.py` | `parse_message` (pure) · `apply` (writes) | apply only |
| `chat_organizer/bridge.py` | [[Chat_Root_Organizer_Bridge_Block]] paste-back | no |
| `chat_organizer/retrieval.py` | triggers, keywords, providers, ambiguity | via `upsert_node` |
| `chat_organizer/service.py` | `Organizer` — routes a turn, owns the connection | via `upsert_node` |
| `chat_organizer/api.py` | HTTP surface + the PWA shell | reads + guarded writes |
| `chat_organizer/web/` | the installable front-end — [[Chat_Root_Organizer_Android]] | no |

## 2. Data Model

schema_ssot:: `chat_organizer/db.py::SCHEMA`

The DDL is **defined once, in code**, and is deliberately not restated in this
node — a schema that lives in two places drifts. What this node fixes is the
*contract around it*:

* **One master table.** `graph`, one row per node. Tags and links are JSON
  columns on that row, not join tables.
* **One writer.** Every ingestion path — native parsing, bridge paste-back,
  retrieval — ends in `db.upsert_node(conn, node)`. Nothing else writes `graph`.
* **Auto-build on ingestion.** `db.migrate` is idempotent and runs on connect.
  The table grows by upsert as chats arrive; there is no per-chat migration.
* **FTS never drifts.** `graph_fts` is kept in lockstep by SQLite triggers, not
  by writer discipline, so a future writer cannot forget to refresh it.
* **Canon IDs are minted, never invented.** `db.next_free_canon_id` bumps SEQ
  until the ID is unused. `canon.py` defers to DDB.OS's `ddb_index.py` whenever
  that module is importable, including its zero-width-space scrub.

## 3. Parsing Layer

`parse_message(text) -> list[NodeOp]` is **pure** — no SQLite, no clock. Existing
node lookup is injected as a `matcher` callable, so classification and
reconciliation are unit-testable with no database.

flow:: turn → filler check → split into units → classify → derive tags/links/summary → reconcile → `NodeOp`

`apply(conn, op)` is the only function that writes, and it writes solely through
`upsert_node`. Ops of kind `question` and `skip` write nothing, by design.

### Reconciliation (protocol Section 9)

* Best candidate scores **≥ 0.75** → `update` (body appended, tags and links
  unioned, `created_at` preserved).
* A runner-up within **0.15** of the winner → `question`. **Never auto-pick.**
* Nothing clears the bar → `create`.

## 4. Retrieval Layer

Three provider paths, one write path. Retrieval owns **no table of its own**.

| Path | Status | Notes |
|---|---|---|
| 2 · Bridge paste-back | **built** | see [[Chat_Root_Organizer_Bridge_Block]] |
| 1 · Host tools | **built** | `HostToolProvider` wraps `conversation_search` / `recent_chats` / `read_conversation` |
| 3 · Standalone local FTS5 | **deferred** | open question — implement `ChatSearchProvider` and pass it to `Organizer` |

Path 1 delegates to the host's own chat-history primitives and never re-crawls
or re-indexes history the host already indexes — that would be wasted RAM on a
4GB device. The primitives are injected as plain callables, so the provider is
testable outside a Claude host.

### Ambiguity is a hard constraint

protocol_ref:: "[[COS_Root_Organizer_Protocol]] Section 6, Step 4"

More than one plausible hit **must** come back as a question. `resolve_hits`
returns a `question` op carrying every candidate; a version that silently
returns `hits[0]` is a bug, not a convenience. Tests pin this in both the
retrieval layer and the parser's reconciliation.

## 5. Views / Query Layer

route:: `GET /nodes?tag=status/active` → Dataview **TABLE** equivalent
route:: `GET /nodes/tasks?open=true&group_by=parent_root` → Dataview **TASK** equivalent
route:: `POST /ingest` · `POST /ingest/answer` → capture from the phone (loopback-only)
route:: `GET /` · `/manifest.webmanifest` · `/sw.js` · `/icons/…` → the PWA shell

Plain SQL over `graph` covers both Dataview examples — no new query language.

The report specified a read-only surface with ingestion as a Python call. The
write routes are a deliberate expansion so the phone front-end can capture;
they refuse any non-loopback peer. Details: [[Chat_Root_Organizer_Android]].

```python
from flask import Flask
from chat_organizer import Organizer
from chat_organizer.api import attach

organizer = Organizer("/path/to/ddbos.sqlite3")
attach(existing_ddbos_app, organizer)          # mounts both routes
```

## 6. Usage

```python
from chat_organizer import Organizer

org = Organizer("/path/to/ddbos.sqlite3")

result = org.ingest("We're going with flat per-trip pricing for Stay Driving.")
result.written        # [Node(...)] — what landed in graph
result.questions      # [NodeOp(kind='question')] — what needs Dame's answer
result.needs_answer   # bool

# Wire retrieval path 1 inside a Claude host:
from chat_organizer.retrieval import HostToolProvider
org.provider = HostToolProvider(conversation_search, recent_chats, read_conversation)

# Answer an ambiguity question:
org.answer_ambiguity(result.questions[0].candidates[1])
```

## 7. Front-end

The installable PWA and the Android WebView wrapper are specified in
[[Chat_Root_Organizer_Android]] and are not restated here.

```bash
python3 tools/serve_demo.py 8410     # seeded graph, no DDB.OS database needed
```

## 8. Tests

```bash
python3 -m pytest tests -q
```

Chat-export fixtures live in `tests/fixtures/`. They are **synthetic stand-ins**
shaped like real Claude exports — swap them for genuine DDB.OS exports before
trusting the reconciliation thresholds against Dame's real corpus.
