#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${TMPDIR:-/tmp}/onboard-uv-cache}"
if [ -z "${PG18_BIN:-}" ]; then
  if [ -d /opt/homebrew/opt/postgresql@18/bin ]; then PG18_BIN=/opt/homebrew/opt/postgresql@18/bin
  elif [ -d /usr/local/opt/postgresql@18/bin ]; then PG18_BIN=/usr/local/opt/postgresql@18/bin
  else PG18_BIN=$(pg_config --bindir); fi
fi
export PATH="$PG18_BIN:$root/.superpowers/bin:$PATH"
if ! pg_dump --version | grep -q ' 18\.'; then echo "Install PostgreSQL 18 and set PG18_BIN to its bin directory." >&2; exit 1; fi
if [ ! -x "$root/.superpowers/bin/dbmate" ]; then echo "Run bash scripts/install-dbmate.sh first." >&2; exit 1; fi
temporary=""
cleanup() {
  status=$?
  trap - EXIT
  if [ -n "$temporary" ]; then
    pg_ctl -D "$temporary/data" stop -m fast >/dev/null 2>&1 || true
    rm -rf "$temporary"
  fi
  exit "$status"
}
trap cleanup EXIT
if [ -z "${TEST_DATABASE_URL:-}" ]; then
  temporary=$(mktemp -d /tmp/onboard-test.XXXXXX)
  port=$(uv run python -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
  initdb -D "$temporary/data" -U postgres -A trust --no-locale -E UTF8 >/dev/null
  pg_ctl -D "$temporary/data" -l "$temporary/postgres.log" -o "-h 127.0.0.1 -p $port -k $temporary" start >/dev/null
  createdb -h 127.0.0.1 -p "$port" -U postgres onboard_hq_test_local
  export TEST_DATABASE_URL="postgresql://postgres@127.0.0.1:$port/onboard_hq_test_local?sslmode=disable"
fi
uv run python -c 'from tests.database import configured_test_url; configured_test_url()'
"$@"
