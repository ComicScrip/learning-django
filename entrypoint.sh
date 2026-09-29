#!/usr/bin/env bash
set -euo pipefail

# Wait for the database to accept connections before running migrations.
python - <<'PYEOF'
import os
import sys
import time

import psycopg

host = os.environ.get("POSTGRES_HOST", "localhost")
port = os.environ.get("POSTGRES_PORT", "5432")
user = os.environ.get("POSTGRES_USER", "appuser")
password = os.environ.get("POSTGRES_PASSWORD", "")
dbname = os.environ.get("POSTGRES_DB", "appdb")

deadline = time.time() + 60
while time.time() < deadline:
    try:
        conn = psycopg.connect(
            host=host, port=port, user=user, password=password, dbname=dbname, connect_timeout=3
        )
        conn.close()
        print("Database is available.")
        sys.exit(0)
    except psycopg.OperationalError as exc:
        print(f"Waiting for database at {host}:{port}... ({exc})")
        time.sleep(2)

print("Database did not become available in time.", file=sys.stderr)
sys.exit(1)
PYEOF

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    python manage.py migrate --noinput
fi

if [ "${COLLECT_STATIC:-true}" = "true" ]; then
    python manage.py collectstatic --noinput
fi

exec "$@"
