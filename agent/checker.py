"""
The checker: an independent review of a draft answer before anyone sees it.

It gets the question, the draft, and every query the agent ran with its result
(the "evidence"). It does NOT get the agent's conversation, so it judges the
work on what was actually run, not on how convincing the agent sounded.
"""
import json

REVIEW_INSTRUCTIONS = """You review answers written by a data analyst agent about New York \
City open data. You did not write the answer. Your job is to catch mistakes before a member \
of the public sees it.

You receive: the question, the draft answer, and the evidence (every SQL query the agent ran, \
with its result or error). Check the draft against these rules:

1. Every number in the answer appears in the evidence, or follows from it by simple \
arithmetic (sums, shares, rates). Flag any number you cannot trace.
2. The final queries filter on exact category names (complaint_type = '...' or IN (...)), \
not loose patterns like ILIKE '%noise%'. Loose patterns are fine for exploring, not for \
the figures in the answer, because they can sweep in unrelated categories.
3. Time periods: no partial periods in trends or comparisons unless the answer says so. \
"Last month" means the last full calendar month.
4. Places are compared with per-resident rates, not raw counts.
5. Suspicious patterns were checked: zero rows, sudden jumps, one place far above the rest, \
a spike at midnight (possible placeholder timestamps).
6. The answer addresses every part of the question, states any assumption it made, and \
includes caveats that matter.
7. Restaurant data has one row per violation: counts of inspections or restaurants must use \
COUNT(DISTINCT ...).
8. It does not help identify or single out private individuals. A justified refusal with no \
queries passes.

Only flag real problems that would make the answer wrong or misleading. Do not flag style.

Reply with JSON only, no other text:
{"verdict": "pass" or "revise", "problems": ["specific problem and how to fix it", ...]}
"""


def format_evidence(evidence):
    if not evidence:
        return "(no queries were run)"
    parts = []
    for i, item in enumerate(evidence, 1):
        outcome = item["outcome"]
        result = outcome.get("result") or f"ERROR: {outcome.get('error')}"
        parts.append(f"--- Query {i}: {item['purpose']}\n{item['sql']}\nResult:\n{result}")
    return "\n\n".join(parts)


def parse_verdict(text):
    """Pull the JSON verdict out of the reply. If it can't be read, don't block the answer."""
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        verdict = json.loads(text[start:end])
        problems = [str(p) for p in verdict.get("problems", [])]
        status = "revise" if verdict.get("verdict") == "revise" and problems else "pass"
        return {"verdict": status, "problems": problems}
    except (ValueError, json.JSONDecodeError):
        return {"verdict": "pass", "problems": [], "note": "review unreadable; skipped"}


def review(client, model, question, draft, evidence):
    """Returns ({"verdict": "pass"|"revise", "problems": [...]}, usage)."""
    response = client.messages.create(
        model=model,
        max_tokens=2000,
        system=REVIEW_INSTRUCTIONS,
        messages=[{
            "role": "user",
            "content": (f"QUESTION:\n{question}\n\nDRAFT ANSWER:\n{draft}\n\n"
                        f"EVIDENCE:\n{format_evidence(evidence)}"),
        }],
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    return parse_verdict(text), response.usage
