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
