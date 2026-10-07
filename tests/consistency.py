"""
Consistency check: does the same question get the same answer every time?

    python tests/consistency.py            # questions marked "consistency", 3 runs each
    python tests/consistency.py danger 5   # one question, 5 runs

A judge model reads the headlines (first sentence of each answer) and decides whether
they reach the same conclusion. Wording can differ; the conclusion must not.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from anthropic import Anthropic          # noqa: E402

from agent.agent import ask              # noqa: E402
from tests.questions import QUESTIONS    # noqa: E402

JUDGE_MODEL = os.getenv("JUDGE_MODEL", "claude-haiku-4-5-20251001")

JUDGE_INSTRUCTIONS = """You compare several answers to the same question about New York City \
data. Decide whether their headline conclusions agree. Different wording or slightly different \
numbers are fine. A different winner, a different direction (up vs down), or "X is higher" \
vs "they are about the same" is a disagreement.

Reply with JSON only: {"consistent": true or false, "reason": "one sentence"}"""


def headline(answer):
    first = answer.strip().split("\n")[0]
    return first.split(". ")[0].strip()


def judge(question, headlines):
    listed = "\n".join(f"{i}. {h}" for i, h in enumerate(headlines, 1))
    response = Anthropic().messages.create(
        model=JUDGE_MODEL, max_tokens=300, system=JUDGE_INSTRUCTIONS,
        messages=[{"role": "user", "content": f"QUESTION: {question}\n\nHEADLINES:\n{listed}"}],
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    try:
        return json.loads(text[text.index("{"): text.rindex("}") + 1])
    except ValueError:
        return {"consistent": None, "reason": "judge reply unreadable"}


def main():
    args = sys.argv[1:]
    runs = next((int(a) for a in args if a.isdigit()), 3)
    wanted = [a for a in args if not a.isdigit()]
    tests = [t for t in QUESTIONS
             if (t["id"] in wanted) or (not wanted and t.get("consistency"))]

    summary = []
    for test in tests:
        print(f"\n{test['id']}: {test['question']}")
        headlines, cost = [], 0.0
        for i in range(runs):
            try:
                answer, stats = ask(test["question"], verbose=False)
            except Exception as err:
                answer, stats = f"ERROR: {err}", {"cost_usd": 0.0}
            headlines.append(headline(answer))
            cost += stats["cost_usd"]
            print(f"  run {i + 1}: {headlines[-1]}")
        verdict = judge(test["question"], headlines)
        label = {True: "CONSISTENT", False: "INCONSISTENT", None: "UNKNOWN"}[verdict["consistent"]]
        print(f"  -> {label}: {verdict['reason']}  (${cost:.2f})")
        summary.append((test["id"], label, cost))

    print("\n" + "\n".join(f"{tid:<18}{label:<14}${cost:.2f}" for tid, label, cost in summary))


if __name__ == "__main__":
    main()
