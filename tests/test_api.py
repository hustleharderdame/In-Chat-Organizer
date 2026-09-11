"""Views / query layer — the two read endpoints (protocol Section 5)."""

import pytest

flask = pytest.importorskip("flask")

from chat_organizer import db  # noqa: E402
from chat_organizer.api import attach  # noqa: E402


@pytest.fixture()
def client(organizer):
    root = organizer.ingest("Starting a new project for driver onboarding.").written[0]
    organizer.ingest("TODO: design the driver signup form.", parent_root=root.canon_id)
    organizer.ingest("TODO: write the background check step.", parent_root=root.canon_id)
    organizer.ingest("We decided the graph table is the single master table.")
    organizer.ingest("Should we defer the standalone offline fallback?")
    app = attach(flask.Flask(__name__), organizer)
    app.config.update(TESTING=True)
    return app.test_client(), organizer


def test_nodes_table_view(client):
    http, _ = client
    payload = http.get("/nodes").get_json()
    assert payload["count"] == 5
    assert {n["node_type"] for n in payload["nodes"]} >= {"root", "task", "decision"}


def test_nodes_filtered_by_tag(client):
    http, _ = client
    payload = http.get("/nodes?tag=status/active").get_json()
    assert payload["count"] >= 1
    assert all("status/active" in n["tags"] for n in payload["nodes"])


def test_nodes_filtered_by_type_and_status(client):
    http, _ = client
    payload = http.get("/nodes?type=task&status=active").get_json()
    assert {n["node_type"] for n in payload["nodes"]} == {"task"}


def test_nodes_sorted_by_updated_at_desc_by_default(client):
    http, _ = client
    stamps = [n["updated_at"] for n in http.get("/nodes").get_json()["nodes"]]
    assert stamps == sorted(stamps, reverse=True)


def test_nodes_ascending_sort(client):
    http, _ = client
    stamps = [n["updated_at"] for n in http.get("/nodes?asc=true").get_json()["nodes"]]
    assert stamps == sorted(stamps)


def test_nodes_pagination(client):
    http, _ = client
    page = http.get("/nodes?limit=2&offset=0").get_json()
    assert page["count"] == 2
    assert http.get("/nodes?limit=2&offset=4").get_json()["count"] == 1


def test_nodes_rejects_non_integer_paging(client):
    http, _ = client
    assert http.get("/nodes?limit=banana").status_code == 400


def test_tags_and_links_come_back_as_lists_not_json_strings(client):
    http, _ = client
    node = http.get("/nodes").get_json()["nodes"][0]
    assert isinstance(node["tags"], list)
    assert isinstance(node["links"], list)


def test_open_tasks_grouped_by_parent_root(client):
    http, organizer = client
    payload = http.get("/nodes/tasks?open=true&group_by=parent_root").get_json()
    assert payload["group_by"] == "parent_root"
    assert payload["count"] == 2
    root_id = [n.canon_id for n in organizer.nodes(node_type="root")][0]
    assert len(payload["groups"][root_id]) == 2


def test_open_defaults_to_true(client):
    http, _ = client
    assert http.get("/nodes/tasks").get_json()["count"] == 2


def test_closed_tasks_appear_only_when_open_is_false(client):
    http, organizer = client
    task = organizer.nodes(node_type="task")[0]
    task.status = "archived"
    db.upsert_node(organizer.conn, task)
    assert http.get("/nodes/tasks?open=true").get_json()["count"] == 1
    assert http.get("/nodes/tasks?open=false").get_json()["count"] == 2


def test_tasks_group_by_status(client):
    http, _ = client
    payload = http.get("/nodes/tasks?group_by=status").get_json()
    assert set(payload["groups"]) == {"active"}


def test_tasks_rejects_an_unknown_grouping(client):
    http, _ = client
    assert http.get("/nodes/tasks?group_by=bogus").status_code == 400


def test_blueprint_honours_a_url_prefix(organizer):
    app = attach(flask.Flask(__name__), organizer, url_prefix="/organizer")
    http = app.test_client()
    assert http.get("/organizer/nodes").status_code == 200
    assert http.get("/nodes").status_code == 404


# --- write side: POST /ingest (loopback only) -------------------------------
def test_ingest_files_a_native_turn(client):
    http, organizer = client
    r = http.post("/ingest", json={"text": "We're going with flat per-trip pricing."})
    assert r.status_code == 201
    payload = r.get_json()
    assert payload["path"] == "native"
    assert payload["written"][0]["node_type"] == "decision"
    assert organizer.nodes(node_type="decision")


def test_ingest_files_a_bridge_paste(client):
    http, _ = client
    paste = (
        "===COS-BRIDGE-V1===\nnode_id: driver_bonus\nnode_type: decision\n"
        "body:\n  Driver bonus is $5 per completed trip.\n===END-COS-BRIDGE==="
    )
    payload = http.post("/ingest", json={"text": paste}).get_json()
    assert payload["path"] == "bridge"
    assert payload["written"][0]["node_id"] == "driver_bonus"


def test_ingest_records_the_source_chat(client):
    http, _ = client
    payload = http.post("/ingest", json={
        "text": "We decided to retire hourly billing entirely.",
        "source_chat": "phone",
    }).get_json()
    assert payload["written"][0]["source_chat"] == "phone"


def test_ingest_of_filler_writes_nothing_but_still_succeeds(client):
    http, _ = client
    r = http.post("/ingest", json={"text": "ok thanks"})
    assert r.status_code == 200
    assert r.get_json()["written"] == []


def test_ingest_rejects_a_missing_or_empty_text(client):
    http, _ = client
    assert http.post("/ingest", json={}).status_code == 400
    assert http.post("/ingest", json={"text": "   "}).status_code == 400
    assert http.post("/ingest", json={"text": 12}).status_code == 400


def test_ingest_rejects_a_non_object_body(client):
    http, _ = client
    assert http.post("/ingest", json=["not", "an", "object"]).status_code == 400
    assert http.post("/ingest", data="raw", content_type="text/plain").status_code == 400


def test_writes_are_refused_from_a_non_loopback_peer(client):
    http, organizer = client
    before = len(organizer.nodes(limit=500))
    r = http.post("/ingest", json={"text": "We decided something important."},
                  environ_overrides={"REMOTE_ADDR": "192.168.1.44"})
    assert r.status_code == 403
    assert len(organizer.nodes(limit=500)) == before


def test_reads_are_still_allowed_from_the_local_network(client):
    http, _ = client
    r = http.get("/nodes", environ_overrides={"REMOTE_ADDR": "192.168.1.44"})
    assert r.status_code == 200


@pytest.mark.parametrize("addr", ["127.0.0.1", "127.0.1.5", "::1", "::ffff:127.0.0.1"])
def test_loopback_forms_are_all_accepted(addr):
    from chat_organizer.api import is_loopback
    assert is_loopback(addr)


@pytest.mark.parametrize("addr", ["192.168.1.44", "10.0.0.2", "8.8.8.8", "", None, "garbage"])
def test_non_loopback_and_unparseable_peers_are_refused(addr):
    from chat_organizer.api import is_loopback
    assert not is_loopback(addr)


# --- POST /ingest/answer -----------------------------------------------------
def test_answering_an_ambiguity_from_the_phone(conn, fake_provider):
    from chat_organizer.retrieval import ChatHit
    from chat_organizer.service import Organizer

    provider = fake_provider([
        ChatHit(chat_id="chat-1", title="pricing v1", score=0.9),
        ChatHit(chat_id="chat-2", title="pricing v2", score=0.9),
    ])
    org = Organizer(conn=conn, provider=provider)
    app = attach(flask.Flask(__name__), org)
    http = app.test_client()

    payload = http.post("/ingest", json={"text": "remember when we talked about pricing?"}).get_json()
    assert payload["needs_answer"]
    chosen = payload["questions"][0]["candidates"][1]

    r = http.post("/ingest/answer", json={"chosen": chosen})
    assert r.status_code == 201
    assert r.get_json()["node"]["source_chat"] == "chat-2"


def test_answer_rejects_a_candidate_with_no_identifier(client):
    http, _ = client
    assert http.post("/ingest/answer", json={"chosen": {}}).status_code == 400
    assert http.post("/ingest/answer", json={}).status_code == 400


def test_answer_404s_on_an_unknown_canon_id(client):
    http, _ = client
    r = http.post("/ingest/answer",
                  json={"chosen": {"canon_id": "COS.IDEA.20260911.0400.Missing.001"}})
    assert r.status_code == 404


def test_answer_is_loopback_only(client):
    http, _ = client
    r = http.post("/ingest/answer", json={"chosen": {"canon_id": "x"}},
                  environ_overrides={"REMOTE_ADDR": "8.8.8.8"})
    assert r.status_code == 403


# --- the PWA shell -----------------------------------------------------------
def test_app_shell_is_served_at_the_root(client):
    http, _ = client
    r = http.get("/")
    assert r.status_code == 200
    assert b"Chat Root Organizer" in r.data
    assert b"manifest.webmanifest" in r.data


def test_manifest_is_served_with_the_right_type(client):
    http, _ = client
    r = http.get("/manifest.webmanifest")
    assert r.status_code == 200
    assert "application/manifest+json" in r.headers["Content-Type"]
    manifest = r.get_json()
    assert manifest["display"] == "standalone"
    assert {i["sizes"] for i in manifest["icons"]} == {"192x192", "512x512"}
    assert any(i.get("purpose") == "maskable" for i in manifest["icons"])


def test_service_worker_is_served_from_the_scope_root(client):
    http, _ = client
    r = http.get("/sw.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["Content-Type"]
    # A cached service worker is how a PWA gets stuck on an old build.
    assert "no-cache" in r.headers.get("Cache-Control", "")


@pytest.mark.parametrize("name", ["icon-192.png", "icon-512.png", "icon-maskable-512.png"])
def test_icons_are_served_as_png(client, name):
    http, _ = client
    r = http.get(f"/icons/{name}")
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "image/png"
    assert r.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_every_manifest_icon_actually_resolves(client):
    http, _ = client
    for icon in http.get("/manifest.webmanifest").get_json()["icons"]:
        assert http.get("/" + icon["src"]).status_code == 200, icon["src"]


def test_icons_cannot_escape_the_icon_directory(client):
    http, _ = client
    assert http.get("/icons/../app.html").status_code in (301, 308, 404)


def test_healthz(client):
    http, _ = client
    assert http.get("/healthz").get_json()["ok"] is True
