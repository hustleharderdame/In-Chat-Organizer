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
  - "[[Chat_Root_Organizer_Android]]"
  - "[[DDB.OS]]"
---

Views / query layer for [[Chat_Root_Organizer_Service]] — protocol Section 5.

Two read endpoints registered on the existing [[DDB.OS]] Flask app at
``127.0.0.1:8410``. No new query language: plain SQL over ``graph`` covers both
Dataview examples in the protocol.

    route:: GET  /nodes?tag=status/active          -> Dataview TABLE equivalent
    route:: GET  /nodes/tasks?open=true&group_by=parent_root -> Dataview TASK equivalent
    route:: POST /ingest                          -> capture from the phone
    route:: POST /ingest/answer                   -> resolve an ambiguity question
    route:: GET  / , /manifest.webmanifest , /sw.js , /icons/<f> -> the PWA shell
    mount:: app.register_blueprint(build_blueprint(organizer))
    owner:: [[Damien_Brock]]

**Write endpoints are loopback-only.** The graph is Dame's whole working memory;
the server is meant to be reachable only from the device it runs on. Reads are
left open so a desktop on the same tailnet can look, but anything that mutates
the graph refuses a non-loopback peer. See [[Chat_Root_Organizer_Android]].
"""

from __future__ import annotations

import ipaddress
import mimetypes
import pathlib
from typing import Any, Optional, Tuple

from flask import Blueprint, jsonify, request, send_from_directory

from .service import Organizer

WEB_ROOT = pathlib.Path(__file__).parent / "web"

#: Peers allowed to mutate the graph. The Flask app is meant to be bound to
#: 127.0.0.1 anyway; this is the belt to that braces.
LOOPBACK_NETS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
)


def _as_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def is_loopback(remote_addr: Optional[str]) -> bool:
    """True when the peer is on this device. Unknown peers are not trusted."""
    if not remote_addr:
        return False
    try:
        address = ipaddress.ip_address(remote_addr)
    except ValueError:
        return False
    if address.version == 6 and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return any(address in net for net in LOOPBACK_NETS)


def _json_body() -> Tuple[Optional[dict], Optional[Any]]:
    """Parse a JSON body, returning (payload, error_response)."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None, (jsonify({"error": "expected a JSON object body"}), 400)
    return payload, None


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

    # --- write side: capture from the phone -----------------------------
    @blueprint.post("/ingest")
    def ingest() -> Any:
        """Capture a turn or a pasted bridge block.

        The organizer routes it exactly as it would in-chat: a bridge paste goes
        down the bridge path, anything else is parsed as a native turn. An
        ambiguous match comes back as ``questions`` with ``needs_answer`` true
        and nothing written for that op — the caller must choose.
        """
        if not is_loopback(request.remote_addr):
            return jsonify({"error": "writes are loopback-only"}), 403

        payload, error = _json_body()
        if error:
            return error

        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return jsonify({"error": "'text' must be a non-empty string"}), 400

        result = organizer.ingest(
            text,
            parent_root=payload.get("parent_root"),
            source_chat=payload.get("source_chat"),
            source_turn_kind=payload.get("source_turn_kind", "human"),
        )
        return jsonify(result.to_json()), 201 if result.written else 200

    @blueprint.post("/ingest/answer")
    def answer() -> Any:
        """Resolve an ambiguity question by naming the candidate Dame picked.

        Takes one candidate object straight from a question op's ``candidates``
        list — either shape (``canon_id`` or ``chat_id``) is accepted.
        """
        if not is_loopback(request.remote_addr):
            return jsonify({"error": "writes are loopback-only"}), 403

        payload, error = _json_body()
        if error:
            return error

        chosen = payload.get("chosen")
        if not isinstance(chosen, dict) or not (chosen.get("canon_id") or chosen.get("chat_id")):
            return jsonify({"error": "'chosen' must carry a canon_id or a chat_id"}), 400

        try:
            node = organizer.answer_ambiguity(chosen, parent_root=payload.get("parent_root"))
        except KeyError as exc:
            return jsonify({"error": str(exc)}), 404
        return jsonify({"node": node.to_json()}), 201

    # --- the PWA shell ---------------------------------------------------
    @blueprint.get("/")
    def app_shell() -> Any:
        """The installable front-end. See [[Chat_Root_Organizer_Android]]."""
        return send_from_directory(WEB_ROOT, "app.html")

    @blueprint.get("/manifest.webmanifest")
    def manifest() -> Any:
        return send_from_directory(
            WEB_ROOT, "manifest.webmanifest", mimetype="application/manifest+json"
        )

    @blueprint.get("/sw.js")
    def service_worker() -> Any:
        """Served from the scope root so the worker can control the whole app."""
        response = send_from_directory(WEB_ROOT, "sw.js", mimetype="text/javascript")
        # A cached service worker is how a PWA gets stuck on an old build.
        response.headers["Cache-Control"] = "no-cache"
        return response

    @blueprint.get("/icons/<path:filename>")
    def icons(filename: str) -> Any:
        mimetype, _ = mimetypes.guess_type(filename)
        return send_from_directory(WEB_ROOT / "icons", filename, mimetype=mimetype)

    @blueprint.get("/healthz")
    def healthz() -> Any:
        """The app shell polls this to tell 'server down' from 'empty graph'."""
        return jsonify({"ok": True, "service": "chat-organizer"})

    return blueprint


def attach(app: Any, organizer: Organizer, *, url_prefix: str = "") -> Any:
    """Register the organizer views on an existing Flask app."""
    app.register_blueprint(build_blueprint(organizer, url_prefix=url_prefix))
    return app
