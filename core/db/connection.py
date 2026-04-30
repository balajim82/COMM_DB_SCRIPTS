import psycopg2
from psycopg2.extras import RealDictCursor

from config import settings


def _build_dsn() -> dict:
    """Build psycopg2 connection kwargs from settings.

    Priority:
      1. DATABASE_URL  – used as-is if set (credentials already embedded).
      2. Individual fields: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD.
    Raises RuntimeError if neither option is fully configured.
    """
    if settings.DATABASE_URL:
        return {"dsn": settings.DATABASE_URL}

    missing = [
        var for var, val in {
            "DB_HOST": settings.DB_HOST,
            "DB_NAME": settings.DB_NAME,
            "DB_USER": settings.DB_USER,
            "DB_PASSWORD": settings.DB_PASSWORD,
        }.items()
        if not val
    ]
    if missing:
        raise RuntimeError(
            "Database not configured. Set DATABASE_URL  OR  all of: "
            + ", ".join(missing)
            + "  in your .env file."
        )

    return {
        "host": settings.DB_HOST,
        "port": settings.DB_PORT,
        "dbname": settings.DB_NAME,
        "user": settings.DB_USER,
        "password": settings.DB_PASSWORD,
        "sslmode": settings.DB_SSLMODE,
    }


def get_connection():
    """Return a new psycopg2 connection.

    Reads credentials from DATABASE_URL (Option 1) or individual DB_* vars
    (Option 2) as defined in .env.
    """
    return psycopg2.connect(**_build_dsn())


def fetch_table_schema(table_name: str) -> list[dict]:
    """Return column definitions for *table_name* from information_schema.

    table_name is matched case-insensitively (lowercased before query).
    """
    sql = """
        SELECT
            column_name,
            data_type,
            udt_name,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (table_name.lower(),))
            return [dict(row) for row in cur.fetchall()]


def fetch_constraints(table_name: str) -> list[dict]:
    """Return PK and FK constraint details for *table_name*."""
    sql = """
        SELECT
            tc.constraint_name,
            tc.constraint_type,
            kcu.column_name,
            ccu.table_name  AS foreign_table_name,
            ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints   tc
        JOIN information_schema.key_column_usage    kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema   = kcu.table_schema
        LEFT JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
            AND tc.table_schema   = ccu.table_schema
        WHERE tc.table_name     = %s
          AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')
        ORDER BY tc.constraint_type, kcu.ordinal_position
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (table_name.lower(),))
            return [dict(row) for row in cur.fetchall()]


def table_exists(table_name: str) -> bool:
    sql = """
        SELECT 1
        FROM information_schema.tables
        WHERE table_name = %s
        LIMIT 1
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (table_name.lower(),))
            return cur.fetchone() is not None


def _split_statements(sql: str) -> list[str]:
    """Split SQL on semicolons while respecting dollar-quoted blocks (DO $$ ... $$).

    A naive split on ';' breaks DO $$ BEGIN ... ; END $$; blocks because the
    semicolon after PERFORM is inside the dollar-quote. This parser tracks
    whether the cursor is inside a $$-delimited block before splitting.
    """
    statements: list[str] = []
    buf: list[str] = []
    in_dollar_quote = False
    i = 0

    while i < len(sql):
        ch = sql[i]

        if sql[i : i + 2] == "$$":
            in_dollar_quote = not in_dollar_quote
            buf.append("$$")
            i += 2
            continue

        if ch == ";" and not in_dollar_quote:
            stmt = "".join(buf).strip()
            if stmt:
                # Drop pure-comment blocks
                non_comment = "\n".join(
                    ln for ln in stmt.splitlines()
                    if not ln.strip().startswith("--")
                ).strip()
                if non_comment:
                    statements.append(stmt)
            buf = []
        else:
            buf.append(ch)

        i += 1

    # Trailing content without a final semicolon
    stmt = "".join(buf).strip()
    if stmt:
        non_comment = "\n".join(
            ln for ln in stmt.splitlines() if not ln.strip().startswith("--")
        ).strip()
        if non_comment:
            statements.append(stmt)

    return statements


def execute_sql(sql: str) -> None:
    """Execute a SQL string (single or multi-statement) and commit.

    Handles dollar-quoted blocks (DO $$ ... $$;) correctly — the semicolons
    inside those blocks are not treated as statement separators.
    """
    statements = _split_statements(sql)
    with get_connection() as conn:
        with conn.cursor() as cur:
            for stmt in statements:
                cur.execute(stmt)
        conn.commit()
