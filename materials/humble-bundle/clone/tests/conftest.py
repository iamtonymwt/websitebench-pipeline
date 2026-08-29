"""Test bootstrap: clone dir on sys.path + isolated bound database.

The database env var must be set before anything opens the seam so test
runs never touch the repo's default data dir; the filename must match the
runtime contract (``humble-bundle.sqlite3``).
"""

import os
import sys
import tempfile
from pathlib import Path

CLONE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLONE_DIR))

_DB_DIR = Path(tempfile.mkdtemp(prefix="humble-bundle-clone-tests-"))
os.environ["WEBSITEBENCH_SITE_BACKEND_DATABASE"] = str(
    _DB_DIR / "humble-bundle.sqlite3"
)

import pytest  # noqa: E402

from backend import catalog_db  # noqa: E402


@pytest.fixture()
def db():
    """The business backend, restored to the deterministic seed state."""

    catalog_db.reset()
    return catalog_db
