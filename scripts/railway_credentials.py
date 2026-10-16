"""Generate private, seven-day deployment credentials and a hash-only bootstrap manifest."""

import argparse
import hashlib
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4


def write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(data, output, indent=2)
        output.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(".tools"))
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    credentials, manifest = {}, {}
    expiry = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    for role in [
        "administrator",
        "creator",
        "viewer",
        "customer-b",
        "reviewer",
        "approver",
        "auditor",
    ]:
        token = "bia_" + secrets.token_urlsafe(32)
        info = {"id": "pat-" + uuid4().hex, "user_id": "demo-" + role, "expires_at": expiry}
        credentials[role] = {**info, "token": token}
        manifest[role] = {**info, "token_hash": hashlib.sha256(token.encode()).hexdigest()}
    # Only the hash-only manifest is sent to the backend. Neither file belongs in Git/builds.
    write_private(args.directory / "railway-credentials.json", credentials)
    write_private(args.directory / "railway-manifest.json", manifest)
    write_private(
        args.directory / "railway-secrets.json",
        {"postgres_password": secrets.token_hex(32), "manifest": manifest},
    )
    print("Created private credential and hash-only manifest files (0600); expires in seven days.")


if __name__ == "__main__":
    main()
