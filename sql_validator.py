import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, SqlglotError
from sqlglot.optimizer.scope import build_scope


MAX_SQL_LENGTH = 4000


class SQLValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# Conservative supported subset. Unknown AST nodes are rejected.
ALLOWED_NODES = frozenset("""
Select From Table Identifier Column Star
Alias TableAlias
With CTE Subquery
Join Where Group Having Order Ordered Limit Offset
Distinct
Literal Null Boolean
Paren Tuple
And Or Not
EQ NEQ GT GTE LT LTE
Is In Between Like ILike
Add Sub Mul Div Mod Neg
Case If
Count Sum Avg Min Max Abs Round Lower Upper Coalesce
Extract Var DateTrunc TimestampTrunc Floor Ceil Length Concat DPipe
""".split())


def reject(code: str, message: str):
    raise SQLValidationError(code, message)


def validate_select(sql: str) -> str:
    """Validate a restricted SELECT and return normalized PostgreSQL SQL."""
    if not isinstance(sql, str) or not sql.strip():
        reject("EMPTY_SQL", "SQL must be a non-empty string")

    if len(sql) > MAX_SQL_LENGTH:
        reject("SQL_TOO_LONG", "SQL must not exceed 4000 characters")

    try:
        statements = sqlglot.parse(
            sql,
            read="postgres",
            error_level=ErrorLevel.RAISE,
        )
    except (SqlglotError, RecursionError):
        reject("INVALID_SQL", "Unable to parse SQL")

    if len(statements) != 1:
        reject("MULTIPLE_STATEMENTS", "Exactly one statement is allowed")

    tree = statements[0]
    if not isinstance(tree, exp.Select):
        reject("SELECT_ONLY", "Only SELECT or WITH ... SELECT is allowed")

    for node in tree.walk():
        if type(node).__name__ not in ALLOWED_NODES:
            reject(
                "UNSUPPORTED_SQL",
                "SQL contains a forbidden or unsupported construct",
            )

        if isinstance(node, exp.With) and node.args.get("recursive"):
            reject("UNSUPPORTED_SQL", "Recursive CTEs are not supported")

        if isinstance(node, exp.Column):
            if node.args.get("catalog") or node.args.get("db"):
                reject(
                    "UNSUPPORTED_SQL",
                    "Use table.column rather than schema.table.column",
                )

    try:
        root_scope = build_scope(tree)
        if root_scope is None:
            reject("INVALID_SQL", "Unable to resolve query scopes")

        physical_tables = {}
        for scope in root_scope.traverse():
            for _, source in scope.selected_sources.values():
                if isinstance(source, exp.Table):
                    physical_tables[id(source)] = source

    except SQLValidationError:
        raise
    except (SqlglotError, ValueError, RecursionError):
        reject("INVALID_SQL", "Unable to resolve query scopes")

    for table in physical_tables.values():
        if not isinstance(table.this, exp.Identifier):
            reject("UNSUPPORTED_SQL", "Only named tables are allowed")

        schema = table.args.get("db")
        if table.args.get("catalog"):
            reject("SCHEMA_NOT_ALLOWED", "Catalog-qualified names are forbidden")

        if schema is not None:
            if not isinstance(schema, exp.Identifier) or schema.name != "public":
                reject("SCHEMA_NOT_ALLOWED", "Only public tables are allowed")

        # Also reject unqualified names resembling system relations.
        if table.name.lower().startswith(("pg_", "sql_")):
            reject("SYSTEM_TABLE_FORBIDDEN", "System relations are forbidden")

        table.set("db", exp.to_identifier("public"))

    return tree.sql(dialect="postgres")
