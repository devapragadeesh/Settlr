"""The module-level ASGI app `uvicorn service.asgi:app` (and the
`Dockerfile`) actually serve. `service/api.py::create_app` takes a `db_path`
argument for testability (each test builds its own temp database); this
module is the one place that resolves that path from the environment for a
real deployment.
"""

from __future__ import annotations

import os
from pathlib import Path

from service.api import create_app

DB_PATH = Path(os.environ.get("STORE_DB_PATH", "recon.db"))

app = create_app(DB_PATH)
