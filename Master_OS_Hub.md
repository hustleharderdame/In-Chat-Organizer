---
node_id: "master_os_hub"
node_type: "system_hub"
version: "2.5.0"
status: "active"
single_source: true
tags:
  - "system/hub"
  - "status/active"
parent_node: "[[Master_OS_Hub]]"
linked_nodes:
  - "[[Chat_Root_Organizer_Service]]"
  - "[[Chat_Root_Organizer_Bridge_Block]]"
  - "[[Claude_Code_Implementation_Report]]"
  - "[[COS_Root_Organizer_Protocol]]"
  - "[[DDB.OS]]"
---

# [[Master_OS_Hub]]

owner:: [[Damien_Brock]]
repo:: In-Chat-Organizer

## 1. Active Graph Registry

* **Service (this repo):** [[Chat_Root_Organizer_Service]] | #domain/software
* **Bridge format:** [[Chat_Root_Organizer_Bridge_Block]] | #domain/software
* **Build brief:** [[Claude_Code_Implementation_Report]] | #domain/software
* **Upstream protocol:** [[COS_Root_Organizer_Protocol]] *(external node — not in this repo)*
* **Host stack:** [[DDB.OS]] *(external node — Flask + SQLite at 127.0.0.1:8410)*

## 2. Dynamic Database Views (Obsidian Dataview)

```dataview
TABLE version AS "Version", status AS "Status", tags AS "Tags"
FROM ""
WHERE contains(tags, "status/active") AND file.name != "Master_OS_Hub"
SORT file.mtime DESC
```

## 3. Global Active Backlog Index

```dataview
TASK
FROM ""
WHERE !completed
GROUP BY file.link
```

## 4. Live Graph Views (runtime equivalents)

The same two views, served off the ``graph`` table instead of the vault, are
defined once in [[Chat_Root_Organizer_Service]] Section 5. They are not restated
here — the routes are the single source.
