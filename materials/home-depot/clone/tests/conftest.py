"""Test bootstrap: isolated database + clone dir on sys.path before app import."""
import os
import sys
import tempfile
from pathlib import Path

CLONE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLONE_DIR))

_DB_DIR = Path(tempfile.mkdtemp(prefix="home-depot-clone-tests-"))
os.environ["WEBSITEBENCH_SITE_BACKEND_DATABASE"] = str(_DB_DIR / "home-depot.sqlite3")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402
from backend import catalog_db  # noqa: E402


@pytest.fixture()
def client():
    catalog_db.reset()
    with TestClient(app_module.app, base_url="http://testserver") as c:
        yield c
    catalog_db.reset()
