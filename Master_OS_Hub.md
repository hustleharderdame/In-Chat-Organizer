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
  - "[[Chat_Root_Organizer_Android]]"
  - "[[Claude_Code_Implementation_Report]]"
  - "[[SSA_RECON]]"
  - "[[SSA_RECON_App_UI]]"
  - "[[COS_Root_Organizer_Protocol]]"
  - "[[DDB.OS]]"
---

# [[Master_OS_Hub]]

owner:: [[Damien_Brock]]
repo:: In-Chat-Organizer

## 1. Active Graph Registry

* **Service (this repo):** [[Chat_Root_Organizer_Service]] | #domain/software
* **Bridge format:** [[Chat_Root_Organizer_Bridge_Block]] | #domain/software
* **Phone front-end:** [[Chat_Root_Organizer_Android]] | #domain/software #tech/pwa
* **Build brief:** [[Claude_Code_Implementation_Report]] | #domain/software
* **SSA rep-payee reconciliation:** [[SSA_RECON]] | #domain/financial-administration `domain:financial-administration`
* **SSA mobile surface:** [[SSA_RECON_App_UI]] | `domain:financial-administration` `tech:mobile-ui`
* **Upstream protocol:** [[COS_Root_Organizer_Protocol]] *(external node — not in this repo)*
* **Host stack:** [[DDB.OS]] *(external node — Flask + SQLite at 127.0.0.1:8410)*

## 2. Dynamic Database Views (Obsidian Dataview)

```dataview
TABLE version AS "Version", status AS "Status", tags AS "Tags"
FROM ""
WHERE (contains(tags, "status/active") OR contains(tags, "status:active"))
  AND file.name != "Master_OS_Hub"
SORT file.mtime DESC
```

Two tag namespaces are matched on purpose. Slash-namespaced tags
(`status/active`) are what every node in this repo carries; colon-namespaced
tags (`status:active`) are the canon [[SSA_RECON]] v4.0.0 adopted from
[[BFR_v3.0.0]]. Until the older nodes are converted, dropping either arm of
this filter makes half the graph invisible to the view.

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
