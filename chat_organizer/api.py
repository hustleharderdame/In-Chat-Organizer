"""
---
node_id: "cos_api_module"
node_type: "code"
version: "1.0.0"
status: "active"
single_source: true
tags:
  - "domain/software"
  - "status/active"
  - "tech/flask"
parent_node: "[[Master_OS_Hub]]"
linked_nodes:
  - "[[Chat_Root_Organizer_Service]]"
  - "[[DDB.OS]]"
---

Views / query layer for [[Chat_Root_Organizer_Service]] — protocol Section 5.

Two read endpoints registered on the existing [[DDB.OS]] Flask app at
``127.0.0.1:8410``. No new query language: plain SQL over ``graph`` covers both
Dataview examples in the protocol.

    route:: GET /nodes?tag=status/active          -> Dataview TABLE equivalent
    route:: GET /nodes/tasks?open=true&group_by=parent_root -> Dataview TASK equivalent
    mount:: app.register_blueprint(build_blueprint(organizer))
    owner:: [[Damien_Brock]]
"""

from __future__ import annotations

from typing import Any, Optional

from flask import Blueprint, jsonify, request

from .service import Organizer


def _as_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def build_blueprint(organizer: Organizer, *, url_prefix: str = "") -> Blueprint:
    """Blueprint bound to one :class:`Organizer`. Read-only by design.

    Ingestion is a Python call (``organizer.ingest``) made by whatever is
    hosting the chat — the HTTP surface exists so Dame can *look* at the graph.
    """
    blueprint = Blueprint("chat_organizer", __name__, url_prefix=url_prefix)

    @blueprint.get("/nodes")
    def list_nodes() -> Any:
        """Table view, sortable by updated_at. Filters: tag, type, status, root."""
        args = request.args
        try:
            limit = int(args.get("limit", 200))
            offset = int(args.get("offset", 0))
        except ValueError:
            return jsonify({"error": "limit and offset must be integers"}), 400

        nodes = organizer.nodes(
            tag=args.get("tag"),
            node_type=args.get("type"),
            status=args.get("status"),
            parent_root=args.get("parent_root"),
            order_by=args.get("sort", "updated_at"),
            descending=not _as_bool(args.get("asc")),
            limit=limit,
            offset=offset,
        )
        return jsonify(
            {
                "count": len(nodes),
                "filters": {
                    k: v for k, v in args.items(multi=False) if k not in ("limit", "offset")
                },
                "nodes": [n.to_json() for n in nodes],
            }
        )

    @blueprint.get("/nodes/tasks")
    def list_tasks() -> Any:
        """Open tasks, grouped. ``open=false`` returns every task instead."""
        args = request.args
        group_by = args.get("group_by", "parent_root")
        if group_by not in ("parent_root", "status", "node_type", "source_chat"):
            return jsonify({"error": f"cannot group tasks by {group_by!r}"}), 400

        if _as_bool(args.get("open"), default=True):
            grouped = organizer.open_tasks(group_by=group_by)
        else:
            grouped = {}
            for task in organizer.nodes(node_type="task", limit=1000):
                key = str(getattr(task, group_by, None) or "ungrouped")
                grouped.setdefault(key, []).append(task)

        return jsonify(
            {
                "group_by": group_by,
                "count": sum(len(v) for v in grouped.values()),
                "groups": {
                    key: [n.to_json() for n in nodes] for key, nodes in grouped.items()
                },
            }
        )

    return blueprint


def attach(app: Any, organizer: Organizer, *, url_prefix: str = "") -> Any:
    """Register the organizer views on an existing Flask app."""
    app.register_blueprint(build_blueprint(organizer, url_prefix=url_prefix))
    return app
