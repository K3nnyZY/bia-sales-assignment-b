"""HTTP smoke test of the complete frontend -> API -> PostgreSQL path (stdlib only)."""

import argparse
import json
from urllib.request import urlopen

parser = argparse.ArgumentParser()
parser.add_argument("--api-url", default="http://127.0.0.1:8000")
parser.add_argument("--web-url", default="http://127.0.0.1:3000")
args = parser.parse_args()


def get(base, path):
    with urlopen(f"{base.rstrip('/')}{path}", timeout=10) as response:
        assert response.status == 200
        return response.read().decode()


assert json.loads(get(args.api_url, "/health"))["status"] == "ok"
ready = json.loads(get(args.api_url, "/health/ready"))
assert ready == {"status": "ok", "service": "bia-api", "database": "ok", "migrations": "ok"}
assert json.loads(get(args.web_url, "/health")) == {"status": "ok", "service": "bia-web"}
proxy = json.loads(get(args.web_url, "/api/health"))
assert proxy == {"health": ready, "error": None}
assert "BIA Agent Studio" in get(args.web_url, "/")
print("PASS: frontend -> FastAPI -> PostgreSQL + Alembic; all HTTP health checks passed.")
