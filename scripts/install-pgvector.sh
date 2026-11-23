#!/usr/bin/env bash
set -euo pipefail
pg_config_bin=${PG_CONFIG:-pg_config}
case "$("$pg_config_bin" --version)" in
  'PostgreSQL 18.'*) ;;
  *) echo 'pgvector for this project requires PostgreSQL 18.' >&2; exit 1 ;;
esac
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
curl --fail --silent --show-error --location https://codeload.github.com/pgvector/pgvector/tar.gz/refs/tags/v0.8.7 -o "$stage/pgvector.tgz"
echo "cac0b10c360f05b2d521200105ba3697e773d4cd3731f5a915a7e37ebe0bea85  $stage/pgvector.tgz" | shasum -a 256 -c -
tar -xzf "$stage/pgvector.tgz" -C "$stage"
make -C "$stage/pgvector-0.8.7" PG_CONFIG="$pg_config_bin" OPTFLAGS=""
make -C "$stage/pgvector-0.8.7" PG_CONFIG="$pg_config_bin" install
