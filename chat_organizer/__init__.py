"""
---
node_id: "cos_package_root"
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
  - "[[Claude_Code_Implementation_Report]]"
  - "[[COS_Root_Organizer_Protocol]]"
---

[[Chat_Root_Organizer_Service]] — turns raw chat turns into the node/tag/link
graph defined by [[COS_Root_Organizer_Protocol]], on top of the [[DDB.OS]]
Flask + SQLite stack.

Flask is imported lazily (``chat_organizer.api``) so the parsing and retrieval
layers stay usable on a bare Termux Python with no web stack installed.

    owner:: [[Damien_Brock]]
"""

from . import bridge, canon, db, nodes, parser, retrieval
from .nodes import Link, Node, NodeOp
from .service import IngestResult, Organizer

__version__ = "1.0.0"

__all__ = [
    "Organizer",
    "IngestResult",
    "Node",
    "NodeOp",
    "Link",
    "bridge",
    "canon",
    "db",
    "nodes",
    "parser",
    "retrieval",
    "__version__",
]
