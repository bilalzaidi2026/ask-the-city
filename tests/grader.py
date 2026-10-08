"""
The grader: scores an answer against a rubric, the way a reviewer marks an exam.

It is separate from the agent and from the checker. The checker is part of the product
(it fixes answers before visitors see them); the grader is part of the testing (it
measures how good the final answers are, so we can tell if a change helped or hurt).
"""
import json
import os

from anthropic import Anthropic

GRADER_MODEL = os.getenv("GRADER_MODEL", "claude-sonnet-5-5")

RUBRIC = {
    "correct": "Every number is supported by the evidence (or equals the true value given). "
               "The headline answers the question that was asked.",
    "trap": "The answer avoids the specific trap described for this question, as the ideal "
            "answer would.",
    "honest": "It states the limits that matter (complaints are not incidents, partial periods, "
              "missing data), admits what the data can't answer, and declines what it should "
              "decline, without inventing figures.",
    "clear": "It opens with a direct answer, is easy for a member of the public to follow, and "
             "is no longer than it needs to be.",
}

INSTRUCTIONS = """You grade answers from an AI analyst that answers questions about New York \
City open data. Be strict but fair, like an experienced editor at a data journalism desk.

Score each dimension from 1 to 5:
5 = excellent, nothing to fix
4 = good, small issues only
3 = acceptable, a noticeable flaw a careful reader would catch
2 = poor, a flaw that misleads or a key element missing
1 = wrong or harmful

Dimensions:
{rubric}

Use the evidence (the agent's actual queries and results) to verify numbers. Do not reward \
length or confident tone. A short, correct refusal can score 5 on every dimension.

Keep each reason to one or two sentences. Reply with JSON only:
{{"correct": {{"score": n, "reason": "..."}}, "trap": {{...}}, "honest": {{...}}, "clear": {{...}}}}"""


def _format_evidence(evidence):
    if not evidence:
        return "(no queries were run)"
    parts = []
    for i, item in enumerate(evidence, 1):
        outcome = item["outcome"]
        result = outcome.get("result") or f"ERROR: {outcome.get('error')}"
        parts.append(f"Query {i} ({item['purpose']}):\n{item['sql']}\n-> {result}")
    return "\n\n".join(parts)


def grade(test, answer, evidence, true_value=None):
    """Return {"scores": {dimension: n}, "reasons": {...}, "average": x} for one answer."""
    rubric = "\n".join(f"- {name}: {text}" for name, text in RUBRIC.items())
    brief = (f"QUESTION: {test['question']}\n\n"
             f"THE TRAP: {test['trap']}\n\n"
             f"WHAT AN IDEAL ANSWER DOES: {test.get('ideal', 'Not specified; use the rubric.')}\n\n"
             + (f"TRUE VALUE (computed independently): {true_value}\n\n" if true_value is not None else "")
             + f"ANSWER TO GRADE:\n{answer}\n\nEVIDENCE:\n{_format_evidence(evidence)}")
    for attempt in range(2):  # one retry if the reply can't be read
        response = Anthropic().messages.create(
            model=GRADER_MODEL, max_tokens=4000,
            system=INSTRUCTIONS.format(rubric=rubric),
            messages=[{"role": "user", "content": brief}],
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        try:
            parsed = json.loads(text[text.index("{"): text.rindex("}") + 1])
            scores = {k: int(parsed[k]["score"]) for k in RUBRIC}
            reasons = {k: str(parsed[k].get("reason", "")) for k in RUBRIC}
            return {"scores": scores, "reasons": reasons,
                    "average": round(sum(scores.values()) / len(scores), 2),
                    "usage": response.usage}
        except (ValueError, KeyError, TypeError):
            continue
    return {"scores": {}, "reasons": {"error": "grader reply unreadable twice"},
            "average": None, "usage": response.usage}
