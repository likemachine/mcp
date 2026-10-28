from pathlib import Path

import psycopg
from dotenv import dotenv_values

config = dotenv_values(Path(__file__).resolve().parent / ".env")

checks = [
    (
        "INSERT",
        "INSERT INTO public.mcp_permission_probe (id, note) "
        "VALUES (2, 'must not be saved')",
    ),
    (
        "UPDATE",
        "UPDATE public.mcp_permission_probe SET note = 'changed' WHERE id = 1",
    ),
    (
        "DELETE",
        "DELETE FROM public.mcp_permission_probe WHERE id = 1",
    ),
]

with psycopg.connect(
    host=config["PGHOST"],
    port=int(config["PGPORT"]),
    dbname=config["PGDATABASE"],
    user=config["PGUSER"],
    password=config["PGPASSWORD"],
    connect_timeout=5,
    options="-c statement_timeout=5000",
) as conn:
    conn.read_only = False

    user = conn.execute("SELECT current_user").fetchone()[0]
    conn.rollback()

    print("USER:", user)
    if user != "mcp_readonly":
        raise SystemExit("STOP: expected mcp_readonly")

    failures = 0

    row = conn.execute(
        "SELECT id, note FROM public.mcp_permission_probe WHERE id = 1"
    ).fetchone()
    conn.rollback()

    if row == (1, "Read-only permission test"):
        print("SELECT: PASS")
    else:
        failures += 1
        print("SELECT: FAIL", row)

    can_create = conn.execute(
        "SELECT has_schema_privilege(current_user, 'public', 'CREATE')"
    ).fetchone()[0]
    conn.rollback()

    if can_create:
        failures += 1
        print("CREATE in public: FAIL - privilege exists")
    else:
        print("CREATE in public: PASS - no privilege")

    for name, sql in checks:
        try:
            conn.execute(sql)
        except psycopg.errors.InsufficientPrivilege:
            print(f"{name}: PASS - permission denied")
        except psycopg.Error as exc:
            failures += 1
            print(f"{name}: FAIL - unexpected error {exc.sqlstate}")
        else:
            failures += 1
            print(f"{name}: FAIL - operation was allowed")
        finally:
            conn.rollback()

    print("RESULT:", "PASS" if failures == 0 else "FAIL")
    if failures:
        raise SystemExit(1)
