"""
Charts: turn a query result into a chart spec (Vega-Lite JSON) that a browser draws.

Design choice: Claude never types chart numbers or writes plotting code. It gives a SQL
query plus which columns go where; our code runs the query in the sandbox and fills a
fixed template. So every bar and point comes straight from the data, every chart looks
the same, and no model-written code ever runs.
"""
from datetime import date, datetime

MAX_POINTS = 500
MAX_SERIES = 4

# The first four slots of a validated, colorblind-checked categorical palette.
SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
INK, INK_MUTED, GRID = "#0b0b0b", "#52514e", "#e7e6e2"


def _jsonable(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):  # numpy-style numbers
        return value.item()
    return value


def build_spec(kind, title, rows, x, y, series=None, y_label=None, order="by_value"):
    """Return a Vega-Lite spec for a line or bar chart."""
    temporal = bool(rows) and isinstance(rows[0][x], (date, datetime))
    data = [{k: _jsonable(v) for k, v in row.items()} for row in rows]
    color = ({"field": series, "type": "nominal", "title": None,
              "scale": {"range": SERIES_COLORS},
              "legend": {"orient": "top", "direction": "horizontal"}}
             if series else {"value": SERIES_COLORS[0]})
    tooltip = [{"field": c, "type": "quantitative" if c == y else "nominal",
                **({"format": ",.0f"} if c == y else {})}
               for c in [x, series, y] if c]
    if temporal:
        tooltip[0] = {"field": x, "type": "temporal", "format": "%b %Y"}

    if kind == "line":
        mark = {"type": "line", "strokeWidth": 2, "point": {"size": 30, "filled": True}}
        encoding = {
            "x": {"field": x, "type": "temporal" if temporal else "ordinal", "title": None,
                  "axis": {"format": "%b %Y"} if temporal else {"labelAngle": 0}},
            "y": {"field": y, "type": "quantitative", "title": y_label or y},
        }
    else:  # horizontal bars: long category names stay readable
        mark = {"type": "bar", "cornerRadiusEnd": 4, "height": {"band": 0.7}}
        encoding = {
            # Rankings sort biggest first; periods (years, winters) keep their own order.
            "y": {"field": x, "type": "nominal", "title": None,
                  "sort": "-x" if order == "by_value" else None},
            "x": {"field": y, "type": "quantitative", "title": y_label or y},
        }
        if series:
            encoding["yOffset"] = {"field": series}

    encoding.update({"color": color, "tooltip": tooltip})
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "width": "container",
        "height": 280 if kind == "line" else max(120, 28 * len({r[x] for r in rows})),
        "data": {"values": data},
        "mark": mark,
        "encoding": encoding,
        "config": {
            "background": None,
            "font": "system-ui, -apple-system, sans-serif",
            "axis": {"labelColor": INK_MUTED, "titleColor": INK_MUTED, "gridColor": GRID,
                     "domain": False, "tickColor": GRID, "labelFontSize": 12},
            "view": {"stroke": None},
            "legend": {"labelColor": INK_MUTED},
        },
    }


def make_chart(con, tool_input, check_sql, timeout_runner):
    """Run the chart's query in the sandbox and build the spec. Returns (outcome, chart)."""
    sql = tool_input["sql"]
    problem = check_sql(sql)
    if problem:
        return {"ok": False, "error": problem}, None
    try:
        columns, rows = timeout_runner(con, sql, MAX_POINTS + 1)
    except Exception as err:
        return {"ok": False, "error": str(err).split("\n")[0]}, None

    x, y, series = tool_input["x"], tool_input["y"], tool_input.get("series")
    missing = [c for c in (x, y, series) if c and c not in columns]
    if missing:
        return {"ok": False, "error": f"Columns {missing} not in query result {columns}"}, None
    if not rows:
        return {"ok": False, "error": "The query returned no rows, so there is nothing to chart."}, None
    if len(rows) > MAX_POINTS:
        return {"ok": False, "error": f"More than {MAX_POINTS} points. Aggregate further."}, None
    records = [dict(zip(columns, r)) for r in rows]
    if series and len({r[series] for r in records}) > MAX_SERIES:
        return {"ok": False, "error": f"At most {MAX_SERIES} series. Keep the top ones and "
                                      "group the rest as 'Other', or drop the series."}, None

    spec = build_spec(tool_input["kind"], tool_input["title"], records, x, y, series,
                      tool_input.get("y_label"), tool_input.get("order", "by_value"))
    preview = "\n".join(" | ".join(str(v) for v in r) for r in rows[:5])
    chart = {"title": tool_input["title"], "sql": sql, "spec": spec}
    return {"ok": True, "rows": len(rows),
            "result": f"Chart created from {len(rows)} rows. First rows:\n"
                      f"{' | '.join(columns)}\n{preview}"}, chart


DEFINITION = {
    "name": "make_chart",
    "description": (
        "Draw a chart for the answer. You give a SELECT query and say which columns to "
        "plot; the chart is built from the query's real result, so never type numbers in. "
        "Use 'line' for change over time (x = a month or date column), 'bar' for comparing "
        "places or categories (x = the label column). Use it once per answer at most twice, "
        "only when a picture helps: trends, or comparisons of 3 or more items. Skip it for "
        f"single numbers and refusals. At most {MAX_POINTS} rows and {MAX_SERIES} series."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["line", "bar"]},
            "title": {"type": "string", "description": "Short title stating what is shown, with units and period."},
            "sql": {"type": "string", "description": "One SELECT returning the chart's rows."},
            "x": {"type": "string", "description": "Column for the x axis (dates for line, labels for bar)."},
            "y": {"type": "string", "description": "Numeric column to plot."},
            "series": {"type": "string", "description": "Optional column that splits lines or bars into groups."},
            "y_label": {"type": "string", "description": "Axis label with units, e.g. 'Complaints per 10,000 residents'."},
            "order": {"type": "string", "enum": ["by_value", "as_given"],
                      "description": "Bar charts: 'by_value' ranks biggest first (for comparisons); "
                                     "'as_given' keeps the query's row order (for years or periods)."},
        },
        "required": ["kind", "title", "sql", "x", "y"],
    },
}
