"""
The checker: an independent review of a draft answer before anyone sees it.

It gets the question, the draft, and every query the agent ran with its result
(the "evidence"). It does NOT get the agent's conversation, so it judges the
work on what was actually run, not on how convincing the agent sounded.

Version 2, after measuring version 1: it now flags only problems that would change a
number or a conclusion, sorts them by severity, and only "major" ones trigger a revision.
"""
import json

REVIEW_INSTRUCTIONS = """You review answers written by a data analyst agent about New York \
City open data, before a member of the public sees them. You did not write the answer.

You receive the question, the draft answer, the evidence (every SQL query the agent ran with \
its result or error), and the agent's reference notes (standard definitions and data guides).

Look ONLY for problems that would make a number or a conclusion wrong or misleading:
1. A number in the answer that is not in the evidence and doesn't follow from it by simple \
arithmetic.
2. Final figures computed with loose patterns (ILIKE '%...%') that could include unrelated \
categories, or with a definition that differs from the standard definitions without saying why.
3. A trend or comparison that includes a partial period (the current month, the latest day) \
without saying so, where that could change the conclusion.
4. Places compared by raw counts instead of per-resident rates.
5. Restaurant inspections or restaurants counted by rows instead of COUNT(DISTINCT ...).
6. A close result presented as a clear winner, or a conclusion that would flip under another \
reasonable definition that the answer doesn't mention.
7. Helping identify or single out a private individual.

Do NOT flag:
- Facts taken from the reference notes (they are trusted documentation).
- Style, length, wording, or extra detail you would like to see.
- A refusal or "the data can't answer this" reply, if it is justified. Never push an answer \
to add figures or estimates it reasonably declined to give.

Severity:
- "major": the headline, a key number, the main conclusion, or any stated finding is wrong \
or contradicted by the evidence (e.g. "the drop began in late 2025" when the evidence shows \
early 2025).
- "minor": a real but small issue that doesn't change what a reader would take away.

Reply with JSON only, no other text:
{"problems": [{"severity": "major" or "minor", "issue": "what is wrong and how to fix it"}]}
An empty list means the answer is sound."""


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
    """Pull the JSON out of the reply. If it can't be read, don't block the answer."""
    try:
        start, end = text.index("{"), text.rindex("}") + 1
        found = json.loads(text[start:end]).get("problems", [])
        problems = [{"severity": str(p.get("severity", "minor")).lower(),
                     "issue": str(p.get("issue", p))} for p in found if isinstance(p, dict)]
    except (ValueError, json.JSONDecodeError, AttributeError):
        return {"verdict": "pass", "problems": [], "note": "review unreadable; skipped"}
    major = [p for p in problems if p["severity"] == "major"]
    return {"verdict": "revise" if major else "pass", "problems": problems}


def review(client, model, question, draft, evidence, reference):
    """Returns ({"verdict": "pass"|"revise", "problems": [...]}, usage)."""
    response = client.messages.create(
        model=model,
        max_tokens=2000,
        system=REVIEW_INSTRUCTIONS,
        messages=[{
            "role": "user",
            "content": (f"QUESTION:\n{question}\n\nDRAFT ANSWER:\n{draft}\n\n"
                        f"EVIDENCE:\n{format_evidence(evidence)}\n\n"
                        f"REFERENCE NOTES:\n{reference}"),
        }],
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    return parse_verdict(text), response.usage
