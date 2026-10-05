"""Database access. Everything the app (and the agent) reads goes through run_select()."""
import os
import re

import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Words that must never appear in a query. The database user is read-only too,
# but a second layer is cheap and gives the agent a clear error message.
FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|call|do|merge)\b",
    re.IGNORECASE,
)


def check_select(sql: str) -> str:
    """Return the query without a trailing ';', or raise ValueError if it is not one plain SELECT."""
    sql = sql.strip().rstrip(";").strip()
    if ";" in sql:
        raise ValueError("Only one statement is allowed.")
    if not re.match(r"(select|with)\b", sql, re.IGNORECASE):
        raise ValueError("Only SELECT queries are allowed.")
    if FORBIDDEN.search(sql):
        raise ValueError("Only read-only queries are allowed.")
    return sql


def run_select(sql: str, max_rows: int = 200) -> pd.DataFrame:
    """Run one read-only query and return at most max_rows rows as a DataFrame."""
    sql = check_select(sql)
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is missing. Add it to the .env file.")

    conn = psycopg2.connect(url)
    try:
        conn.set_session(readonly=True)  # the database itself refuses any write
        with conn.cursor() as cur:
            # Set inside the transaction: the Neon pooler rejects it as a connection option.
            cur.execute("set local statement_timeout = 20000")  # stop slow queries after 20 s
            # Wrapping the query lets us cap the rows without touching the query itself.
            cur.execute(f"select * from ({sql}) as q limit {int(max_rows)}")
            columns = [c[0] for c in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=columns)
    finally:
        conn.close()
