import json

from db import get_connection


def main():
    with get_connection() as conn:
        role = conn.execute("""
            SELECT
                rolname,
                rolsuper,
                rolcreaterole,
                rolcreatedb,
                rolreplication,
                rolbypassrls
            FROM pg_catalog.pg_roles
            WHERE rolname = current_user
        """).fetchone()

        schema = conn.execute("""
            SELECT
                pg_catalog.has_schema_privilege(
                    current_user, 'public', 'USAGE'
                ) AS can_use,
                pg_catalog.has_schema_privilege(
                    current_user, 'public', 'CREATE'
                ) AS can_create
        """).fetchone()

        tables = conn.execute("""
            SELECT
                c.relname AS name,
                pg_catalog.pg_get_userbyid(c.relowner) AS owner,
                c.relrowsecurity AS rls,
                pg_catalog.has_table_privilege(c.oid, 'INSERT')
                    AS can_insert,
                pg_catalog.has_table_privilege(c.oid, 'UPDATE')
                    AS can_update,
                pg_catalog.has_table_privilege(c.oid, 'DELETE')
                    AS can_delete,
                pg_catalog.has_table_privilege(c.oid, 'TRUNCATE')
                    AS can_truncate,
                pg_catalog.has_any_column_privilege(c.oid, 'INSERT')
                    AS can_insert_column,
                pg_catalog.has_any_column_privilege(c.oid, 'UPDATE')
                    AS can_update_column,
                pg_catalog.pg_has_role(c.relowner, 'USAGE')
                    AS owner_privileges
            FROM pg_catalog.pg_class AS c
            JOIN pg_catalog.pg_namespace AS n
                ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
              AND pg_catalog.has_table_privilege(c.oid, 'SELECT')
            ORDER BY c.relname
        """).fetchall()

    print("ROLE:")
    print(json.dumps(role, indent=2))
    print("PUBLIC SCHEMA:")
    print(json.dumps(schema, indent=2))
    print("READABLE TABLES:")
    print(json.dumps(tables, indent=2))

    assert role["rolname"] == "mcp_readonly", role

    for attribute in (
        "rolsuper",
        "rolcreaterole",
        "rolcreatedb",
        "rolreplication",
        "rolbypassrls",
    ):
        assert role[attribute] is False, (attribute, role)

    assert schema["can_use"] is True, schema
    assert schema["can_create"] is False, schema

    expected = {"clients", "products", "orders", "order_items"}
    assert expected <= {table["name"] for table in tables}, tables

    for table in tables:
        for privilege in (
            "can_insert",
            "can_update",
            "can_delete",
            "can_truncate",
            "can_insert_column",
            "can_update_column",
            "owner_privileges",
        ):
            assert table[privilege] is False, (privilege, table)

        assert table["rls"] is False, (
            "STOP: review RLS policies before proceeding",
            table,
        )

    print("ROLE ATTRIBUTES: PASS")
    print("SCHEMA PRIVILEGES: PASS")
    print("TABLE PRIVILEGES: PASS")
    print("DEMO RLS CHECK: PASS")
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
