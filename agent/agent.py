"""
The agent loop: the heart of Ask the City.

1. Send Claude the question, the instructions and the tool list.
2. If Claude asks for a tool, run it and send back the result.
3. Repeat until Claude answers in plain text, or the step limit is reached.
"""
import json
import os
from datetime import date

from anthropic import Anthropic
from dotenv import load_dotenv

from agent.tools import TOOL_DEFINITIONS, open_sandbox, run_tool

load_dotenv()

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
MAX_TOOL_CALLS = 12   # enough for real exploration, low enough to cap cost
# Sonnet 5.5 prices in US dollars per million tokens. Cached input is billed at a
# discount when reused (cache_read) and a small premium when first stored (cache_write).
PRICE_PER_MILLION = {"input": 2.00, "output": 10.00, "cache_read": 0.20, "cache_write": 2.50}

INSTRUCTIONS = """You are Ask the City, an analyst who answers questions about New York City \
using the city's open data. Today is {today}.

## Tables
{catalog}

## How to work
1. Call describe_table before you first query a table. Read its guide: it lists traps that \
lead to wrong answers.
2. Before filtering on a category, look up the exact values with SELECT DISTINCT. Never guess \
a category name.
3. Every number in your answer must come from a query you ran. Never estimate or invent figures.
4. Check that results make sense. If something looks odd (zero rows, a sudden jump, one place \
far above the rest), investigate before answering.
5. If a question is vague, choose a sensible reading, and state it in your answer.
6. If the data can't answer the question, say so plainly and offer the closest question it \
can answer.

## Judgment rules
- When comparing places, use rates per 10,000 residents, not raw counts.
- Complaints measure what people report, not what happened.
- Watch for partial periods: the newest data is about a day behind, and the current month is \
incomplete.
- Never try to identify or single out private individuals.

## Answer format (plain text, no markdown headings)
Start with a one-sentence direct answer.
Then the key figures (a short table is fine).
Then "What this can't tell you:" with the 1 to 3 caveats that matter most.
Then "Method:" listing the tables used, the date range covered, and any assumption you made.
"""


def table_catalog_text(con):
    rows = con.execute(
        "SELECT table_name, description, row_count, earliest, latest FROM table_catalog"
    ).fetchall()
    lines = []
    for name, description, count, earliest, latest in rows:
        dates = f", {earliest} to {latest}" if earliest else ""
        lines.append(f"- {name}: {description} ({count:,} rows{dates})")
    return "\n".join(lines)


def show(kind, text):
    """Print one step of the agent's work, so you can watch it think."""
    labels = {"think": "THINK ", "tool": "TOOL  ", "result": "  ->  ", "error": "  !!  "}
    print(f"{labels[kind]}{text}")


def ask(question, verbose=True):
    """Answer one question. Returns the answer text and a summary of what it cost."""
    client = Anthropic()
    con = open_sandbox()
    system = INSTRUCTIONS.format(today=date.today(), catalog=table_catalog_text(con))
    messages = [{"role": "user", "content": question}]
    tool_calls = 0
    tokens = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}

    while True:
        out_of_steps = tool_calls >= MAX_TOOL_CALLS
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            # cache_control: the instructions are identical on every turn, so the API
            # can reuse them instead of re-reading them, which cuts cost and time.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            tools=TOOL_DEFINITIONS,
            # Out of steps: still show Claude the tools, but don't let it call any more.
            tool_choice={"type": "none"} if out_of_steps else {"type": "auto"},
            messages=messages,
        )
        usage = response.usage
        tokens["input"] += usage.input_tokens
        tokens["output"] += usage.output_tokens
        tokens["cache_read"] += usage.cache_read_input_tokens or 0
        tokens["cache_write"] += usage.cache_creation_input_tokens or 0

        # Keep Claude's whole reply in the conversation, exactly as it came back.
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            answer = "".join(block.text for block in response.content if block.type == "text")
            break

        # Claude asked for one or more tools. Run each and collect the results.
        results = []
        for block in response.content:
            if block.type == "text" and block.text.strip() and verbose:
                show("think", block.text.strip())
            if block.type != "tool_use":
                continue
            tool_calls += 1
            if verbose:
                label = block.input.get("purpose") or block.input.get("table", "")
                show("tool", f"{block.name}: {label}")
                if block.name == "run_sql":
                    print("     " + block.input["sql"].strip().replace("\n", "\n     "))
            outcome = run_tool(con, block.name, block.input)
            if verbose:
                if not outcome["ok"]:
                    show("error", outcome["error"])
                elif block.name == "run_sql":
                    # Preview: the header plus up to 3 rows, then the row count.
                    lines = outcome["result"].split("\n")
                    preview = lines[:4] if len(lines) > 5 else lines[:-1]
                    show("result", "\n      ".join(preview) + f"\n      ({outcome['rows']} rows)")
                else:
                    show("result", "columns, sample rows and guide received")
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(outcome, default=str),
                "is_error": not outcome["ok"],
            })
        # Tool results go back to Claude as the next "user" message.
        messages.append({"role": "user", "content": results})

    con.close()
    cost = sum(tokens[k] * PRICE_PER_MILLION[k] for k in tokens) / 1_000_000
    stats = {"tool_calls": tool_calls, **tokens, "cost_usd": round(cost, 4)}
    return answer, stats
