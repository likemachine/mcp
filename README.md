# PostgreSQL MCP Server for LMOS

Python/FastMCP server for controlled access to PostgreSQL
from an LMOS multi-agent system.

## Current status

Implemented:
- MCP tool: get_db_health.
- PostgreSQL connectivity through psycopg.
- Configuration through a local .env file.
- Dedicated database role: mcp_readonly.
- Read-only health-check transaction.
- Docker image with dependencies installed from local wheels.
- Docker Compose configuration.
- In-process MCP client smoke test inside a container.

Not implemented yet:
- Schema inspection tools.
- User-provided SQL execution and validation.
- LMOS integration.
- Automated database initialization for a clean installation.
- Full automated test suite.

## Current deployment

The current configuration targets an Ubuntu Linux server.

PostgreSQL:
- Image: postgres:16.
- Database: mcp.
- MCP connection role: mcp_readonly.
- Data directory: ./pgdata.
- Published address: 127.0.0.1:5432.

The Compose file expects an already initialized PostgreSQL data directory.
It is not yet a complete clean-install deployment.

The MCP service currently uses host networking and STDIO transport.
No HTTP endpoint is exposed.

## Configuration

Create .env using .env.example as a template.

The configured database and role must already exist.
Do not commit .env or real credentials.

## Build

Prerequisites:
- Docker Engine and Docker Compose.
- Local image: python:3.11-slim-bookworm.
- Local image: postgres:16.
- Compatible dependency wheels in ./wheelhouse.

Build the application image:

    docker build --pull=false --network=none -t lmos-postgres-mcp:dev .

## Run PostgreSQL

    docker compose up -d --wait --wait-timeout 60 postgres

Do not start another PostgreSQL container against the same data directory.

## MCP smoke test

    docker compose run --rm --no-deps mcp python check_mcp.py

Expected:
- Tool list contains get_db_health.
- database is mcp.
- db_user is mcp_readonly.
- read_only is true.
- status is ok.

This test uses an in-process MCP client and server.
It does not verify a separate STDIO subprocess or LMOS integration.

## Security status

Verified using a disposable test table:
- SELECT succeeds.
- INSERT, UPDATE and DELETE are denied for mcp_readonly.
- CREATE privilege on schema public is absent.

This is not a complete security audit.
SQL validation and additional restrictions are planned.

## Repository exclusions

Do not commit:
- .env
- .venv/
- pgdata/
- wheelhouse/
- backups/

## Schema tools

The server exposes three read-only PostgreSQL schema tools. All tools accept
only the `public` schema, pass identifiers as SQL parameters, and return
structured JSON.

### list_tables

Returns readable tables in the `public` schema.

```json
{
  "schema": "public",
  "tables": ["clients", "orders", "products"]
}

describe_table
Returns columns, primary key columns and foreign keys for one table.
{
  "schema": "public",
  "table": "orders",
  "columns": [
    {"name": "id", "type": "bigint", "nullable": false},
    {"name": "client_id", "type": "bigint", "nullable": false}
  ],
  "primary_key": ["id"],
  "foreign_keys": [
    {
      "column": "client_id",
      "references": "clients.id"
    }
  ]
}

get_table_stats
Returns approximate row count, total table size, index names and analyze
timestamps. It does not execute  COUNT(*)  or  ANALYZE ; it reads existing
PostgreSQL metadata and cumulative statistics.
{
  "schema": "public",
  "table": "orders",
  "estimated_rows": 200,
  "size": "96 kB",
  "last_analyze": "2026-10-28T11:24:19.868775+00:00",
  "last_autoanalyze": "2026-10-28T11:24:37.330960+00:00",
  "indexes": [
    "orders_pkey",
    "idx_orders_client_id",
    "idx_orders_created_at"
  ]
}

 estimated_rows  is PostgreSQL’s planner estimate and may be  null  before
statistics have been collected.  last_analyze  reports the latest manual
 ANALYZE ;  last_autoanalyze  reports the latest automatic analyze.
Checks
Run all unit tests:
python -m pytest tests/ -q

Run MCP integration checks against the configured PostgreSQL database:
python check_mcp.py
python check_describe.py
python check_stats.py

Expected result for every check:
RESULT: PASS

