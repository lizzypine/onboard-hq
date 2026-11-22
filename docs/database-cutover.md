# Normalized database cutover

This runbook releases the twelve-table integer-ID schema and its matching app
as one unit. It is an operator procedure, not an automatic startup task. A merged
PR does not apply it to Neon. Obtain explicit authorization for the intended live
database before the maintenance window.

Archive/Restore/Delete action buttons and managed sign-in are separate follow-ups.
The app already respects archived state as view-only. Use synthetic records only.

## Before the window

1. Review `20261115000100_normalize_checklists.sql` line by line against all eleven
   checks in `docs/database-design.md`. Require green Ruff, mypy, unit, PostgreSQL,
   and browser checks and the whole-branch review. Do not edit the three applied
   migrations.
2. Pin both application revisions. The tested UUID baseline is
   `3f498780ab4703ec04363a6c0eafaac2db4c8430`; pin the reviewed implementation
   release when it is merged. Keep the old app available for recovery.
3. Rehearse the exact release against an isolated copy and a separate empty
   recovery database. The automated rehearsal in
   `tests/e2e/test_database_upgrade.py` uses disposable loopback PostgreSQL 18,
   the pinned old app, TestModel, and an actual lost browser-save response. It
   never uses the configured Neon database.
4. Choose private durable storage for the final backup, outside Git. Verify
   PostgreSQL 18 `pg_dump` and `pg_restore` are on PATH. Keep credentials in `.env`;
   never pass a connection URI as a tool argument or print the environment.
5. Verify the intended Neon project, direct endpoint, and database in its console.
   `.env` must point `DATABASE_URL_UNPOOLED` to that direct connection and
   `DATABASE_URL` to its matching app connection. Keep
   `DBMATE_NO_DUMP_SCHEMA=true`. Do not display either URL in logs or screenshots.

## Freeze writes, then take the final backup

Stop user traffic and every old app worker. Drain/resolve in-flight requests and
confirm no old process can finish another write. Keep writes stopped until the
new app passes read-only validation. An earlier rehearsal backup does not include
writes made since it was taken and is insufficient for rollback.

Record expected provider/checklist/history counts and selected retry keys,
statuses, dates, deadlines, counters, and captured context using read-only checks.
Preserve browser tabs/session storage, including unconfirmed saves; do not clear
browser storage as part of the upgrade.

Set `CUTOVER_BACKUP` to a new protected durable filename and `CUTOVER_ACTION` to
`backup`. The following block passes connection settings only in the child
environment, writes no credential file, and refuses to overwrite a backup.
`CUTOVER_*` variables are operator inputs, not application settings.

```sh
umask 077
CUTOVER_ACTION=backup CUTOVER_BACKUP=/your/private/durable/final.dump \
uv run --env-file .env python - <<'PY'
import os
import subprocess
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict

try:
    action = os.environ['CUTOVER_ACTION']
    archive = Path(os.environ['CUTOVER_BACKUP'])
    uri = os.environ['DATABASE_URL_UNPOOLED']
    options = conninfo_to_dict(uri)
    if action not in {'backup', 'restore'}:
        raise ValueError
    child = {'PATH': os.environ['PATH'], 'PGPASSFILE': '/dev/null',
             'PGSERVICEFILE': '/dev/null', 'PGCONNECT_TIMEOUT': '10'}
    for option, variable in [('host','PGHOST'), ('port','PGPORT'),
                             ('dbname','PGDATABASE'), ('user','PGUSER'),
                             ('password','PGPASSWORD'), ('sslmode','PGSSLMODE'),
                             ('channel_binding','PGCHANNELBINDING'),
                             ('sslrootcert','PGSSLROOTCERT')]:
        if option in options:
            child[variable] = options[option]
    if action == 'backup':
        if archive.exists():
            raise ValueError
        args = ['pg_dump','--format=custom','--no-owner','--no-acl',
                '--file',str(archive)]
    else:
        # Only a separately chosen EMPTY recovery database may receive a restore.
        with psycopg.connect(uri) as conn:
            if conn.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]:
                raise ValueError
        args = ['pg_restore','--exit-on-error','--no-owner','--no-acl',
                '--dbname',options['dbname'],str(archive)]
    result = subprocess.run(args,env=child,capture_output=True,check=False)
    if result.returncode:
        raise ValueError
    print('Backup/restore command completed; verify the resulting records.')
except Exception:
    raise SystemExit('Backup/restore failed. Check the chosen target and tools without printing credentials.') from None
PY
```

Verify the **final** backup by restoring it to the separate empty recovery database
and comparing the recorded evidence, including the last committed write. For the
restore, first select that recovery database in `.env`, then use the same block
with `CUTOVER_ACTION=restore` and the existing archive path. Run the pinned old app
against the recovery database and verify its original UUID-linked records through
read-only requests. Stop that app after verification. Re-select and independently
verify the live target in `.env` before migrating; keep live writes stopped.

## Apply and validate

Only after the final backup is recoverable, apply the reviewed migration explicitly:

```sh
npx dbmate --no-dump-schema -e DATABASE_URL_UNPOOLED migrate
npx dbmate --no-dump-schema -e DATABASE_URL_UNPOOLED status --exit-code
```

Require four applied migrations and `Pending: 0`. A preflight failure leaves the
old schema and migration state unchanged: resolve the reported data conflict and
rehearse again; do not remove checks or discard history to force conversion.

Start only the matching new app revision, still behind the write freeze. Compare
all recorded counts and values. Verify twelve application tables, ten integer
identity primary keys, two composite junction keys, fourteen explicit foreign
keys, preserved creation/analysis/manual retry UUIDs, and the new snapshot/warning
rows. Check the full selected checklist and original evidence through read-only
HTTP requests. Do not seed an existing database to repair mismatches.

Reload browser assets onto the new release. Legacy save recovery makes only GET
requests: a matching committed operation opens its current saved view; an
unresolved or conflicting draft stays visible until explicit dismissal. Confirm
archived providers remain view-only. Reopen user writes only after validation.

For a deliberately empty development database, the explicit seed is
`uv run --env-file .env python -m db.seed`; it loads five synthetic checklist rows.
It never runs at startup. Generate `db/schema.sql` only from passwordless disposable
local PostgreSQL, not from the credentialed application connection.

## Recovery

The new SQL `down` intentionally refuses the UUID-to-integer conversion and leaves
target data intact. The target does not retain every former UUID; a fabricated
SQL downgrade would break record identity/history.

If validation fails **before new writes are admitted**, keep traffic stopped,
restore the verified final backup into a separate empty recovery database, and
run the pinned old app against that verified database. Switch connections only
after its read-only UUID/history checks pass. Never restore over populated target
tables or mix old and new workers.

After new writes begin, an older backup cannot preserve those later changes.
Stop traffic, preserve the new state, and use a reviewed forward fix or explicit
reconciliation. Do not automatically restore the older backup and lose new work.
