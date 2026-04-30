"""Fetch organisation codes from the admin schema."""

from core.db.connection import get_connection


def fetch_org_codes() -> list[str]:
    """Return all org_code values from admin."Organizations", ordered alphabetically.

    Assumes the table exists in the admin schema with an org_code TEXT column.
    Raises RuntimeError with a clear message if the table or column is missing.
    """
    sql = 'SELECT org_code FROM admin."Organizations" ORDER BY org_code'
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
    except Exception as exc:
        raise RuntimeError(
            f'Failed to fetch org codes from admin."Organizations": {exc}\n'
            "Ensure the table exists and DATABASE_URL (or DB_* vars) is configured in .env"
        ) from exc

    return [row[0] for row in rows]
