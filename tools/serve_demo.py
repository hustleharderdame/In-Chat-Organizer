#!/usr/bin/env python3
"""Run the organizer with a few seeded nodes — for looking at the PWA locally.

    python3 tools/serve_demo.py [port]

Not part of the service: a dev harness, so the front-end can be driven without
a real DDB.OS database.
"""
from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from flask import Flask
from chat_organizer import Organizer
from chat_organizer.api import attach

SEED = [
    "Starting a new project for the driver onboarding flow.",
    "We're going with flat per-trip pricing for Stay Driving. Hourly is retired.",
    "The graph table must have canon_id as its primary key.",
    "TODO: update the booking form to show the flat rate.",
    "TODO: write the background check step for new drivers.",
    "Should we build the standalone offline fallback now, or defer it?",
    "The retrieval layer depends on [[COS_Root_Organizer_Protocol]].",
]

def build(db_path=":memory:"):
    org = Organizer(db_path)
    root = org.ingest(SEED[0]).written[0]
    for turn in SEED[1:]:
        org.ingest(turn, parent_root=root.canon_id, source_chat="seed")
    app = Flask(__name__)
    attach(app, org)
    return app

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8410
    build().run(host="127.0.0.1", port=port, debug=False)
