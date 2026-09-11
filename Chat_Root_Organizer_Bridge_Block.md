---
node_id: "chat_root_organizer_bridge_block"
node_type: "spec"
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
  - "[[Master_OS_Hub]]"
---

# [[Chat_Root_Organizer_Bridge_Block]]

owner:: [[Damien_Brock]]
implements:: "[[COS_Root_Organizer_Protocol]] Section 13.1"
code_ssot:: `chat_organizer/bridge.py`
status:: #status/active

**What it is:** the zero-infrastructure ingestion path. Dame pastes a prompt
into any chat, that chat's assistant replies with canon blocks, Dame pastes the
reply back into [[Chat_Root_Organizer_Service]]. No crawler, no host tools, no
backend change.

## 1. The Prompt (SSOT: `bridge.BRIDGE_PROMPT`)

The text Dame pastes out lives in code as `chat_organizer.bridge.BRIDGE_PROMPT`
and is **never retyped here** — the parser that reads the reply and the prompt
that requests it must never drift. Retrieve it with:

```python
from chat_organizer.bridge import BRIDGE_PROMPT
print(BRIDGE_PROMPT)
```

A test asserts the prompt carries the same two markers the parser matches on.

## 2. Block Grammar

marker_open:: `===COS-BRIDGE-V1===`
marker_close:: `===END-COS-BRIDGE===`

* Fields are `key: value` lines; unknown keys are treated as body text.
* Everything after a `body:` line is body, verbatim, dedented.
* Recognised fields are exactly the `graph` columns — see `bridge._KNOWN_FIELDS`.
* `links:` accepts `relation -> Target`, bare `Target`, and `[[Target]]`.
* `tags:` is comma-separated hierarchical tags (`domain/x`, `status/y`, `tech/z`).

## 3. Tolerances (deliberate)

The far side is an arbitrary assistant, so the parser forgives:

* **Surrounding chatter** — prose before and after the markers is discarded.
* **Multiple blocks** in one paste — each becomes its own node.
* **Missing fields** — anything absent is derived by the ordinary
  `parser.classify` / `derive_tags` / `derive_links` helpers.
* **YAML front-matter** instead of markers — accepted, because assistants reach
  for the house format by reflex.
* **Invented canon IDs** — a `canon_id` that fails [[Canon_ID_System]]
  validation is discarded and a real one is minted on write. This is the one
  tolerance that is a *rejection*: a hallucinated ID must never enter the graph.

## 4. Reconciliation

A bridge block is pre-structured text, not a special case. It runs the same
create-vs-update reconciliation as a native turn, including the mandatory
ambiguity escalation — pasting the same block twice updates one node, it does
not create a second.
