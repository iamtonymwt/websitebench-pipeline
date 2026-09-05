"""Test fixtures for the monoprice clone.

Each test gets its own database in a temporary directory, and each test gets its
own client with its own cookie jar. Both matter:

* Sharing a database across tests makes a purchase in one test change the cart
  another test is asserting on. On the previous site 185 tasks shared one cookie
  jar, the first twenty filled the same cart, and nineteen "cart is empty after
  checkout" tasks failed -- a defect in the scaffolding that read exactly like a
  defect in the clone.
* The backend refuses a database whose filename does not match the runtime
  contract, so the temporary file has to be named `<site>.sqlite3`, not
  whatever `mktemp` produces.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest

CLONE_DIR = pathlib.Path(__file__).resolve().parents[1]
SITE_DIR = CLONE_DIR.parent
sys.path.insert(0, str(CLONE_DIR))


@pytest.fixture(scope="session")
def catalogue() -> dict:
    return json.loads((SITE_DIR / "data" / "catalogue.json").read_text(encoding="utf-8"))


@pytest.fixture
def clone_app(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv("WEBSITEBENCH_SITE_BACKEND_DATABASE",
                       str(data_dir / "monoprice.sqlite3"))
    for module in ("app", "commerce", "backend.site_backend_integration"):
        sys.modules.pop(module, None)
    import app as clone_module
    return clone_module


@pytest.fixture
def client(clone_app):
    from fastapi.testclient import TestClient

    with TestClient(clone_app.app) as test_client:
        yield test_client


@pytest.fixture
def backend(client, clone_app):
    # Depends on `client` so startup has run and the backend is open.
    return clone_app._state["backend"]


@pytest.fixture(autouse=True)
def _keep_cwd():
    before = os.getcwd()
    yield
    os.chdir(before)
