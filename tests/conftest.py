"""Shared pytest fixtures for [[Chat_Root_Organizer_Service]]."""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from chat_organizer import db as db_module  # noqa: E402
from chat_organizer.service import Organizer  # noqa: E402

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture()
def conn():
    connection = db_module.connect(":memory:")
    yield connection
    connection.close()


@pytest.fixture()
def organizer(conn):
    return Organizer(conn=conn)


@pytest.fixture()
def chat_exports():
    """The synthetic chat-export fixtures, keyed by chat_id."""
    exports = {}
    for path in sorted(FIXTURE_DIR.glob("chat_*.json")):
        data = json.loads(path.read_text())
        exports[data["chat_id"]] = data
    return exports


class FakeProvider:
    """Stand-in for the host's conversation_search, for retrieval tests."""

    name = "fake"

    def __init__(self, hits):
        self.hits = hits
        self.calls = []

    def search(self, keywords, *, limit=10):
        self.calls.append(list(keywords))
        return list(self.hits)[:limit]


@pytest.fixture()
def fake_provider():
    return FakeProvider
