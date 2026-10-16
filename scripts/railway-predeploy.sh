#!/bin/sh
set -eu
alembic -c apps/api/alembic.ini upgrade head
python -m app.deployment.bootstrap
