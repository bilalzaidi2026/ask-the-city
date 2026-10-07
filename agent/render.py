"""
Render an answer as a standalone web page: the text, its charts, and how it was made.

The libraries it needs (marked turns markdown into HTML; vega draws the charts) are
bundled in web/vendor and inlined into the page, so a saved answer works offline and
never depends on a third-party server. Step 5's web app reuses this layout.
"""
import html
import json
from pathlib import Path

VENDOR = Path(__file__).parent.parent / "web" / "vendor"
LIBRARIES = ["marked.min.js", "vega.min.js", "vega-lite.min.js", "vega-embed.min.js"]


def inline_scripts():
    return "\n".join(f"<script>{(VENDOR / name).read_text(encoding='utf-8')}</script>"
                     for name in LIBRARIES)

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ask the City: {title}</title>
{scripts}
<style>
  :root {{ --bg:#fcfcfb; --ink:#0b0b0b; --muted:#52514e; --line:#e7e6e2; --accent:#2a78d6; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
         font:16px/1.6 system-ui,-apple-system,sans-serif; padding:32px 20px 64px; }}
  main {{ max-width:760px; margin:0 auto; }}
  .q {{ font-size:13px; letter-spacing:.08em; text-transform:uppercase; color:var(--accent); }}
  h1 {{ font-size:28px; line-height:1.2; margin:6px 0 24px; }}
  table {{ border-collapse:collapse; margin:12px 0; font-variant-numeric:tabular-nums; }}
  th, td {{ border-bottom:1px solid var(--line); padding:6px 12px 6px 0; text-align:left; }}
  .chart-title {{ font-size:15px; line-height:1.35; margin:28px 0 6px; }}
  .chart {{ width:100%; margin:0 0 8px; }}
  details {{ margin-top:32px; border-top:1px solid var(--line); padding-top:12px; color:var(--muted); }}
  pre {{ white-space:pre-wrap; font-size:13px; background:#f3f2ee; padding:10px; border-radius:6px; }}
  .stats {{ font-size:13px; color:var(--muted); margin-top:24px; }}
</style></head>
<body><main>
  <div class="q">Question</div>
  <h1>{question}</h1>
  <div id="answer"></div>
  {chart_divs}
  <details><summary>Show the SQL behind the charts</summary>{chart_sql}</details>
  <div class="stats">{stats}</div>
</main>
<script>
  document.getElementById("answer").innerHTML = marked.parse({answer_json});
  const specs = {specs_json};
  specs.forEach((spec, i) => vegaEmbed("#chart" + i, spec, {{actions: false}}));
</script>
</body></html>
"""


def write_page(question, answer, stats, path):
    charts = stats.get("charts", [])
    page = PAGE.format(
        title=html.escape(question[:60]),
        scripts=inline_scripts(),
        question=html.escape(question),
        answer_json=json.dumps(answer),
        specs_json=json.dumps([c["spec"] for c in charts]),
        chart_divs="\n".join(f'<h3 class="chart-title">{html.escape(c["title"])}</h3>'
                             f'<div class="chart" id="chart{i}"></div>' for i, c in enumerate(charts)),
        chart_sql="".join(f"<p>{html.escape(c['title'])}</p><pre>{html.escape(c['sql'])}</pre>"
                          for c in charts) or "<p>No charts for this answer.</p>",
        stats=html.escape(f"{stats['tool_calls']} tool calls · about ${stats['cost_usd']:.3f} · "
                          f"checker: {stats['final_check']}"),
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")
    return path
