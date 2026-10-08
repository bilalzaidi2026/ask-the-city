"""
The agent's tools: the only things Claude can make happen.

Claude never touches the database. It asks for a tool by name with some inputs;
this file decides whether and how that request runs.

Two tools for now:
  describe_table  read a table's columns, sample rows and data guide
  run_sql         run one read-only SELECT query in a sandbox
"""
import threading
from pathlib import Path

import duckdb

from agent import charts

ROOT = Path(__file__).parent.parent
DB_FILE = ROOT / "data" / "city.duckdb"
GUIDES = ROOT / "data" / "guides"

QUERY_TIMEOUT_SECONDS = 20  # stop runaway queries
MAX_ROWS_SHOWN = 50         # rows sent back to Claude per query
MAX_CELL_CHARS = 80         # long text fields get trimmed

# Which guide explains which table.
GUIDE_FOR_TABLE = {
    "complaints_311": "complaints_311.md",
    "restaurant_inspections": "restaurant_inspections.md",
    "population_borough": "population.md",
    "population_zip": "population.md",
}


# ---------------------------------------------------------------- the sandbox

_database = None
_database_lock = threading.Lock()


def open_sandbox():
    """Give one question its own cursor on the shared, locked-down database.

    The database is opened once per program with its protections built in:
      layer 1: read_only               can't change data
      layer 2: enable_external_access  can't read or write files, or reach the web
               lock_configuration      ...and no query can switch that back on
    These settings belong to the whole database, so they can't be applied per
    connection. (The first version tried, and crashed as soon as two questions
    ran at the same time.) Each question gets a cursor: a separate connection to
    the same protected database, safe to use in parallel."""
    global _database
    with _database_lock:
        if _database is None:
            _database = duckdb.connect(str(DB_FILE), read_only=True, config={
                "enable_external_access": False, "lock_configuration": True})
    return _database.cursor()


def check_sql(sql):
    """Layer 3: allow exactly one SELECT statement. Returns an error message, or None if OK."""
    try:
        statements = duckdb.extract_statements(sql)
    except duckdb.Error as err:
        return f"SQL syntax error: {err}"
    if len(statements) != 1:
        return "Send exactly one SQL statement at a time."
    if statements[0].type != duckdb.StatementType.SELECT:
        return "Only SELECT queries are allowed (WITH ... SELECT is fine)."
    return None


def format_rows(columns, rows, total):
    """Turn query results into compact text Claude can read."""
    def cell(value):
        text = "" if value is None else str(value)
        return text if len(text) <= MAX_CELL_CHARS else text[:MAX_CELL_CHARS] + "..."

    lines = [" | ".join(columns)]
    lines += [" | ".join(cell(v) for v in row) for row in rows]
    shown = f"{total} rows" if total <= len(rows) else f"{total} rows total, first {len(rows)} shown"
    return "\n".join(lines) + f"\n({shown})"


# ---------------------------------------------------------------- the tools

def run_with_timeout(con, sql, limit):
    """Run a checked query; return (columns, first `limit` rows, total row count).
    If it is still running after the timeout, it is interrupted."""
    timer = threading.Timer(QUERY_TIMEOUT_SECONDS, con.interrupt)
    timer.start()
    try:
        result = con.execute(sql)
        columns = [d[0] for d in result.description]
        rows = result.fetchmany(limit)
        total = len(rows)
        # Count the remaining rows without keeping them, and stop counting at a cap
        # so a huge result can't fill up memory.
        while total < 100_000 and (chunk := result.fetchmany(10_000)):
            total += len(chunk)
        return columns, rows, total
    except duckdb.InterruptException:
        raise RuntimeError(f"Query took longer than {QUERY_TIMEOUT_SECONDS}s and was "
                           "stopped. Filter earlier or aggregate more.")
    finally:
        timer.cancel()


def run_sql(con, sql):
    problem = check_sql(sql)
    if problem:
        return {"ok": False, "error": problem}
    try:
        columns, rows, total = run_with_timeout(con, sql, MAX_ROWS_SHOWN)
    except (duckdb.Error, RuntimeError) as err:
        # Send the database's own error back. Claude reads it and fixes the query.
        return {"ok": False, "error": str(err).split("\n")[0]}
    return {"ok": True, "rows": total, "result": format_rows(columns, rows, total)}


def describe_table(con, table):
    if table not in GUIDE_FOR_TABLE:
        return {"ok": False, "error": f"Unknown table. Choose from: {', '.join(GUIDE_FOR_TABLE)}"}
    columns = con.execute(f"DESCRIBE {table}").fetchall()
    sample = con.execute(f"SELECT * FROM {table} USING SAMPLE 3 ROWS").fetchall()
    column_names = [c[0] for c in columns]
    guide = (GUIDES / GUIDE_FOR_TABLE[table]).read_text(encoding="utf-8")
    return {
        "ok": True,
        "columns": "\n".join(f"{name} ({kind})" for name, kind, *_ in columns),
        "sample_rows": format_rows(column_names, sample, len(sample)),
        "guide": guide,
    }


# ---------------------------------------------------------------- what Claude sees

# Claude reads these descriptions to decide which tool to use and how.
# Writing them well matters as much as writing the code.
TOOL_DEFINITIONS = [
    charts.DEFINITION,
    {
        "name": "describe_table",
        "description": (
            "Get a table's columns and types, 3 sample rows, and its data guide "
            "(column meanings and known traps). Always call this before querying a "
            "table for the first time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "enum": list(GUIDE_FOR_TABLE)},
            },
            "required": ["table"],
        },
    },
    {
        "name": "run_sql",
        "description": (
            "Run one read-only DuckDB SQL SELECT query against the city database. "
            f"Returns up to {MAX_ROWS_SHOWN} rows plus the total row count, or the "
            "database error message. Aggregate in SQL rather than pulling raw rows. "
            "Use it to explore (e.g. SELECT DISTINCT values) as well as to answer."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "A single SELECT statement."},
                "purpose": {
                    "type": "string",
                    "description": "One short line on what this query checks or answers.",
                },
            },
            "required": ["sql", "purpose"],
        },
    },
]


def run_tool(con, name, tool_input):
    """Dispatch a tool request from Claude to the matching Python function."""
    if name == "make_chart":
        def runner(c, sql, limit):
            columns, rows, _ = run_with_timeout(c, sql, limit)
            return columns, rows
        outcome, chart = charts.make_chart(con, tool_input, check_sql, runner)
        if chart:
            outcome["chart"] = chart  # the agent takes this out before replying to Claude
        return outcome
    if name == "run_sql":
        return run_sql(con, tool_input["sql"])
    if name == "describe_table":
        return describe_table(con, tool_input["table"])
    return {"ok": False, "error": f"No tool named {name}"}
