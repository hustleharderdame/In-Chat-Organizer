---
node_id: "in_chat_organizer_readme"
node_type: "index"
version: "1.0.0"
status: "active"
single_source: false
tags:
  - "domain/software"
  - "status/active"
parent_node: "[[Master_OS_Hub]]"
linked_nodes:
  - "[[Master_OS_Hub]]"
  - "[[Chat_Root_Organizer_Service]]"
  - "[[Chat_Root_Organizer_Bridge_Block]]"
  - "[[Chat_Root_Organizer_Android]]"
  - "[[Claude_Code_Implementation_Report]]"
---

# In-Chat-Organizer

single_source:: false — this file is a **pointer**, not an authority. Every
statement of record lives in the node it links to.

**Start here:** [[Master_OS_Hub]]

| You want | Node |
|---|---|
| What the service is and how to mount it | [[Chat_Root_Organizer_Service]] |
| The paste-back block format | [[Chat_Root_Organizer_Bridge_Block]] |
| The phone app (PWA + APK project) | [[Chat_Root_Organizer_Android]] |
| The original build brief + delivery ledger | [[Claude_Code_Implementation_Report]] |

```bash
python3 -m pytest tests -q
```

```python
from chat_organizer import Organizer
org = Organizer("/path/to/ddbos.sqlite3")
org.ingest("We're going with flat per-trip pricing for Stay Driving.")
```

```bash
python3 tools/serve_demo.py 8410     # then open http://127.0.0.1:8410/
```
