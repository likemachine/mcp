import logging

import psycopg

from db import DatabaseConfigError, get_connection


logger = logging.getLogger("postgres_mcp")
ALLOWED_SCHEMAS = frozenset({"public"})


def read_tables(schema: str = "public") -> dict:
    if schema not in ALLOWED_SCHEMAS:
        return {
            "status": "error",
            "error": {
                "code": "SCHEMA_NOT_ALLOWED",
                "message": "Only the public schema is allowed",
            },
        }

    try:
        with get_connection() as conn:
            tables = conn.execute("""
                SELECT
                    c.relname AS name,
                    CASE
                        WHEN c.reltuples < 0 THEN NULL
                        ELSE c.reltuples::bigint
                    END AS rows_estimate,
                    pg_catalog.pg_size_pretty(
                        pg_catalog.pg_total_relation_size(c.oid)
                    ) AS size
                FROM pg_catalog.pg_class AS c
                JOIN pg_catalog.pg_namespace AS n
                    ON n.oid = c.relnamespace
                WHERE n.nspname = %s
                  AND c.relkind = 'r'
                  AND pg_catalog.has_schema_privilege(n.oid, 'USAGE')
                  AND pg_catalog.has_table_privilege(c.oid, 'SELECT')
                ORDER BY c.relname
            """, (schema,)).fetchall()

        logger.info(
            "list_tables succeeded: schema=%s tables=%d",
            schema,
            len(tables),
        )
        return {"tables": tables}

    except DatabaseConfigError:
        logger.error("list_tables: invalid database configuration")
        return {
            "status": "error",
            "error": {
                "code": "DATABASE_CONFIG_ERROR",
                "message": "Database configuration is incomplete or invalid",
            },
        }

    except psycopg.Error:
        logger.error("list_tables: database query failed")
        return {
            "status": "error",
            "error": {
                "code": "DATABASE_ERROR",
                "message": "Unable to retrieve tables",
            },
        }


def register_schema_tools(mcp):
    @mcp.tool
    def list_tables(schema: str = "public") -> dict:
        """List readable ordinary tables in the allowed public schema.

        Return table names, estimated row counts and total sizes including
        indexes. An unknown row estimate is returned as null.
        """
        return read_tables(schema)

    @mcp.tool
    def describe_table(table: str, schema: str = "public") -> dict:
        """Describe a readable public table: columns, primary and foreign keys."""
        return read_table_description(table, schema)

    @mcp.tool
    def get_table_stats(table: str, schema: str = "public") -> dict:
        """Return estimated rows, total size, index names and analyze times."""
        return read_table_stats(table, schema)


def read_table_description(table: str, schema: str = "public") -> dict:
    if schema not in ALLOWED_SCHEMAS:
        return {
            "status": "error",
            "error": {
                "code": "SCHEMA_NOT_ALLOWED",
                "message": "Only the public schema is allowed",
            },
        }

    if not isinstance(table, str) or not table.strip():
        return {
            "status": "error",
            "error": {
                "code": "INVALID_TABLE_NAME",
                "message": "Table name must not be empty",
            },
        }

    try:
        with get_connection() as conn:
            relation = conn.execute("""
                SELECT c.oid
                FROM pg_catalog.pg_class AS c
                JOIN pg_catalog.pg_namespace AS n
                    ON n.oid = c.relnamespace
                WHERE n.nspname = %s
                  AND c.relname = %s
                  AND c.relkind = 'r'
                  AND pg_catalog.has_schema_privilege(n.oid, 'USAGE')
                  AND pg_catalog.has_table_privilege(c.oid, 'SELECT')
            """, (schema, table)).fetchone()

            if relation is None:
                return {
                    "status": "error",
                    "error": {
                        "code": "TABLE_NOT_FOUND",
                        "message": "Table does not exist or is not accessible",
                    },
                }

            oid = relation["oid"]

            columns = conn.execute("""
                SELECT
                    a.attname AS name,
                    pg_catalog.format_type(
                        a.atttypid, a.atttypmod
                    ) AS type,
                    NOT a.attnotnull AS nullable
                FROM pg_catalog.pg_attribute AS a
                WHERE a.attrelid = %s
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                ORDER BY a.attnum
            """, (oid,)).fetchall()

            primary_key_rows = conn.execute("""
                SELECT a.attname AS name
                FROM pg_catalog.pg_constraint AS k
                CROSS JOIN LATERAL
                    unnest(k.conkey) WITH ORDINALITY
                    AS key_col(attnum, position)
                JOIN pg_catalog.pg_attribute AS a
                    ON a.attrelid = k.conrelid
                   AND a.attnum = key_col.attnum
                WHERE k.conrelid = %s
                  AND k.contype = 'p'
                ORDER BY key_col.position
            """, (oid,)).fetchall()

            foreign_keys = conn.execute("""
                SELECT
                    k.conname AS constraint_name,
                    local_col.attname AS column,
                    target_schema.nspname AS referenced_schema,
                    target_table.relname AS referenced_table,
                    target_col.attname AS referenced_column,
                    target_table.relname || '.' ||
                        target_col.attname AS references,
                    key_col.position::integer AS position
                FROM pg_catalog.pg_constraint AS k
                CROSS JOIN LATERAL
                    unnest(k.conkey, k.confkey) WITH ORDINALITY
                    AS key_col(local_num, target_num, position)
                JOIN pg_catalog.pg_attribute AS local_col
                    ON local_col.attrelid = k.conrelid
                   AND local_col.attnum = key_col.local_num
                JOIN pg_catalog.pg_class AS target_table
                    ON target_table.oid = k.confrelid
                JOIN pg_catalog.pg_namespace AS target_schema
                    ON target_schema.oid = target_table.relnamespace
                JOIN pg_catalog.pg_attribute AS target_col
                    ON target_col.attrelid = k.confrelid
                   AND target_col.attnum = key_col.target_num
                WHERE k.conrelid = %s
                  AND k.contype = 'f'
                ORDER BY k.conname, key_col.position
            """, (oid,)).fetchall()

        logger.info(
            "describe_table succeeded: schema=%s table=%s",
            schema, table,
        )

        return {
            "schema": schema,
            "table": table,
            "columns": columns,
            "primary_key": [row["name"] for row in primary_key_rows],
            "foreign_keys": foreign_keys,
        }

    except DatabaseConfigError:
        logger.error("describe_table: invalid database configuration")
        return {
            "status": "error",
            "error": {
                "code": "DATABASE_CONFIG_ERROR",
                "message": "Database configuration is incomplete or invalid",
            },
        }

    except psycopg.Error:
        logger.error("describe_table: database query failed")
        return {
            "status": "error",
            "error": {
                "code": "DATABASE_ERROR",
                "message": "Unable to describe table",
            },
        }


def read_table_stats(table: str, schema: str = "public") -> dict:
    if schema not in ALLOWED_SCHEMAS:
        return {
            "status": "error",
            "error": {
                "code": "SCHEMA_NOT_ALLOWED",
                "message": "Only the public schema is allowed",
            },
        }

    if not isinstance(table, str) or not table.strip():
        return {
            "status": "error",
            "error": {
                "code": "INVALID_TABLE_NAME",
                "message": "Table name must not be empty",
            },
        }

    try:
        with get_connection() as conn:
            stats = conn.execute("""
                SELECT
                    c.oid,
                    c.relname AS table,
                    CASE
                        WHEN c.reltuples < 0 THEN NULL
                        ELSE c.reltuples::bigint
                    END AS estimated_rows,
                    pg_catalog.pg_size_pretty(
                        pg_catalog.pg_total_relation_size(c.oid)
                    ) AS size,
                    s.last_analyze,
                    s.last_autoanalyze
                FROM pg_catalog.pg_class AS c
                JOIN pg_catalog.pg_namespace AS n
                    ON n.oid = c.relnamespace
                LEFT JOIN pg_catalog.pg_stat_all_tables AS s
                    ON s.relid = c.oid
                WHERE n.nspname = %s
                  AND c.relname = %s
                  AND c.relkind = 'r'
                  AND pg_catalog.has_schema_privilege(n.oid, 'USAGE')
                  AND pg_catalog.has_table_privilege(c.oid, 'SELECT')
            """, (schema, table)).fetchone()

            if stats is None:
                return {
                    "status": "error",
                    "error": {
                        "code": "TABLE_NOT_FOUND",
                        "message": "Table does not exist or is not accessible",
                    },
                }

            oid = stats.pop("oid")

            indexes = conn.execute("""
                SELECT index_class.relname AS name
                FROM pg_catalog.pg_index AS i
                JOIN pg_catalog.pg_class AS index_class
                    ON index_class.oid = i.indexrelid
                WHERE i.indrelid = %s
                ORDER BY index_class.relname
            """, (oid,)).fetchall()

        stats["schema"] = schema
        stats["indexes"] = [index["name"] for index in indexes]

        for key in ("last_analyze", "last_autoanalyze"):
            if stats[key] is not None:
                stats[key] = stats[key].isoformat()

        logger.info(
            "get_table_stats succeeded: schema=%s table=%s",
            schema, table,
        )
        return stats

    except DatabaseConfigError:
        logger.error("get_table_stats: invalid database configuration")
        return {
            "status": "error",
            "error": {
                "code": "DATABASE_CONFIG_ERROR",
                "message": "Database configuration is incomplete or invalid",
            },
        }

    except psycopg.Error:
        logger.error("get_table_stats: database query failed")
        return {
            "status": "error",
            "error": {
                "code": "DATABASE_ERROR",
                "message": "Unable to retrieve table statistics",
            },
        }
