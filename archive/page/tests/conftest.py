"""Shared pytest fixtures for the archived static Flask site.

Importing ``project`` is offline-safe: the app no longer connects to Google
Sheets at import time, so the test client can render every marketing page
without network access. The handful of data routes reach Sheets lazily and
are exercised with ``gspread`` mocked (see ``test_data_routes.py``).

Run with::

    cd archive/page && python -m pytest
"""

import os
import sys

# Make ``project`` / ``config`` importable however pytest is invoked
# (a pytest.ini at the project root would be gitignored by ``*.ini``).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from project import app as flask_app


@pytest.fixture
def app():
    flask_app.config.update(TESTING=True)
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()
